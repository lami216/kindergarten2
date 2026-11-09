"""Scheduled reminders use the real authenticated ledger, never another debt."""
from datetime import date
import pytest
import monthly_finance as F
import access_control as A
from tests.test_live_pages_http import browser, login, post, intake
from tests.test_access_control import access, worker
import student_followup as SF


def child(c, session, anchor, **values):
    r=post(c,session,'students.create',intake(start_date=anchor,**{'mode':'pay',**values}))
    assert r.status_code==200,r.text
    return r.json()['id']


def entries(c,session):
    r=post(c,session,'followup.read',{})
    assert r.status_code==200,r.text
    return r.json()['items']


@pytest.mark.parametrize('end_day,asof,shown,state',[(8,9,False,None),(8,10,True,'due'),
    (11,9,False,None),(11,10,True,'upcoming'),(12,10,True,'upcoming'),
    (17,10,True,'upcoming'),(18,10,False,None),(18,17,False,None),(18,18,True,'due')])
def test_confirmed_batch_rule_uses_actual_debt_and_early_window(browser,monkeypatch,end_day,asof,shown,state):
    c,conn=browser;s=login(c)
    monkeypatch.setattr(F,'today',lambda:date(2026,11,asof))
    sid=child(c,s,f'2026-10-{end_day:02d}')
    before=F.projection(conn,sid,materialize=False)
    items=entries(c,s)
    assert bool(items)==shown
    if shown:
        row=items[0];assert row['id']==sid and row['status']==state
        assert row['due_total']==(3000 if state=='due' else 0)
        assert row['due_monthly']==row['due_total']
        assert row['reminder_on']==f'2026-11-{10 if end_day<=17 else end_day:02d}'
        if state=='upcoming':
            assert row['upcoming']['due_date']==f'2026-11-{end_day:02d}'
            assert row['upcoming']['remaining']==3000
    after=F.projection(conn,sid,materialize=False)
    assert before['account']==after['account'] and before['periods']==after['periods']
    assert before['due_now']==after['due_now']


def test_old_unpaid_stays_before_next_batch_and_partial_payment_is_exact(browser,monkeypatch):
    c,conn=browser;s=login(c);monkeypatch.setattr(F,'today',lambda:date(2026,11,1))
    sid=child(c,s,'2026-09-08')
    row=entries(c,s)[0];assert row['id']==sid and row['due_total']==3000 and row['reminder_on']=='2026-10-10'
    # Official allocator and waivers, including corrected/cancelled receipts,
    # remain authoritative; the reminder layer has no payment allocation code.
    import uuid
    preview=post(c,s,'payments.preview',dict(student=sid,amount='1000',date='2026-11-01'))
    assert preview.status_code==200,preview.text
    q=preview.json()
    r=post(c,s,'payments.create',dict(student=sid,amount='1000',date='2026-11-01',payer='الأم',request_token=str(uuid.uuid4()),
        confirmed=True,revision=q['revision'],tariff=q['tariff']))
    assert r.status_code==200,r.text
    row=entries(c,s)[0];assert row['due_total']==2000


def test_exempt_and_paused_only_show_old_debt_archived_never_shown(browser,monkeypatch):
    c,conn=browser;s=login(c);monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    sid=child(c,s,'2026-10-08')
    with conn.cursor() as q:
        A.require(q,'accounts.edit');q.execute("UPDATE monthly_accounts SET status='exempt',exempt_from='2026-11-09' WHERE student_id=%s",(sid,))
    row=entries(c,s)[0];assert row['due_total']==3000 and not row['upcoming'] and not row['can_pay']
    with conn.cursor() as q:
        A.require(q,'accounts.edit');q.execute("UPDATE monthly_accounts SET status='regular',departure_on='2026-11-09' WHERE student_id=%s",(sid,))
    row=entries(c,s)[0];assert row['due_total']==3000 and not row['upcoming'] and row['can_pay']
    with conn.cursor() as q:
        A.require(q,'students.delete');q.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(sid,))
    assert entries(c,s)==[]


def test_fully_prepaid_months_do_not_trigger_and_partial_future_is_not_debt(browser,monkeypatch):
    c,conn=browser;s=login(c);monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    full=child(c,s,'2026-10-12',amount='18000',mode='pay')
    partial=child(c,s,'2026-10-11',amount='1000',mode='pay')
    rows=entries(c,s);assert [r['id'] for r in rows]==[partial]
    assert rows[0]['due_total']==0 and rows[0]['upcoming']['remaining']==2000
    assert F.projection(conn,full,materialize=False)['cash_paid']==18000


def test_registration_and_gilet_debt_are_scheduled_without_double_count(browser,monkeypatch):
    c,conn=browser;s=login(c);monkeypatch.setattr(F,'today',lambda:date(2026,11,9))
    sid=child(c,s,'2026-11-08',registration=True,gilet=True)
    assert entries(c,s)==[]
    monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    row=entries(c,s)[0];assert row['due_fees']==3000 and row['due_monthly']==0 and row['due_total']==3000


def test_permissions_block_debt_leaks_and_limit_contact_data(browser,monkeypatch):
    c,conn=browser;s=login(c);monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    sid=child(c,s,'2026-10-08')
    worker(['students.view'],name='student_reader')
    user=login(c,'student_reader');assert post(c,user,'followup.read',{}).status_code==403
    s=login(c);worker(['payments.view'],name='cash_reader')
    user=login(c,'cash_reader');row=entries(c,user)[0]
    assert row['id']==sid and row['due_total']==3000
    assert row['mother_phone']=='' and row['photo'] is None and not row['can_profile'] and not row['can_pay']


def test_waived_or_zero_priced_obligations_never_create_reminders():
    day=date(2026,11,10)
    account=dict(start_date=date(2026,10,8),status='regular',due_at_period_end=True)
    p=dict(account=account,fees={},periods=[dict(no=0,start=date(2026,10,8),end=date(2026,11,8),price=3000,paid=0,waived=3000)],due_now=0)
    assert SF.account_item(p,day,10,0) is None
