"""Audited expense correction versus genuine additional cash settlement.

The original cash event is immutable. A clerical correction adds an amendment
effective on that event's ORIGINAL cash date; it is NOT a new refund today.
"""
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
import db
from monthly_finance import today as business_today


def cash(value, zero=False):
    try:
        total=Decimal(str(value))
    except (InvalidOperation,ValueError):
        raise ValueError("أدخل مبلغاً صحيحاً.")
    if not total.is_finite() or total<0 or (total==0 and not zero) or total>Decimal("99999999.99") or total.as_tuple().exponent < -2:
        raise ValueError("قيمة نقدية خارج النطاق المسموح.")
    return total.quantize(Decimal(".01"))


def _actor(actor):
    if not str(actor or "").strip():
        raise ValueError("حدد المستخدم المسؤول.")
    return str(actor).strip()[:100]


def _before(c, expense_id):
    c.execute("SELECT * FROM expenses WHERE expense_id=%s FOR UPDATE",(expense_id,))
    row=c.fetchone()
    if not row: raise ValueError("المصروف غير موجود.")
    return dict(row)


def _audit(c, expense_id, action, actor, reason, before, after):
    c.execute("""INSERT INTO expense_audit
       (expense_id,action,actor,reason,before_state,after_state)
       VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
       (expense_id,action,actor,reason,
        json.dumps(before,ensure_ascii=False,default=str),
        json.dumps(after,ensure_ascii=False,default=str)))


def _run(expense_id, action, payload, actor, reason, token, handler, expected=None):
    actor=_actor(actor)
    reason=str(reason or "").strip()
    if not reason: raise ValueError("أدخل سبب العملية.")
    token=str(uuid.UUID(str(token or uuid.uuid4())))
    signature=hashlib.sha256(json.dumps({"action":action,"expense_id":expense_id,
                 **payload},sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(token,))
            c.execute("SELECT request_hash FROM expense_request_log WHERE request_token=%s",
                      (token,))
            existing=c.fetchone()
            if existing:
                if existing["request_hash"]!=signature:
                    raise ValueError("تعارض رمز العملية؛ تغيرت بيانات طلب محفوظ.")
                conn.commit()
                return False
            old=_before(c,expense_id)
            if old.get('cancelled_at'):
                if action=='expense_entry_cancelled':
                    conn.commit()
                    return False
                raise ValueError('المصروف ملغى ولا يمكن تعديله أو دفعه.')
            if old.get('teacher_payment_id') or old.get('teacher_advance_id'):
                raise ValueError('هذا المصروف مرتبط براتب أو سلفة؛ عدّل العملية الأصلية من إدارة السجلات.')
            if expected is not None:
                import records
                if records.revision(old)!=expected:
                    raise ValueError('تغيّر المصروف؛ حدّث بياناته قبل الحفظ.')
            import record_history
            record_history.context(c,actor,reason)
            after=handler(c,old)
            _audit(c,expense_id,action,actor,reason,old,after)
            c.execute("""INSERT INTO expense_request_log(request_token,expense_id,request_hash,action)
                      VALUES(%s,%s,%s,%s)""",(token,expense_id,signature,action))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def correct(expense_id, *, amount_total, amount_paid, category, expense_date,
            payee="", notes="", reason, actor, token=None, include_settlements=False, expected=None, payment_method=None):
    """Change the recorded evidence, not the actual date money moved."""
    category=str(category or "").strip()
    if not category or len(category)>100:
        raise ValueError("أدخل اسم مصروف لا يتجاوز 100 حرف.")
    if payment_method is not None and (not str(payment_method).strip() or len(str(payment_method))>50):
        raise ValueError('طريقة الدفع غير صالحة.')
    total=cash(amount_total)
    newpaid=cash(amount_paid,zero=True)
    if newpaid>total: raise ValueError("المدفوع أكبر من قيمة الفاتورة.")
    d=expense_date if isinstance(expense_date,date) else date.fromisoformat(str(expense_date))
    payload={"total":str(total),"paid":str(newpaid),"category":str(category),
             "date":str(d),"payee":str(payee),"notes":str(notes),"reason":str(reason),
             "include_settlements":include_settlements,"payment_method":payment_method}
    def action(c,old):
        c.execute("""SELECT x.event_id,x.source,x.event_date,x.amount+
                  COALESCE((SELECT SUM(a.delta) FROM expense_cash_amendments a
                    WHERE a.event_id=x.event_id),0) AS effective_amount
                  FROM expense_cash_events x WHERE x.expense_id=%s
                  ORDER BY x.event_id FOR UPDATE OF x""",(expense_id,))
        events=c.fetchall()
        if include_settlements:
            # Explicit clerical correction of the entire entry, including earlier
            # settlements. Preserve event dates and append compensating evidence.
            current=sum((Decimal(e['effective_amount']) for e in events),Decimal(0))
            delta=newpaid-current
            if delta>0 and not events:
                c.execute("INSERT INTO expense_cash_events(expense_id,event_date,amount,source) VALUES(%s,%s,%s,'insert')",(expense_id,d,delta))
                delta=0
            for event in reversed(events):
                if not delta: break
                change=delta if delta>0 else max(delta,-Decimal(event['effective_amount']))
                if change:
                    c.execute('INSERT INTO expense_cash_amendments(event_id,expense_id,delta,actor,reason) VALUES(%s,%s,%s,%s,%s)',
                              (event['event_id'],expense_id,change,_actor(actor),str(reason).strip()))
                    delta-=change
            if delta: raise ValueError('لا يوجد سجل صرف أصلي يمكن تصحيحه.')
            status='مدفوع بالكامل' if newpaid==total else 'آجل / دين (غير مدفوع)' if not newpaid else 'مدفوع جزئياً'
            c.execute('UPDATE expenses SET expense_date=%s,category=%s,amount=%s,amount_paid=%s,payment_status=%s,payee=%s,notes=%s,payment_method=COALESCE(%s,payment_method) WHERE expense_id=%s RETURNING *',
                      (d,category,total,newpaid,status,payee,notes,payment_method,expense_id))
            return dict(c.fetchone())
        # Original recorded cash is the ONLY part a correction can amend.
        # Do not rewrite separately dated, truly settled cash movements.
        originals=[e for e in events if e["source"] in ("opening","insert")]
        settled=sum((cash(e["effective_amount"],zero=True) for e in events if e["source"]=="settlement"),Decimal(0))
        target=newpaid-settled
        original=sum((cash(e["effective_amount"],zero=True) for e in originals),Decimal(0))
        if target<0: raise ValueError("لا يمكن تصحيح الدفع بأقل من التسويات النقدية الحقيقية.")
        delta=target-original
        if delta and not originals:
            raise ValueError("لا يوجد قبض أصلي لتصحيحه؛ سجّل تسوية نقدية فعلية.")
        if delta:
            item=originals[0]
            if cash(item["effective_amount"],zero=True)+delta<0:
                raise ValueError("قيمة التصحيح تتجاوز الدفع الأصلي.")
            c.execute("""INSERT INTO expense_cash_amendments
                       (event_id,expense_id,delta,actor,reason)
                       VALUES(%s,%s,%s,%s,%s)""",
                       (item["event_id"],expense_id,delta,_actor(actor),str(reason).strip()))
        status=("مدفوع بالكامل" if newpaid==total else
                "آجل / دين (غير مدفوع)" if newpaid==0 else "مدفوع جزئياً")
        c.execute("""UPDATE expenses SET expense_date=%s,category=%s,amount=%s,
                 amount_paid=%s,payment_status=%s,payee=%s,notes=%s,payment_method=COALESCE(%s,payment_method)
                 WHERE expense_id=%s RETURNING *""",
                 (d,str(category),total,newpaid,status,str(payee),str(notes),payment_method,expense_id))
        after=dict(c.fetchone())
        after["cash_correction_original_date"]=str(originals[0]["event_date"]) if originals else None
        after["cash_correction_delta"]=str(delta)
        return after
    return _run(expense_id,"expense_record_corrected",payload,actor,reason,token,action,expected)


def settle(expense_id, amount, *, on_date=None, actor, reason, token=None):
    paid=cash(amount)
    d=on_date if isinstance(on_date,date) else date.fromisoformat(str(on_date or business_today()))
    if d>business_today():raise ValueError("تاريخ الصرف لا يكون مستقبلياً.")
    payload={"amount":str(paid),"on_date":str(d),"reason":str(reason)}
    def action(c,old):
        remaining=cash(old["amount"])-cash(old["amount_paid"],zero=True)
        if paid>remaining: raise ValueError("مبلغ التسوية أكبر من الدين المتبقي.")
        c.execute("""INSERT INTO expense_cash_events(expense_id,event_date,amount,source)
                   VALUES(%s,%s,%s,'settlement')""",(expense_id,d,paid))
        value=cash(old["amount_paid"],zero=True)+paid
        status="مدفوع بالكامل" if value==cash(old["amount"]) else "مدفوع جزئياً"
        c.execute("""UPDATE expenses SET amount_paid=%s,payment_status=%s
                   WHERE expense_id=%s RETURNING *""",(value,status,expense_id))
        return dict(c.fetchone())
    return _run(expense_id,"expense_cash_settled",payload,actor,reason,token,action)


def cancel(expense_id, *, actor, reason, token=None, expected=None):
    """Cancel an erroneous entry, not evidence of an actual supplier refund."""
    def action(c,old):
        c.execute('''SELECT x.event_id,x.amount+COALESCE((SELECT SUM(delta) FROM expense_cash_amendments
            a WHERE a.event_id=x.event_id),0) AS effective_amount
            FROM expense_cash_events x WHERE x.expense_id=%s ORDER BY event_id FOR UPDATE OF x''',(expense_id,))
        for event in c.fetchall():
            if event['effective_amount']:
                c.execute('INSERT INTO expense_cash_amendments(event_id,expense_id,delta,actor,reason) VALUES(%s,%s,%s,%s,%s)',
                          (event['event_id'],expense_id,-event['effective_amount'],_actor(actor),str(reason).strip()))
        c.execute("UPDATE expenses SET amount=0,amount_paid=0,payment_status='ملغى',cancelled_at=now() WHERE expense_id=%s RETURNING *",(expense_id,))
        return dict(c.fetchone())
    return _run(expense_id,'expense_entry_cancelled',{'reason':str(reason)},actor,reason,token,action,expected)
