"""Audited corrections to subscription inputs and explicit noncash waivers."""
import uuid
from datetime import date
import db
import monthly_finance as F
import record_history as H
import records as R


def change_account(student, *, actor, reason, start_date=None, status=None, cancel=False, expected=None):
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب التغيير وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            H.context(c,actor,reason)
            old=R._lock(c,'monthly_accounts',student,expected)
            if old['archived_at']: raise ValueError('الحساب ملغى بالفعل.')
            if cancel:
                import student_debt as D
                if old['status']=='regular': F._due_started(c,student,old)
                cutoff=min(F.today(),old['exempt_from']) if old['status']=='exempt' and old.get('exempt_from') else F.today()
                if any(r['remaining']>0 for r in D._debt(c,student,cutoff)):
                    raise ValueError('سدّد أو ألغِ الدين المتبقي أولًا؛ الدفعات والإعفاءات متاحة في إدارة السجلات.')
                c.execute('UPDATE monthly_accounts SET archived_at=now(),archived_by=%s,departure_on=%s WHERE student_id=%s',(actor,F.today(),student))
            else:
                anchor=date.fromisoformat(str(start_date))
                if anchor>F.today() or anchor<date(1990,1,1): raise ValueError('اختر تاريخ بداية بين 1990 واليوم.')
                if status not in ('regular','exempt'): raise ValueError('اختر حالة الرسوم.')
                if anchor!=old['start_date']:
                    c.execute("SELECT 1 FROM monthly_allocations a JOIN monthly_receipts r ON r.receipt_id=a.receipt_id WHERE r.student_id=%s AND a.active AND r.state='active' UNION ALL SELECT 1 FROM monthly_waivers WHERE student_id=%s LIMIT 1",(student,student))
                    if c.fetchone(): raise ValueError('لتصحيح البداية، ألغِ الوصولات والإعفاءات المرتبطة أولًا ثم أعد تسجيل الصحيح؛ لا يُعاد تفسير دفعات قديمة بصمت.')
                    c.execute('SELECT period_id,period_no FROM monthly_periods WHERE student_id=%s ORDER BY period_no FOR UPDATE',(student,))
                    for period in c.fetchall():
                        c.execute('UPDATE monthly_periods SET starts=%s,ends=%s WHERE period_id=%s',
                                  (F.anniversary(anchor,period['period_no']),F.anniversary(anchor,period['period_no']+1),period['period_id']))
                if old['status']=='regular' and status=='exempt':
                    import student_debt as D
                    F._due_started(c,student,{**old,'start_date':anchor})
                    if any(item['remaining']>0 for item in D._debt(c,student,F.today())):
                        raise ValueError('يوجد دين سابق؛ سدّده أو ألغِه صراحةً من ملف الطالب قبل تغيير حالة الإعفاء.')
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
                     {'status':status,'start_date':str(start_date),'cancelled':cancel},reason)
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: conn.close()


def change_waiver(ident, *, actor, reason, new_amount=None, on_date=None, cancel=False, expected=None):
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب التغيير وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
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
