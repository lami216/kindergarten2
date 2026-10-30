"""Non-cash debt waiver and durable child archive. No DELETE, no fake income."""
import uuid
from datetime import date
from hashlib import sha256
import json
import db
import monthly_finance as F


def _actor(actor):
    if not str(actor or "").strip():
        raise ValueError("حدد المستخدم المسؤول.")
    return str(actor).strip()[:100]


def _debt(c, student, when):
    """Caller holds account row lock; a past obligation is not a future bill."""
    c.execute("""SELECT f.fee_id AS ident,NULL::bigint AS period_id,
              f.kind AS kind,f.price,
              COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
                JOIN monthly_receipts r ON a.receipt_id=r.receipt_id
                WHERE a.fee_id=f.fee_id AND a.active AND r.state='active'),0) AS paid,
              COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                WHERE w.fee_id=f.fee_id),0) AS waived
        FROM monthly_fees f WHERE f.student_id=%s""",(student,))
    fees=[dict(x) for x in c.fetchall()]
    c.execute("""SELECT NULL::bigint AS ident,p.period_id,p.period_no::text AS kind,
           p.price,
           COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             WHERE a.period_id=p.period_id AND a.active AND r.state='active'),0) AS paid,
           COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
             WHERE w.period_id=p.period_id),0) AS waived
           FROM monthly_periods p JOIN monthly_accounts m USING(student_id)
           WHERE p.student_id=%s AND (CASE WHEN m.due_at_period_end THEN p.ends ELSE p.starts END)<=%s
           ORDER BY p.period_no""",(student,when))
    periods=[dict(x) for x in c.fetchall()]
    return [dict(x,remaining=int(x["price"])-int(x["paid"])-int(x["waived"]))
            for x in fees+periods]


def current_debt(c, student, account, *, as_of=None):
    """Read issued debt for every status; only regular accounts issue new months."""
    day=as_of or F.today()
    F._due_started(c,student,account,as_of=day)
    for boundary in (account.get('departure_on'),
                     account.get('exempt_from') if account['status']=='exempt' else None):
        if boundary: day=min(day,boundary)
    return _debt(c,student,day)


def waiver_preview(conn, student, *, as_of=None):
    """Read-only preview (may omit an as-yet-unissued started month)."""
    result=F.projection(conn,student,as_of=as_of,materialize=True)
    return result


def waive_in_transaction(c, student, rows, *, actor, reason, token, fingerprint, day):
    """Caller owns the canonical account lock and transaction; never records cash."""
    total=sum(max(0,r["remaining"]) for r in rows)
    if not total:return 0
    if any(r['remaining']<0 for r in rows):raise ValueError('تجاوز التمويل قيمة الرسم.')
    c.execute("""INSERT INTO monthly_waiver_batches
        (request_token,student_id,request_hash,effective_on,actor,reason,gross_waived)
        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
        (token,student,fingerprint,day,actor,reason,total))
    for row in rows:
        due=max(0,row["remaining"])
        if not due: continue
        item_key=("fee:"+str(row["ident"])) if row["ident"] else ("month:"+str(row["period_id"]))
        item_token=str(uuid.uuid5(uuid.UUID(token),item_key))
        before={"price":int(row["price"]),"paid":int(row["paid"]),
                "previous_waived":int(row["waived"]),"remaining":due}
        after={**before,"new_waived":int(row["waived"])+due,"remaining":0}
        c.execute("""INSERT INTO monthly_waivers
           (student_id,fee_id,period_id,amount,effective_on,request_token,
            request_hash,actor,reason,before_state,after_state)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
           (student,row["ident"],row["period_id"],due,day,item_token,fingerprint,
            actor,reason,json.dumps(before),json.dumps(after)))
    F._audit(c,student,None,"debt_waived_non_cash",actor,
             {"gross_due":total},{"waived":total,"cash":0},reason)
    return total


