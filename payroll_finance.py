"""Transactional cash-preserving payroll operations for salary slips and advances.

Cancellation retires a document but NEVER means cash was refunded. Actual
original outflow stays in cash_amount and remains in every cash report.
"""
import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
import db
from monthly_finance import today as business_today


def _cash(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("أدخل مبلغاً نقدياً صحيحاً.")
    if not value.is_finite() or value <= 0 or value > Decimal("99999999.99") or value.as_tuple().exponent < -2:
        raise ValueError("المبلغ خارج النطاق المسموح.")
    return value.quantize(Decimal(".01"))


def _fingerprint(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def _audit(c, table, ident, action, actor, reason, before, after):
    column = "payment_id" if table == "teacher_payments" else "advance_id"
    c.execute(f"""INSERT INTO payroll_audit
       ({column},action,actor,reason,before_state,after_state)
       VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
       (ident,action,actor,reason,
        json.dumps(dict(before or {}),ensure_ascii=False,default=str),
        json.dumps(dict(after or {}),ensure_ascii=False,default=str)))


def _actor(actor):
    if not str(actor or "").strip():
        raise ValueError("يجب تحديد المستخدم المسؤول.")
    return str(actor).strip()[:100]


def _month(text):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",str(text)):
        raise ValueError("شهر الصرف يجب أن يكون YYYY-MM.")
    return str(text)


def _insert(table, national_id, args, *, token=None, actor, reason=None):
    who = _actor(actor)
    if reason is not None and (not isinstance(reason,str) or not reason.strip() or len(reason)>2000):
        raise ValueError('أدخل سبب الصرف، حتى 2000 حرف.')
    why = reason.strip() if reason is not None else 'صرف نقدي فعلي'
    token = str(token or uuid.uuid4())
    try:
        token = str(uuid.UUID(token))
    except ValueError:
        raise ValueError("رمز طلب الحفظ غير صحيح.")
    payload = {"table":table,"national_id":national_id,**args}
    # Keep the fingerprints of older callers stable; new callers bind the reason
    # to the idempotent request as well as both audit records.
    if reason is not None: payload['reason']=why
    fp = _fingerprint(payload)
    conn = db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            who=A.actor(c,'salaries.create',who)
            import record_history as H
            H.context(c,who,why)
            # Transactional advisory lock serializes retries with identical IDs.
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (token,))
            c.execute(f"SELECT * FROM {table} WHERE request_token=%s", (token,))
            previous = c.fetchone()
            if previous:
                if previous["request_hash"] != fp:
                    raise ValueError("تعارض رمز الحفظ: نفس الطلب يحتوي على بيانات مختلفة.")
                conn.commit()
                return previous["payment_id" if table=="teacher_payments" else "advance_id"],False
            c.execute("SELECT * FROM teachers WHERE national_id=%s AND archived_at IS NULL FOR UPDATE",
                      (national_id,))
            teacher=c.fetchone()
            if not teacher:
                raise ValueError("لا يمكن صرف مبالغ لمعلمة مؤرشفة أو غير موجودة.")
            import teacher_payroll as TP
            day=date.fromisoformat(str(args['date']))
            if not date(1990,1,1)<=day<=business_today():raise ValueError('تاريخ الصرف غير صالح أو مستقبلي.')
            TP.month(args['month'])
            if table=='teacher_payments':TP.prepare_salary(c,teacher,args)
            else:TP.validate_start(teacher,args['month'],args['date'])
            if table=="teacher_payments":
                c.execute("""INSERT INTO teacher_payments
                    (national_id,amount,cash_amount,payment_date,salary_month,
                     base_salary,bonus,deductions,notes,request_token,request_hash,advance,managed_month)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING payment_id""",
                    (national_id,args["amount"],args["amount"],args["date"],args["month"],
                     args["base"],args["bonus"],args["deductions"],args["notes"],token,fp,args.get('advance',0),args.get('managed',False)))
                ident=c.fetchone()["payment_id"]
                TP.persist_settlements(c,ident,args)
            else:
                c.execute("""INSERT INTO teacher_advances
                    (national_id,amount,cash_amount,advance_date,salary_month,
                     notes,request_token,request_hash)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING advance_id""",
                    (national_id,args["amount"],args["amount"],args["date"],args["month"],
                     args["notes"],token,fp))
                ident=c.fetchone()["advance_id"]
            c.execute(f"SELECT * FROM {table} WHERE "+("payment_id" if table=="teacher_payments" else "advance_id")+"=%s",(ident,))
            _audit(c,table,ident,"cash_disbursed",who,why,{},c.fetchone())
        conn.commit()
        return ident,True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def salary_preview(base, bonus=0, deductions=0):
    """One exact calculation for the visible preview and the persisted cash."""
    try:
        base,bonus,deductions=(Decimal(str(v)) for v in (base,bonus,deductions))
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError('أدخل مبالغ صحيحة للراتب والمكافأة والخصومات.') from None
    if any(not v.is_finite() or v<0 or v.as_tuple().exponent < -2 for v in (base,bonus,deductions)):
        raise ValueError("قيمة الراتب أو الخصم غير صحيحة.")
    if deductions>base+bonus:
        raise ValueError('الخصومات أكبر من الراتب والمكافأة؛ راجع المبالغ.')
    if base+bonus==deductions:
        raise ValueError('صافي الراتب يجب أن يكون أكبر من صفر لتسجيل صرف.')
    return {'base':base,'bonus':bonus,'deductions':deductions,'net':_cash(base+bonus-deductions)}


def save_salary(national_id, month, base, bonus=0, deductions=0,
                notes="", *, actor, token=None, on_date=None, reason=None,
                payment_cash=None,settlements=None,account_revision=None,managed=False):
    preview=salary_preview(base,bonus,deductions)
    base,bonus,deductions,total=(preview[k] for k in ('base','bonus','deductions','net'))
    return _insert("teacher_payments",str(national_id),
        {"amount":total,"date":str(on_date or business_today()),"month":_month(month),
         "base":base,"bonus":bonus,"deductions":deductions,"notes":str(notes or ""),
         **(dict(payment_cash=payment_cash,settlements=settlements,account_revision=account_revision,managed=True) if managed else {})},
        actor=actor,token=token,reason=reason)


def save_advance(national_id, month, cash, notes="", *, actor, token=None,on_date=None,reason=None):
    return _insert("teacher_advances",str(national_id),
        {"amount":_cash(cash),"date":str(on_date or business_today()),"month":_month(month),
         "notes":str(notes or "")},actor=actor,token=token,reason=reason)


def amend(table, ident, *, actor, reason, cancel=False, month=None, notes=None, expected=None):
    """Document correction/void, not a refund: cash_amount never changes."""
    if table not in ("teacher_payments","teacher_advances"):
        raise ValueError("نوع القسيمة غير صالح.")
    actor=_actor(actor)
    reason=str(reason or "").strip()
    if not reason:
        raise ValueError("اذكر سبب التصحيح أو الإلغاء.")
    column="payment_id" if table=="teacher_payments" else "advance_id"
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            import access_control as A
            actor=A.actor(c,'salaries.delete' if cancel else 'salaries.edit',actor)
            import record_history
            record_history.context(c,actor,reason)
            c.execute(f'SELECT national_id FROM {table} WHERE {column}=%s',(ident,))
            owner=c.fetchone()
            if owner:
                import teacher_payroll as TP
                TP.teacher(c,owner['national_id'],lock=True)
            c.execute(f"SELECT * FROM {table} WHERE {column}=%s FOR UPDATE",(ident,))
            old=c.fetchone()
            if not old: raise ValueError("القسيمة غير موجودة.")
            import records as R
            if expected is not None and R.revision(old)!=expected:
                raise ValueError('تغيّر السجل منذ فتحه؛ حدّث النموذج وراجع البيانات الجديدة.')
            if old["record_state"]!="active":
                raise ValueError("القسيمة ملغاة بالفعل.")
            if cancel:
                c.execute(f"UPDATE {table} SET record_state='cancelled' WHERE {column}=%s RETURNING *",(ident,))
                action="document_cancelled_cash_retained"
            else:
                import teacher_payroll as TP
                if table=='teacher_payments':
                    state=TP.data(c,old['national_id'])
                    allocations=[dict(id=s['advance_id'],amount=s['amount']) for s in state['settlements'] if s['active'] and s['payment_id']==ident]
                    args=dict(month=_month(month),date=str(old['payment_date']),amount=old['cash_amount'],base=old['base_salary'],bonus=old['bonus'],deductions=old['deductions'],managed=old['managed_month'],settlements=allocations)
                    TP.prepare_salary(c,state['teacher'],args,exclude=ident)
                else:
                    TP.validate_start(TP.teacher(c,old['national_id']),_month(month),old['advance_date'])
                    c.execute('''SELECT 1 FROM teacher_advance_settlements s JOIN teacher_payments p USING(payment_id)
                      WHERE s.advance_id=%s AND s.active AND p.salary_month<%s LIMIT 1''',(ident,_month(month)))
                    if c.fetchone():raise ValueError('توجد تسديدات تسبق التاريخ الجديد للسلفة؛ صحح دفعاتها المرتبطة أولًا.')
                c.execute(f"""UPDATE {table} SET salary_month=%s,notes=%s
                    WHERE {column}=%s RETURNING *""",
                    (_month(month),str(notes or ""),ident))
                action="document_corrected"
            new=c.fetchone()
            _audit(c,table,ident,action,actor,reason,old,new)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def archive_teacher(national_id, *, actor):
    actor=_actor(actor)
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            import access_control as A
            actor=A.actor(c,'teachers.delete',actor)
            c.execute("""UPDATE teachers SET archived_at=now(),archived_by=%s
                      WHERE national_id=%s AND archived_at IS NULL RETURNING national_id""",
                      (actor,national_id))
            if not c.fetchone():
                raise ValueError("ملف المعلمة مؤرشف أو غير موجود.")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def correct_cash_entry(table, ident, *, actor, reason, expected=None, cancel=False,
                       amount=None, base=0, bonus=0, deductions=0, month=None, on_date=None, notes='', national_id=None,
                       payment_cash=None,settlements=None,account_revision=None,managed=False):
    """Explicit correction of erroneous cash input, distinct from retiring a slip."""
    if table not in ('teacher_payments','teacher_advances'): raise ValueError('نوع العملية غير صالح.')
    actor=_actor(actor)
    if not str(reason or '').strip(): raise ValueError('أدخل سبب التصحيح أو الإلغاء.')
    if not cancel:
        month=_month(month)
        day=date.fromisoformat(str(on_date))
        if day>business_today(): raise ValueError('تاريخ الصرف لا يكون مستقبليًا.')
        if table=='teacher_payments':
            from expense_finance import cash
            base,bonus,deductions=(cash(x,zero=True) for x in (base,bonus,deductions))
            amount=_cash(base+bonus-deductions)
        else: amount=_cash(amount)
    conn=db.new_transaction_connection()
    column='payment_id' if table=='teacher_payments' else 'advance_id'
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'salaries.delete' if cancel else 'salaries.edit',actor)
            import record_history as H
            import records as R
            H.context(c,actor,reason)
            c.execute(f'SELECT national_id FROM {table} WHERE {column}=%s',(ident,))
            owner=c.fetchone()
            if not owner:raise ValueError('العملية غير موجودة.')
            import teacher_payroll as TP
            person=TP.teacher(c,owner['national_id'],lock=True)
            old=R._lock(c,table,ident,expected)
            account=TP.data(c,old['national_id'])
            TP.check_revision(account,account_revision)
            if table=='teacher_advances' and old['legacy_repaid'] and (cancel or amount<old['legacy_repaid']):
                raise ValueError('اربط التسديد القديم بدفعة الراتب أولًا، أو صحح حالته السابقة؛ لن نخمن الشهر المتأثر.')
            linked=sum((s['amount'] for s in account['settlements'] if s['active'] and s['payment_id']==ident),Decimal(0)) if table=='teacher_payments' else 0
            if table=='teacher_payments' and not old['managed_month'] and old['advance']>linked:
                raise ValueError('اربط تسديد السلفة القديم بمصدره أولًا قبل تصحيح هذه الدفعة أو إلغائها.')
            if table=='teacher_payments' and old['managed_month'] and not managed and not cancel:
                raise ValueError('صحح هذه الدفعة من ملف المعلم للحفاظ على تسديد السلف والدفعات الجزئية.')
            if old.get('entry_cancelled_at'):
                if cancel: conn.commit(); return False
                raise ValueError('الإدخال ملغى بالفعل.')
            if cancel:
                if table=='teacher_payments':TP.persist_settlements(c,ident,{})
                else:TP.trim_advance(c,ident,Decimal(0))
                c.execute(f"UPDATE {table} SET cash_amount=0,record_state='cancelled',entry_cancelled_at=now() WHERE {column}=%s RETURNING *",(ident,))
                action='cash_entry_cancelled'
            else:
                teacher=national_id or old['national_id']
                if teacher!=old['national_id']:raise ValueError('لا تنقل راتبًا بين حسابين؛ صحح ملف المعلم من مصدره.')
                c.execute('SELECT national_id FROM teachers WHERE national_id=%s AND archived_at IS NULL FOR SHARE',(teacher,))
                if not c.fetchone() and teacher!=old['national_id']: raise ValueError('المعلمة غير موجودة أو محذوفة.')
                if table=='teacher_payments':
                    if teacher!=old['national_id']:raise ValueError('لا تنقل راتبًا بين حسابين؛ صحح ملف المعلم من مصدره.')
                    args=dict(amount=amount,base=base,bonus=bonus,deductions=deductions,month=month,date=str(day),
                      payment_cash=payment_cash,settlements=settlements,account_revision=account_revision,managed=managed)
                    TP.prepare_salary(c,person,args,exclude=ident)
                    amount=args['amount'];base=args['base'];bonus=args['bonus'];deductions=args['deductions']
                    c.execute('''UPDATE teacher_payments SET national_id=%s,amount=%s,cash_amount=%s,
                        base_salary=%s,bonus=%s,deductions=%s,salary_month=%s,payment_date=%s,notes=%s,advance=%s,managed_month=%s
                        WHERE payment_id=%s RETURNING *''',(teacher,amount,amount,base,bonus,deductions,month,day,notes,args.get('advance',0),managed,ident))
                    after=c.fetchone();TP.persist_settlements(c,ident,args)
                else:
                    TP.validate_start(person,month,day)
                    c.execute('''SELECT 1 FROM teacher_advance_settlements s JOIN teacher_payments p USING(payment_id)
                      WHERE s.advance_id=%s AND s.active AND (p.payment_date<%s OR p.salary_month<%s) LIMIT 1''',(ident,day,month))
                    if c.fetchone():raise ValueError('توجد تسديدات تسبق التاريخ الجديد للسلفة؛ صحح دفعاتها المرتبطة أولًا.')
                    TP.trim_advance(c,ident,amount)
                    c.execute('''UPDATE teacher_advances SET national_id=%s,amount=%s,cash_amount=%s,
                        salary_month=%s,advance_date=%s,notes=%s WHERE advance_id=%s RETURNING *''',
                        (teacher,amount,amount,month,day,notes,ident))
                    after=c.fetchone()
                action='cash_entry_corrected'
            if cancel:after=c.fetchone()
            TP.sync_advances(c,old['national_id'])
            c.execute(f'SELECT * FROM {table} WHERE {column}=%s',(ident,));after=c.fetchone()
            _audit(c,table,ident,action,actor,reason,old,after)
            # A explicitly linked mirror cannot leave a phantom supplier debt.
            link='teacher_payment_id' if table=='teacher_payments' else 'teacher_advance_id'
            c.execute(f"UPDATE expenses SET amount=%s,amount_paid=%s,payment_status=%s,cancelled_at=CASE WHEN %s THEN now() ELSE cancelled_at END WHERE {link}=%s",
                      (0 if cancel else amount,0 if cancel else amount,'ملغى' if cancel else 'مدفوع بالكامل',cancel,ident))
        conn.commit(); return True
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
