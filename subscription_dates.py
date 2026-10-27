"""Intake dates, audited in-file corrections and student account summaries."""
from datetime import date

import access_control as A
import monthly_finance as F
import record_history as H


def registration_sql(student='s', account='a'):
    return f'''CASE WHEN EXISTS(SELECT 1 FROM monthly_audit m WHERE m.student_id={student}.student_id
        AND m.action IN ('subscription_start_selected','registration_start_corrected','registration_start_adopted'))
        THEN {account}.start_date ELSE COALESCE((SELECT MIN(r.registration_date) FROM registrations r
        WHERE r.student_id={student}.student_id),{student}.created_at::date) END'''


def intake_date(value, birth):
    if value is None:
        return F.today()
    try:
        if not isinstance(value,str) or len(value)!=10: raise ValueError()
        result=date.fromisoformat(value)
    except (ValueError,TypeError):
        raise ValueError('أدخل تاريخ بداية اشتراك صحيحًا.') from None
    if result<date(1990,1,1) or result>F.today() or birth is not None and result<birth:
        raise ValueError('بداية الاشتراك يجب أن تكون بين تاريخ ميلاد الطفل واليوم.')
    return result


def profile_summary(p):
    account=p['account'];open_account=account['status']=='regular' and not account.get('departure_on')
    cutoff=min(F.today(),account.get('departure_on') or F.today(),account.get('exempt_from') or F.today())
    outstanding=next((row for row in p['periods'] if row['paid']+row.get('waived',0)<row['price'] and
        (open_account or (row['end'] if account.get('due_at_period_end') else row['start'])<=cutoff)),None)
    index=0
    for row in p['periods']:
        if row['no']!=index or row['paid']+row.get('waived',0)<row['price']:break
        index+=1
    next_start=outstanding['start'] if outstanding else F.anniversary(account['start_date'],index) if open_account else None
    next_due=(outstanding['end'] if account.get('due_at_period_end') else outstanding['start']) if outstanding else F.anniversary(account['start_date'],index+int(bool(account.get('due_at_period_end')))) if open_account else None
    return dict(paid_through=p['paid_through'],next_unpaid=next_start,next_due=next_due,
        partial_period=dict(start=outstanding['start'],end=outstanding['end'],paid=outstanding['paid'],
            remaining=outstanding['price']-outstanding['paid']-outstanding.get('waived',0)) if outstanding and outstanding['paid'] else None,
        fee_details={key:{**value,'remaining':max(0,value['price']-value['paid']-value.get('waived',0))} for key,value in p['fees'].items()})



def correct_start(c,student,value,*,actor,reason,birth,expected,expected_ledger):
    """Correct one anchor inside the caller's student/account transaction.

    Period numbers, stored prices, cash and frozen receipt copies retain their
    identities. The audit marker also invalidates open payment previews.
    """
    import records as R
    A.require(c,'accounts.edit')
    old=R._lock(c,'monthly_accounts',student,expected)
    if old['archived_at']:raise ValueError('الحساب ملغى بالفعل.')
    if type(expected_ledger) is not int:
        raise ValueError('تغيّر السجل منذ فتحه؛ حدّث الصفحة وراجع البيانات الجديدة قبل الحفظ.')
    F._assert_receipt_revision(c,student,expected_ledger)
    anchor=intake_date(value,birth)
    if old.get('departure_on') and anchor>old['departure_on']:
        raise ValueError('بداية الاشتراك لا تكون بعد تاريخ مغادرة الطالب.')
    if anchor==old['start_date']:return False
    H.context(c,actor,reason)
    c.execute('SELECT period_id,period_no,starts,ends,price FROM monthly_periods WHERE student_id=%s ORDER BY period_no FOR UPDATE',(student,))
    periods=[dict(row) for row in c.fetchall()]
    for period in periods:
        c.execute('UPDATE monthly_periods SET starts=%s,ends=%s WHERE period_id=%s',
                  (F.anniversary(anchor,period['period_no']),F.anniversary(anchor,period['period_no']+1),period['period_id']))
    c.execute('UPDATE monthly_accounts SET start_date=%s WHERE student_id=%s',(anchor,student))
    F._due_started(c,student,{**old,'start_date':anchor})
    F._audit(c,student,None,'registration_start_corrected',actor,
             dict(start_date=old['start_date'],periods=periods),
             dict(start_date=anchor,cash_unchanged=True,receipt_snapshots_unchanged=True),reason)
    return True
