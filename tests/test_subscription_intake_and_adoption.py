"""Intake dates, individual audited correction and account summaries."""
from datetime import timedelta
import uuid
import pytest

import monthly_finance as F
from tests.test_access_control import access,PASSWORD
from tests.test_live_pages_http import browser,intake,login,post


def snapshot_student(client,sid):return next(row for row in client.get('/api/snapshot').json()['students'] if row['id']==sid)


def test_intake_selected_start_and_current_cash_date_are_distinct(browser):
    client,conn=browser;session=login(client)
    start=F.today()-timedelta(days=45)
    r=post(client,session,'students.create',intake(start_date=str(start),mode='pay',registration=True,gilet=False,amount='19000'))
    assert r.status_code==200,r.text
    sid=r.json()['id'];student=snapshot_student(client,sid)
    assert student['start']==student['registered_on']==str(start)
    assert student['account']['full']==6 and student['account']['paid']==19000
    assert student['account']['paid_through']==str(F.anniversary(start,6)-timedelta(days=1))
    assert student['account']['next_unpaid']==str(F.anniversary(start,6))
    assert student['account']['fee_details']['registration']['paid']==1000
    with conn.cursor() as c:
        c.execute('SELECT received_on FROM monthly_receipts WHERE student_id=%s',(sid,))
        assert c.fetchone()['received_on']==F.today()
    result=post(client,session,'reports.finance',dict(start=str(start),end=str(start)))
    assert result.status_code==200,result.text
    assert result.json()['school']['new_count']==1 and result.json()['summary']['income']==0


@pytest.mark.parametrize('value',['', '2026-02-30','1990-01-01','2999-01-01'])
def test_bad_intake_start_is_atomic(browser,value):
    client,conn=browser;session=login(client)
    response=post(client,session,'students.create',intake(name='Invalid date must not save',start_date=value,mode='pay',amount='1000',registration=True))
    assert response.status_code==422,response.text
    with conn.cursor() as c:
        for table in ('students','parents','monthly_accounts','monthly_receipts'):
            c.execute('SELECT COUNT(*) AS n FROM '+table);assert c.fetchone()['n']==0


def test_default_date_and_profile_parent_edit_revision_still_work(browser):
    client,conn=browser;session=login(client)
    response=post(client,session,'students.create',intake())
    assert response.status_code==200,response.text
    sid=response.json()['id'];s=snapshot_student(client,sid)
    assert s['start']==str(F.today())
    edit=post(client,session,'students.edit',dict(id=sid,revision=s['revision'],parent_revision=s['parent_revision'],reason='Address only',values=dict(address='Correct address')))
    assert edit.status_code==200,edit.text


def test_read_only_profile_finance_is_permission_scoped(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(start_date=str(F.today()),mode='pay',registration=False,gilet=False,amount='1500')).json()['id']
    s=snapshot_student(client,sid)
    assert s['account']['full']==0 and s['account']['partial_period']['remaining']==1500
    import access_control as A
    A.save_user(employee_name='Student viewer',name='dates_viewer',password=PASSWORD,permissions=['students.view'])
    login(client,'dates_viewer');s=snapshot_student(client,sid)
    assert s['registered_on']==str(F.today()) and s['account'] is None and 'start' not in s



def correct(client,session,sid,student,new_start,**extra):
    meta=student['subscription_edit']
    return post(client,session,'students.edit',dict(id=sid,revision=student['revision'],
        account_revision=meta['revision'],ledger_revision=meta['ledger_revision'],
        parent_revision=student['parent_revision'],reason='Correct enrollment date',
        values=dict(start_date=str(new_start),**extra)))


