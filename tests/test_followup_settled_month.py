"""Due-only follow-up shows actual fully cash-funded months, not waivers."""
from copy import deepcopy
from datetime import date
import uuid

import pytest

import access_control as A
import followup_settings as S
import monthly_finance as F
import receipt_history as H
import student_followup as SF
from tests.test_access_control import access
from tests.test_live_pages_http import browser, intake, login, post


ANCHOR = date(2026, 8, 8)
TODAY = date(2026, 11, 10)


def period(no, *, price=3000, paid=0, waived=0):
    return dict(no=no, start=F.anniversary(ANCHOR,no), end=F.anniversary(ANCHOR,no+1),
                price=price, paid=paid, waived=waived)


@pytest.mark.parametrize('periods,fees,expected', [
    pytest.param([], {'registration':dict(price=1000,paid=0)}, None, id='unpaid-registration-only'),
    pytest.param([period(2)], {'registration':dict(price=1000,paid=1000)}, None, id='registration-cash-is-not-month'),
    pytest.param([period(0,paid=1000),period(2)], {}, None, id='partial-month'),
    pytest.param([period(0,waived=3000),period(2)], {}, None, id='fully-waived-month'),
    pytest.param([period(0,paid=1000,waived=2000),period(2)], {}, None, id='cash-and-waiver-is-not-fully-paid'),
    pytest.param([period(0,price=0),period(2)], {}, None, id='zero-priced-month'),
    pytest.param([period(0,paid=3000),period(2)], {}, date(2026,8,8), id='one-fully-paid-month'),
    pytest.param([period(0,paid=3000),period(1,paid=3000),period(2)], {}, date(2026,9,8), id='two-fully-paid-months'),
    pytest.param([period(5,paid=3000),period(2),period(0,paid=3000)], {}, date(2027,1,8), id='latest-paid-start-even-if-future-or-unsorted'),
])
def test_last_paid_month_counts_only_positive_price_fully_cash_funded_periods(periods,fees,expected):
    account=dict(start_date=ANCHOR,status='regular',due_at_period_end=True,
                 calendar_due_day=10,calendar_due_from=None)
    due=sum(max(0,p['price']-p['paid']-p.get('waived',0)) for p in periods
            if F.period_due(account,p,TODAY)<=TODAY)
    due+=sum(max(0,f['price']-f['paid']) for f in fees.values())
    projection=dict(account=account,periods=periods,fees=fees,due_now=due)
    original=deepcopy(projection)
    row=SF.account_item(projection,TODAY,10,3000)
    assert row is not None and row['status']=='due' and row['due_total']==due
    assert row['last_paid_month']==expected
    assert row['upcoming'] is None
    assert projection==original  # This display read never edits the ledger.


@pytest.mark.parametrize('due', [0,-1])
def test_upcoming_window_never_emits_an_account_without_official_debt(due):
    account=dict(start_date=date(2026,10,8),status='regular',due_at_period_end=True,
                 calendar_due_day=10,calendar_due_from=None)
    p=dict(no=0,start=date(2026,10,8),end=date(2026,11,8),price=3000,paid=0)
    projection=dict(account=account,periods=[p],fees={},due_now=due)
    assert SF.reminder_date(date(2026,11,10),5)==date(2026,11,5)
    assert SF.account_item(projection,date(2026,11,5),5,3000) is None


def enroll(client,session,anchor,**values):
    response=post(client,session,'students.create',intake(start_date=anchor,**{'mode':'pay',**values}))
    assert response.status_code==200,response.text
    return response.json()['id']


def items(client,session):
    response=post(client,session,'followup.read',{})
    assert response.status_code==200,response.text
    return {row['id']:row for row in response.json()['items']}


def freeze(monkeypatch,day):
    monkeypatch.setattr(F,'today',lambda:day)
    monkeypatch.setattr(H,'today',lambda:day)


