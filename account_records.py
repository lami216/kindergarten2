"""Audited corrections to subscription inputs and explicit noncash waivers."""
import uuid
from datetime import date
import db
import monthly_finance as F
import record_history as H
import records as R


def exemption_preview(conn, student):
    import access_control as A
    import student_debt as D
    with conn.cursor() as c:
        A.require(c,'accounts.edit')
        old=F._lock(c,student,for_payment=False)
        rows=D.current_debt(c,student,old)
        due=sum(max(0,r['remaining']) for r in rows)
        return dict(student=student,due=due,revision=R.revision(old),
            ledger_revision=F.receipt_revision(conn,student),status=old['status'],
            can_waive=not due or A.can('accounts.delete'))


def change_account(student, *, actor, reason, start_date=None, status=None, cancel=False, expected=None,
                   token=None, expected_due=None, expected_ledger=None, confirmed=False):
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب التغيير وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'accounts.delete' if cancel else 'accounts.edit',actor)
            fingerprint=F._hash(dict(student=student,status=status,start_date=str(start_date),cancel=cancel,
                reason=reason,actor=actor,expected=expected,due=expected_due,ledger=expected_ledger,confirmed=confirmed))
            if token:
                token=str(uuid.UUID(str(token)))
                c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(token,))
                c.execute('SELECT * FROM account_status_requests WHERE request_token=%s',(token,))
                previous=c.fetchone()
                if previous:
                    if previous['request_hash']!=fingerprint:raise ValueError('تغيّرت بيانات طلب الإعفاء؛ افتح تأكيدًا جديدًا.')
                    if previous['waived']:A.require(c,'accounts.delete')
                    conn.commit();return dict(waived=int(previous['waived']),created=False)
            H.context(c,actor,reason)
            c.execute('SELECT birth_date,archived_at FROM students WHERE student_id=%s FOR KEY SHARE',(student,))
            child=c.fetchone()
            old=R._lock(c,'monthly_accounts',student,expected)
            if old['archived_at'] or not child or child['archived_at']: raise ValueError('الحساب ملغى بالفعل.')
            waived=0
            if expected_ledger is not None:F._assert_receipt_revision(c,student,expected_ledger)
            if cancel:
                import student_debt as D
                if any(r['remaining']>0 for r in D.current_debt(c,student,old)):
                    raise ValueError('سدّد أو ألغِ الدين المتبقي أولًا؛ الدفعات والإعفاءات متاحة في إدارة السجلات.')
                c.execute('UPDATE monthly_accounts SET archived_at=now(),archived_by=%s,departure_on=%s WHERE student_id=%s',(actor,min(old.get('departure_on') or F.today(),F.today()),student))
            else:
                anchor=date.fromisoformat(str(start_date or old['start_date']))
                if anchor>F.today() or anchor<date(1990,1,1): raise ValueError('اختر تاريخ بداية بين 1990 واليوم.')
                if status not in ('regular','exempt'): raise ValueError('اختر حالة الرسوم.')
                if status==old['status']=='exempt' and anchor==old['start_date']:
                    conn.commit();return dict(waived=0,created=False)
                if anchor!=old['start_date']:
                    from subscription_dates import correct_start
                    correct_start(c,student,str(anchor),actor=actor,reason=reason,
                        birth=child['birth_date'] if child else None,expected=R.revision(old),
                        expected_ledger=F.receipt_revision(conn,student))
                if old['status']=='regular' and status=='exempt':
                    import student_debt as D
                    if anchor!=old['start_date']:raise ValueError('صحح بداية الاشتراك أولًا ثم افتح تأكيد الإعفاء.')
                    rows=D.current_debt(c,student,old)
                    total=sum(max(0,item['remaining']) for item in rows)
                    if expected_due is not None and (type(expected_due) is not int or total!=expected_due):
                        raise ValueError('تغيّر الدين؛ حدّث الملف وراجع المبلغ قبل إسقاطه.')
                    if total:
                        A.require(c,'accounts.delete')
                        if not confirmed or expected_due is None or expected_ledger is None or not expected or not token:
                            raise ValueError('راجع مبلغ الدين وأكد إسقاطه مع التحويل إلى معفي.')
                        waived=D.waive_in_transaction(c,student,rows,actor=actor,reason=reason,
                            token=token,fingerprint=fingerprint,day=F.today())
                freeze=(old.get('exempt_from') if old['status']=='exempt' else F.today()) if status=='exempt' else None
                c.execute('''UPDATE monthly_accounts SET start_date=%s,status=%s,exempt_from=%s,
                    exempt_by=CASE WHEN %s='exempt' THEN %s ELSE NULL END,
                    exempt_at=CASE WHEN %s='exempt' THEN now() ELSE NULL END WHERE student_id=%s''',
                    (anchor,status,freeze,status,actor,status,student))
                if old['status']=='exempt' and status=='regular':
                    # Initially exempt accounts have no issued fees or periods.
                    settings=F._tariffs(c)
                    c.execute("INSERT INTO monthly_fees(student_id,kind,price) VALUES(%s,'registration',%s) ON CONFLICT(student_id,kind) DO NOTHING",(student,settings['registration']))
                if status=='regular': F._due_started(c,student,{**old,'start_date':anchor,'status':status})
            F._audit(c,student,None,'account_input_cancelled' if cancel else 'account_input_corrected',actor,old,
                     {'status':status,'start_date':str(start_date),'cancelled':cancel,'waived':waived,'cash':0},reason)
            if token:
                c.execute('INSERT INTO account_status_requests(request_token,request_hash,student_id,waived,actor) VALUES(%s,%s,%s,%s,%s)',
                    (token,fingerprint,student,waived,actor))
        conn.commit();return dict(waived=waived,created=True)
    except Exception: conn.rollback(); raise
    finally: conn.close()


