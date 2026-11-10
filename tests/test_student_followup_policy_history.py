"""Stored reminder preferences cannot hide real debt or expose early notices."""
from datetime import date
import json
import pytest
import monthly_finance as F
import followup_settings as S
import student_followup as SF
from tests.test_student_followup import child, entries
from tests.test_live_pages_http import browser, login, post
from tests.test_access_control import access, worker


def projection():
    return dict(account=dict(start_date=date(2026,10,8),status='regular',due_at_period_end=True),
        fees={},due_now=3000,periods=[dict(no=0,start=date(2026,10,8),end=date(2026,11,8),price=3000,paid=0)])


@pytest.mark.parametrize('stored_day',[1,5,10,20,31])
def test_actual_debt_does_not_wait_for_an_obsolete_reminder_preference(stored_day):
    p=projection();row=SF.account_item(p,date(2026,11,11),stored_day,3000)
    assert row['due_total']==row['due_monthly']==3000 and row['status']=='due'
    assert row['earliest_due']==date(2026,11,8) and row['upcoming'] is None


def test_old_policy_windows_neither_hide_debt_nor_create_unearned_paid_months():
    windows=[dict(day=31,starts=date.min,ends=date(2026,11,11))]
    row=SF.account_item(projection(),date(2026,11,11),31,3000,windows)
    assert row['due_total']==3000 and row['last_paid_month'] is None


def test_saved_reminder_preferences_never_change_real_debt_or_expose_audit(browser,monkeypatch):
    client,conn=browser;owner=login(client)
    monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    sid=child(client,owner,'2026-10-29')
    before=F.projection(conn,sid,materialize=False)
    for day in (20,5,31):
        saved=post(client,owner,'followup.settings',dict(day=day,revision=S.read(conn)['revision'],reason='PRIVATE_OLD_POLICY_REASON',confirmed=True))
        assert saved.status_code==200,saved.text
        row=entries(client,owner)[0]
        assert row['id']==sid and row['due_total']==3000 and row['upcoming'] is None
    after=F.projection(conn,sid,materialize=False)
    assert before==after
    worker(['payments.view'],name='policy_reader')
    reader=login(client,'policy_reader')
    response=post(client,reader,'followup.read',{})
    assert response.status_code==200,response.text
    body=response.json();assert body['items'][0]['due_total']==3000
    assert not body['settings']['editable']
    encoded=json.dumps(body)
    assert 'PRIVATE_OLD_POLICY_REASON' not in encoded and 'before_day' not in encoded
    assert body['items'][0]['mother_phone']=='' and body['items'][0]['photo'] is None


def test_early_preference_never_lists_a_not_yet_due_month(browser,monkeypatch):
    client,conn=browser;owner=login(client)
    monkeypatch.setattr(F,'today',lambda:date(2026,11,9))
    sid=child(client,owner,'2026-10-29')
    saved=post(client,owner,'followup.settings',dict(day=5,revision=S.read(conn)['revision'],reason='Legacy preference',confirmed=True))
    assert saved.status_code==200,saved.text
    assert entries(client,owner)==[] and F.projection(conn,sid,materialize=False)['due_now']==0