def test_in_file_date_correction_preserves_cash_prices_and_original_receipts(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=True,amount='7000')).json()['id']
    student=snapshot_student(client,sid);new=F.today()-timedelta(days=100)
    with conn.cursor() as c:
        c.execute('SELECT * FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id',(sid,));receipts=[dict(r) for r in c.fetchall()]
        c.execute('SELECT * FROM monthly_allocation_snapshots ORDER BY allocation_id');frozen=[dict(r) for r in c.fetchall()]
        c.execute('SELECT period_id,price FROM monthly_periods WHERE student_id=%s',(sid,));prices={r['period_id']:r['price'] for r in c.fetchall()}
    saved=correct(client,session,sid,student,new,address='Corrected with date')
    assert saved.status_code==200,saved.text
    s=snapshot_student(client,sid)
    assert s['registered_on']==s['start']==str(new) and s['address']=='Corrected with date'
    assert s['account']['paid']==7000 and s['account']['due']>student['account']['due']
    with conn.cursor() as c:
        c.execute('SELECT * FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id',(sid,));assert [dict(r) for r in c.fetchall()]==receipts
        c.execute('SELECT * FROM monthly_allocation_snapshots ORDER BY allocation_id');assert [dict(r) for r in c.fetchall()]==frozen
        c.execute('SELECT period_id,price FROM monthly_periods WHERE student_id=%s',(sid,));after={r['period_id']:r['price'] for r in c.fetchall()}
        assert all(after[key]==price for key,price in prices.items())
        c.execute("SELECT actor,reason,before_state,after_state FROM record_changes WHERE table_name='monthly_accounts' AND record_key=%s ORDER BY change_id DESC LIMIT 1",(sid,))
        audit=c.fetchone();assert audit['actor']=='owner' and audit['reason']=='Correct enrollment date'
        assert audit['before_state']['start_date']==str(F.today()) and audit['after_state']['start_date']==str(new)
    report=post(client,session,'reports.finance',dict(start=str(new),end=str(new))).json()
    assert report['school']['new_count']==1 and report['summary']['income']==0
    # A corrected enrollment date invalidates a second old editor and payment preview.
    rejected=correct(client,session,sid,student,new+timedelta(days=1))
    assert rejected.status_code==422


