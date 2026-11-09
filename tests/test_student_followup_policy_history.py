"""Changing reminder policy cannot hide previously eligible unpaid debt."""
from datetime import date, datetime, timezone
import json

import monthly_finance as F
import followup_settings as S
import student_followup as SF
from tests.test_student_followup import child, entries
from tests.test_live_pages_http import browser, login, post
from tests.test_access_control import access, worker


def projection(created=None):
    return dict(account=dict(start_date=date(2026,10,8),status='regular',due_at_period_end=True,
                             created_at=created), fees={},due_now=3000,
                periods=[dict(no=0,start=date(2026,10,8),end=date(2026,11,8),price=3000,paid=0),
                         dict(no=1,start=date(2026,11,8),end=date(2026,12,8),price=3000,paid=0)])


def change(before,after,day):
    return dict(before_day=before,after_day=after,changed_on=date(2026,11,day))


def test_visible_debt_stays_visible_after_later_batch_day():
    p=projection();day=date(2026,11,11)
    assert SF.account_item(p,day,20,3000) is None
    windows=SF.policy_windows([change(10,20,11)],day)
    row=SF.account_item(p,day,20,3000,windows)
    assert row['due_total']==3000 and row['status']=='due'
    assert row['reminder_on']==date(2026,11,10)


def test_previous_policy_must_really_have_reached_eligibility_before_ending():
    p=projection();day=date(2026,11,11)
    windows=SF.policy_windows([change(20,31,9)],day)
    assert SF.account_item(p,day,31,3000,windows) is None


def test_early_notice_ended_before_debt_matured_does_not_retain_visibility():
    p=projection();day=date(2026,11,8)
    windows=SF.policy_windows([change(1,31,7)],day)
    # Reminder1 anticipated due8, but policy1 ended7 before it became debt.
    assert SF.account_item(p,day,31,3000,windows) is None
    # An otherwise identical change ON the debt date retains the old notice.
    mature=SF.policy_windows([change(1,31,8)],day)
    assert SF.account_item(p,day,31,3000,mature)['due_total']==3000


def test_appearance_cannot_precede_policy_start():
    p=projection();day=date(2026,11,13)
    windows=SF.policy_windows([change(20,1,11),change(1,20,12)],day)
    # Day1 would nominally notify due8 on Nov1, but was only active Nov11–12.
    row=SF.account_item(p,day,20,3000,windows)
    assert row['reminder_on']==date(2026,11,11)


def test_old_window_cannot_claim_visibility_before_account_creation():
    p=projection(datetime(2026,11,13,9,tzinfo=timezone.utc));day=date(2026,11,14)
    windows=SF.policy_windows([change(10,20,11)],day)
    assert SF.account_item(p,day,20,3000,windows) is None


def test_future_audit_changes_do_not_create_historical_visibility():
    day=date(2026,11,11)
    assert SF.policy_windows([change(10,20,20)],day)==[]
    assert SF.account_item(projection(),day,20,3000,SF.policy_windows([change(10,20,20)],day)) is None


def test_upcoming_reminders_still_follow_current_policy_only():
    p=projection();p['account']['start_date']=date(2026,10,17);p['due_now']=0
    p['periods']=[dict(no=0,start=date(2026,10,17),end=date(2026,11,17),price=3000,paid=0)]
    day=date(2026,11,10);windows=SF.policy_windows([change(10,8,10)],day)
    assert SF.account_item(p,day,10,3000)['status']=='upcoming'
    assert SF.account_item(p,day,8,3000,windows) is None


def audit_clock(conn):
    # A deterministic database clock in this fixture's disposable schema only.
    # The real tariff update and append-only audit capture still execute.
    with conn.cursor() as c:
        c.execute('''CREATE FUNCTION followup_test_clock() RETURNS trigger AS $$
            BEGIN IF NEW.table_name='monthly_tariffs'
                AND NEW.before_state->'followup_day' IS DISTINCT FROM NEW.after_state->'followup_day'
                THEN NEW.happened_at=TIMESTAMPTZ '2026-11-11 12:00:00+00'; END IF;
                RETURN NEW; END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER followup_test_clock BEFORE INSERT ON record_changes
                FOR EACH ROW EXECUTE FUNCTION followup_test_clock()''')


def test_actual_owner_policy_change_retains_debt_without_exposing_audit_to_reader(browser,monkeypatch):
    client,conn=browser;owner=login(client)
    monkeypatch.setattr(F,'today',lambda:date(2026,11,10))
    sid=child(client,owner,'2026-10-08')
    assert entries(client,owner)[0]['due_total']==3000
    audit_clock(conn)
    monkeypatch.setattr(F,'today',lambda:date(2026,11,11))
    saved=post(client,owner,'followup.settings',dict(day=20,revision=S.read(conn)['revision'],
        reason='POLICY_HISTORY_SECRET',confirmed=True))
    assert saved.status_code==200,saved.text
    row=entries(client,owner)[0]
    assert row['id']==sid and row['due_total']==3000 and row['reminder_on']=='2026-11-10'
    worker(['payments.view'],name='policy_reader')
    reader=login(client,'policy_reader')
    response=post(client,reader,'followup.read',{})
    assert response.status_code==200,response.text
    body=response.json();assert body['items'][0]['due_total']==3000
    assert body['settings']['day']==20 and not body['settings']['editable']
    encoded=json.dumps(body)
    assert 'POLICY_HISTORY_SECRET' not in encoded and 'before_day' not in encoded
    assert body['items'][0]['mother_phone']=='' and body['items'][0]['photo'] is None