def test_http_fee_only_and_registration_payment_never_claim_a_paid_month(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch,TODAY)
    fee_only=enroll(client,session,'2026-11-08',registration=True,amount='0')
    registration_paid=enroll(client,session,'2026-10-08',registration=True,amount='1000')
    rows=items(client,session)
    assert set(rows)=={fee_only,registration_paid}
    assert rows[fee_only]['due_total']==1000 and rows[fee_only]['due_monthly']==0
    assert rows[registration_paid]['due_total']==3000
    assert all(row['last_paid_month'] is None for row in rows.values())
    assert F.projection(conn,registration_paid)['cash_paid']==1000


def test_http_correcting_and_cancelling_receipt_updates_last_fully_paid_month(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch,TODAY)
    sid=enroll(client,session,'2026-08-08',amount='6000')
    row=items(client,session)[sid]
    assert row['last_paid_month']=='2026-09-08' and row['due_total']==3000
    original=F.projection(conn,sid)['receipts'][0]['receipt_id']
    impact=H.receipt_impact(conn,original,new_amount=4000)
    corrected,_=F.correct_receipt(original,4000,'تصحيح مدفوع الشهر',actor='owner',
        token=str(uuid.uuid4()),expected_revision=impact['revision'])
    row=items(client,session)[sid]
    assert row['last_paid_month']=='2026-08-08' and row['due_total']==5000
    impact=H.receipt_impact(conn,corrected,new_amount=1000)
    partial,_=F.correct_receipt(corrected,1000,'تصحيح إلى شهر غير مكتمل',actor='owner',
        token=str(uuid.uuid4()),expected_revision=impact['revision'])
    row=items(client,session)[sid]
    assert row['last_paid_month'] is None and row['due_total']==8000
    F.cancel_receipt(partial,'إلغاء إدخال قبض خاطئ',actor='owner',token=str(uuid.uuid4()),
                     expected_revision=F.receipt_revision(conn,sid))
    row=items(client,session)[sid]
    assert row['last_paid_month'] is None and row['due_total']==9000
    assert F.projection(conn,sid)['cash_paid']==0


def test_http_genuine_future_prepaid_month_is_reported_without_calling_it_paid_through(browser,monkeypatch):
    from account_records import change_account
    client,conn=browser;session=login(client);freeze(monkeypatch,TODAY)
    sid=enroll(client,session,'2026-10-08',amount='18000')
    assert sid not in items(client,session)
    # Explicit reactivation adds the ordinary registration fee while existing
    # advance tuition allocations remain intact. This yields genuine fee debt
    # alongside future fully paid months, without inventing any financial rows.
    change_account(sid,status='exempt',actor='owner',reason='إعفاء موثق')
    change_account(sid,status='regular',actor='owner',reason='استئناف الاشتراك المدفوع')
    row=items(client,session)[sid]
    assert row['due_total']==row['due_fees']==1000 and row['due_monthly']==0
    assert row['last_paid_month']=='2027-03-08'
    p=F.projection(conn,sid)
    assert p['cash_paid']==18000 and p['paid_periods']==6
    assert row['last_paid_month']!=p['paid_through'].isoformat()


def test_http_configured_early_window_excludes_upcoming_only_accounts(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch,date(2026,11,5))
    sid=enroll(client,session,'2026-10-08')
    fee=enroll(client,session,'2026-11-04',registration=True)
    setting=S.read(conn)
    S.save(conn,dict(day=5,revision=setting['revision'],confirmed=True,reason='تذكير مبكر تجريبي'))
    before=F.projection(conn,sid)
    rows=items(client,session)
    assert set(rows)=={fee}  # Actual fee debt stays; a future month does not.
    assert rows[fee]['due_total']==1000 and rows[fee]['last_paid_month'] is None
    assert F.projection(conn,sid)['due_now']==before['due_now']==0
    freeze(monkeypatch,TODAY)
    rows=items(client,session)
    assert sid in rows and rows[sid]['due_total']==3000
    assert rows[sid]['last_paid_month'] is None and rows[sid]['upcoming'] is None