def waive_debt(student, reason, confirmed, *, actor, token=None, effective_on=None,
               expected_revision=None, expected_due=None):
    """Explicitly void the *outstanding* part of each already issued obligation.

    The original gross fee/period and cash-paid allocations remain untouched.
    A request can only be replayed identically; differing use of its UUID fails.
    """
    actor=_actor(actor)
    reason=str(reason or "").strip()
    if not confirmed or not reason:
        raise ValueError("اكتب السبب وأكّد إلغاء الدين صراحةً.")
    day=effective_on or F.today()
    if isinstance(day,str): day=date.fromisoformat(day)
    if day>F.today(): raise ValueError("تاريخ إلغاء الدين لا يكون مستقبلياً.")
    token=str(uuid.UUID(str(token or uuid.uuid4())))
    fingerprint=sha256(json.dumps({"student":student,"reason":reason,"day":str(day)},
                sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'accounts.delete',actor)
            account=F._lock(c,student,for_payment=False)
            c.execute("SELECT gross_waived,request_hash FROM monthly_waiver_batches WHERE request_token=%s",
                      (token,))
            old=c.fetchone()
            if old:
                if old["request_hash"]!=fingerprint:
                    raise ValueError("تعارض رمز الإلغاء؛ تغيرت بيانات الطلب.")
                total=int(old["gross_waived"])
                conn.commit()
                return total,False
            if account["archived_at"]:
                raise ValueError("الحساب مؤرشف؛ لا تلغِ ديناً جديداً دون مراجعة مالية.")
            if expected_revision is not None:
                F._assert_receipt_revision(c,student,expected_revision)
            rows=current_debt(c,student,account,as_of=day)
            total=sum(max(0,r["remaining"]) for r in rows)
            if expected_due is not None and total!=expected_due:
                raise ValueError('تغيّر الدين؛ حدّث الملف وراجع المبلغ قبل إسقاطه.')
            if not total:
                raise ValueError("لا يوجد دين مستحق لإلغائه.")
            if any(r["remaining"]<0 for r in rows):
                raise ValueError("تجاوز التمويل قيمة الرسم.")
            waive_in_transaction(c,student,rows,actor=actor,reason=reason,token=token,
                fingerprint=fingerprint,day=day)
        conn.commit()
        return total,True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def pay_unpaid_fee(student, kind, *, actor, token=None, expected_due=None, as_of=None):
    """Accept real cash for exactly one requested, presently unpaid fee."""
    if expected_due is not None: F.amount(expected_due)
    if kind not in ("registration","gilet"):
        raise ValueError("اختر الرسم المستحق فقط.")
    actor=_actor(actor)
    token=str(uuid.UUID(str(token or uuid.uuid4())))
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'payments.create',actor)
            account=F._lock(c,student)
            row=F._fee(c,student,kind)
            if not row:
                raise ValueError("هذا الرسم غير مطلوب لهذا الطفل.")
            due=int(row["price"])-int(row["paid"])-int(row["waived"])
            c.execute("""SELECT receipt_id,request_hash,amount,student_id,state
                         FROM monthly_receipts WHERE request_token=%s""",(token,))
            old=c.fetchone()
            if old:
                if expected_due is not None and (expected_due!=int(old["amount"]) or old["state"]!="active"):
                    raise ValueError("تغيّرت الدفعة؛ أعد فتح نافذة تسديد الرسم.")
                previous_payload={"student":student,"kind":kind,"fee_id":row["fee_id"],
                                  "amount":int(old["amount"]),"purpose":"specific-unpaid-fee"}
                if as_of is not None: previous_payload['received_on']=str(as_of)
                previous_hash=F._hash(previous_payload)
                if old["student_id"]!=student or old["request_hash"]!=previous_hash:
                    raise ValueError("تعارض رمز طلب القبض؛ تغير الرسم أو الطفل.")
                conn.commit()
                return old["receipt_id"],False
            if due<=0: raise ValueError("لا يوجد مبلغ مستحق لهذا الرسم.")
            if expected_due is not None and due!=expected_due:
                raise ValueError("تغيّر المبلغ المستحق؛ أعد فتح نافذة تسديد الرسم.")
            payload={"student":student,"kind":kind,"fee_id":row["fee_id"],
                     "amount":due,"purpose":"specific-unpaid-fee"}
            if as_of is not None: payload['received_on']=str(as_of)
            fingerprint=F._hash(payload)
            rid,new=F._issue(c,account,due,"ولي الأمر",actor,token,fingerprint,
                    selected_registration=kind=="registration",selected_gilet=kind=="gilet",as_of=as_of)
        conn.commit()
        return rid,new
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def restore_student(student, *, actor, reason, expected, expected_account=None):
    """Reopen for review, keeping the departure cutoff; never bill absence.

    A later actual return to attendance must explicitly establish subscription
    terms. Restoration alone is not an authorization to create missed months.
    """
    import records as R
    import record_history as H
    if not str(reason or '').strip(): raise ValueError('اكتب سبب استرجاع الملف.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'students.edit',actor)
            child=R._lock(c,'students',student,expected)
            if not child['archived_at']: raise ValueError('الملف مسترجع بالفعل؛ حدّث القائمة.')
            c.execute('SELECT * FROM monthly_accounts WHERE student_id=%s FOR UPDATE',(student,))
            account=c.fetchone()
            if account:
                A.require(c,'accounts.edit')
                if not expected_account or R.revision(account)!=expected_account:
                    raise ValueError('تغيّر الحساب؛ أعد فتح نافذة الاسترجاع.')
                H.context(c,actor,reason)
                cutoff=account.get('departure_on') or child['archived_at'].date()
                c.execute('''UPDATE monthly_accounts SET archived_at=NULL,archived_by=NULL,
                    departure_on=%s WHERE student_id=%s''',(cutoff,student))
                F._audit(c,student,None,'student_restored_for_review',actor,dict(account),
                         {'departure_on':str(cutoff),'cash':0},reason)
            A.require(c,'students.edit')
            H.context(c,actor,reason)
            c.execute('UPDATE students SET archived_at=NULL,archived_by=NULL WHERE student_id=%s',(student,))
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: conn.close()


def archive_student(student, *, actor):
    """Never delete a child or its family/receipts. Lock and recheck cash debt."""
    actor=_actor(actor)
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'students.delete',actor)
            c.execute("SELECT student_id,archived_at FROM students WHERE student_id=%s FOR UPDATE",(student,))
            child=c.fetchone()
            if not child: raise ValueError("الطالب غير موجود.")
            if child["archived_at"]: raise ValueError("هذا الطالب مؤرشف بالفعل.")
            c.execute("SELECT * FROM monthly_accounts WHERE student_id=%s FOR UPDATE",(student,))
            account=c.fetchone()
            if account:
                rows=current_debt(c,student,account)
                due=sum(max(0,r["remaining"]) for r in rows)
                if due:
                    raise ValueError(f"لا يمكن حذف الطالب؛ عليه مبلغ {due:,} أوقية قديمة.")
            c.execute("UPDATE students SET archived_at=NOW(),archived_by=%s WHERE student_id=%s",
                      (actor,student))
            if account:
                c.execute("""UPDATE monthly_accounts SET archived_at=NOW(),
                             archived_by=%s,departure_on=%s WHERE student_id=%s""",
                          (actor,min(account.get('departure_on') or F.today(),F.today()),student))
                F._audit(c,student,None,"student_archived",actor,{},
                         {"departed_on":str(F.today()),"cash":0})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def remove_guardian_if_unlinked(guardian_id):
    """Server-side FK-safe guardian removal; never unlink siblings or debts."""
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            A.require(c,'parents.delete')
            c.execute("SELECT father_id FROM parents WHERE father_id=%s FOR UPDATE",(guardian_id,))
            if not c.fetchone():
                raise ValueError("ولي الأمر غير موجود.")
            c.execute("""SELECT student_id,full_name FROM students WHERE father_id=%s
                         ORDER BY student_id FOR UPDATE""",(guardian_id,))
            children=c.fetchall()
            if children:
                # Real child identities must remain linked, even when archived.
                child=children[0]
                c.execute("""SELECT * FROM monthly_accounts
                             WHERE student_id=%s FOR UPDATE""",(child["student_id"],))
                account=c.fetchone()
                if account:
                    due=sum(max(0,x["remaining"]) for x in current_debt(c,child["student_id"],account))
                    if due:
                        raise ValueError(f"لا يمكن حذف ولي الأمر؛ الطفل {child['full_name']} عليه مبلغ {due:,} أوقية قديمة.")
                raise ValueError("لا يمكن حذف ولي الأمر؛ ما زالت به ملفات أطفال مرتبطة، بما فيها المؤرشفة.")
            c.execute("DELETE FROM parents WHERE father_id=%s",(guardian_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