def test_old_editor_after_payment_is_rejected_atomically(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',amount='3000')).json()['id']
    student=snapshot_student(client,sid)
    F.take_payment(sid,100,actor='owner')
    response=correct(client,session,sid,student,F.today()-timedelta(days=10),address='Must not persist')
    assert response.status_code==422,response.text
    now=snapshot_student(client,sid)
    assert now['start']==str(F.today()) and now['address']==student['address']


def test_date_only_edit_rejects_old_editors_and_old_payment_previews(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',amount='3000')).json()['id']
    student=snapshot_student(client,sid)
    preview=post(client,session,'payments.preview',dict(student=sid,amount='500',date=str(F.today()))).json()
    saved=correct(client,session,sid,student,F.today()-timedelta(days=10))
    assert saved.status_code==200,saved.text
    assert snapshot_student(client,sid)['revision']==student['revision']
    stale=correct(client,session,sid,student,F.today()-timedelta(days=20))
    assert stale.status_code==422
    payment=post(client,session,'payments.create',dict(student=sid,amount='500',date=str(F.today()),confirmed=True,
        revision=preview['revision'],tariff=preview['tariff'],request_token=str(uuid.uuid4())))
    assert payment.status_code==422


def test_date_correction_requires_account_permission_but_normal_edits_do_not(browser):
    import access_control as A
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake()).json()['id'];student=snapshot_student(client,sid)
    A.save_user(employee_name='Student editor',name='student_editor',password=PASSWORD,permissions=['students.view','students.edit'])
    worker=login(client,'student_editor');s=snapshot_student(client,sid)
    assert 'subscription_edit' not in s and s['account'] is None
    denied=correct(client,worker,sid,student,F.today()-timedelta(days=10))
    assert denied.status_code==403
    good=post(client,worker,'students.edit',dict(id=sid,revision=s['revision'],reason='Address only',values=dict(address='Allowed')))
    assert good.status_code==200,good.text
    session=login(client)
    A.save_user(employee_name='Subscription editor',name='date_editor',password=PASSWORD,permissions=['students.view','students.edit','accounts.edit'])
    editor=login(client,'date_editor');s=snapshot_student(client,sid)
    assert s['subscription_edit']['start']==str(F.today())
    saved=correct(client,editor,sid,s,F.today()-timedelta(days=1))
    assert saved.status_code==200,saved.text


def test_invalid_correction_rolls_back_student_and_family(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake()).json()['id'];s=snapshot_student(client,sid)
    response=correct(client,session,sid,s,'2999-01-01',address='Do not save',motherPhone='99887766')
    assert response.status_code==422
    now=snapshot_student(client,sid)
    assert now['address']==s['address'] and now['motherPhone']==s['motherPhone']


def test_receipt_date_correction_after_enrollment_edit_keeps_anchor_and_months(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=True,amount='19000')).json()['id']
    s=snapshot_student(client,sid);anchor=F.today()-timedelta(days=20)
    assert correct(client,session,sid,s,anchor).status_code==200
    state=client.get('/api/snapshot').json();receipt=next(r for r in state['receipts'] if r['student']==sid)
    with conn.cursor() as c:
        c.execute('SELECT starts,ends,price FROM monthly_periods WHERE student_id=%s ORDER BY period_no',(sid,));before=[dict(r) for r in c.fetchall()]
    day=F.today()-timedelta(days=2)
    changed=post(client,session,'records.change',dict(type='receipts',id=receipt['id'],mode='edit',reason='Correct payment date',
        revision=receipt['revision'],confirmed=True,request_token=str(uuid.uuid4()),values=dict(amount='19000',date=str(day))))
    assert changed.status_code==200,changed.text
    now=snapshot_student(client,sid)
    assert now['start']==str(anchor) and now['account']['full']==6 and now['account']['paid']==19000
    with conn.cursor() as c:
        c.execute('SELECT starts,ends,price FROM monthly_periods WHERE student_id=%s ORDER BY period_no',(sid,));assert [dict(r) for r in c.fetchall()]==before
        c.execute('SELECT received_on FROM monthly_receipts WHERE receipt_id=%s',(changed.json()['id'],));assert c.fetchone()['received_on']==day
        c.execute("SELECT before_state,after_state FROM monthly_audit WHERE student_id=%s AND action='receipt_corrected'",(sid,));audit=c.fetchone()
        assert audit['before_state']['received_on']==str(F.today()) and audit['after_state']['received_on']==str(day)
    state=client.get('/api/snapshot').json();current=next(r for r in state['receipts'] if r['id']==changed.json()['id'])
    stale=post(client,session,'records.change',dict(type='receipts',id=receipt['id'],mode='edit',reason='Stale version',revision=receipt['revision'],
        confirmed=True,request_token=str(uuid.uuid4()),values=dict(amount='19000',date=str(F.today()))))
    assert stale.status_code==422
    assert current['date']==str(day)


@pytest.mark.parametrize('status',['exempt','archived'])
def test_historical_receipt_date_can_be_corrected_after_exemption_or_archive(browser,status):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=True,amount='19000')).json()['id']
    s=snapshot_student(client,sid)
    if status=='exempt':
        from account_records import change_account
        change_account(sid,actor='owner',reason='No further fees',start_date=s['start'],status='exempt',expected=s['account_revision'])
    else:
        import records as R
        R.cancel('students',sid,actor='owner',reason='Departure',expected=s['revision'])
    state=client.get('/api/snapshot').json();receipt=next(r for r in state['receipts'] if r['student']==sid)
    day=F.today()-timedelta(days=1)
    changed=post(client,session,'records.change',dict(type='receipts',id=receipt['id'],mode='edit',reason='Correct old cash date',
        revision=receipt['revision'],confirmed=True,request_token=str(uuid.uuid4()),values=dict(amount='19000',date=str(day))))
    assert changed.status_code==200,changed.text
    now=snapshot_student(client,sid)
    assert now['account']['paid']==19000 and now['start']==s['start']
    assert now['exempt']==(status=='exempt') and now['cancelled']==(status=='archived')
    assert now['account']['full']==6