def change_waiver(ident, *, actor, reason, new_amount=None, on_date=None, cancel=False, expected=None):
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب التغيير وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'accounts.delete' if cancel else 'accounts.edit',actor)
            H.context(c,actor,reason)
            c.execute('SELECT student_id FROM monthly_waivers WHERE waiver_id=%s',(ident,))
            found=c.fetchone()
            if not found: raise ValueError('الإعفاء غير موجود أو ملغى.')
            student=found['student_id']
            c.execute('SELECT * FROM monthly_accounts WHERE student_id=%s FOR UPDATE',(student,))
            account=c.fetchone()
            if account['archived_at']: raise ValueError('الحساب ملغى؛ لا تغيّر الإعفاءات المرتبطة به.')
            old=R._lock(c,'monthly_waivers',ident,expected)
            if not cancel:
                amount=F.amount(new_amount)
                day=date.fromisoformat(str(on_date))
                if day>F.today(): raise ValueError('تاريخ الإعفاء لا يكون مستقبليًا.')
                kind='fee_id' if old['fee_id'] else 'period_id'
                target='monthly_fees' if old['fee_id'] else 'monthly_periods'
                c.execute(f'''SELECT price-COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
                    JOIN monthly_receipts r ON r.receipt_id=a.receipt_id WHERE a.{kind}=t.{kind} AND a.active AND r.state='active'),0)
                    -COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w WHERE w.{kind}=t.{kind} AND w.waiver_id<>%s),0) AS maximum
                    FROM {target} t WHERE {kind}=%s''',(ident,old[kind]))
                if amount>c.fetchone()['maximum']: raise ValueError('الإعفاء أكبر من المتبقي غير المدفوع لهذا الرسم.')
            c.execute('DELETE FROM monthly_waivers WHERE waiver_id=%s',(ident,))
            if not cancel:
                import json
                c.execute('''INSERT INTO monthly_waivers(student_id,fee_id,period_id,amount,effective_on,
                    request_token,request_hash,actor,reason,before_state,after_state)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING waiver_id''',
                    (student,old['fee_id'],old['period_id'],amount,day,str(uuid.uuid4()),'waiver-correction',actor,reason,
                     json.dumps(old,default=str),json.dumps({'amount':amount,'effective_on':str(day)})))
                new_id=c.fetchone()['waiver_id']
            else: new_id=None
            F._audit(c,student,None,'waiver_cancelled' if cancel else 'waiver_corrected',actor,old,{'replacement_id':new_id,'cash':0},reason)
        conn.commit(); return new_id
    except Exception: conn.rollback(); raise
    finally: conn.close()
