"""Calendar-month collection deadlines reconcile every public financial read."""
from datetime import date, timedelta
from io import BytesIO
import uuid

import pytest
from pypdf import PdfReader

import access_control as A
import monthly_finance as F
import receipt_history as H
import schema_migrations as M
import student_debt as D
from tests.test_access_control import access
from tests.test_live_pages_http import browser, intake, login, post


def on(monkeypatch, day):
    monkeypatch.setattr(F, 'today', lambda: day)
    monkeypatch.setattr(H, 'today', lambda: day)


def enroll(client, session, anchor, **values):
    payload = intake(start_date=str(anchor), **{'mode':'pay', 'registration':False,
        'gilet':False, 'amount':'0', **values})
    result = post(client, session, 'students.create', payload)
    assert result.status_code == 200, result.text
    return result.json()['id']


def student(client, sid):
    response = client.get('/api/snapshot')
    assert response.status_code == 200, response.text
    return next(s for s in response.json()['students'] if s['id'] == sid)


def followup(client, session):
    response = post(client, session, 'followup.read', {})
    assert response.status_code == 200, response.text
    return response.json()['items']


def pay(client, session, sid, amount):
    payload = dict(student=sid, amount=str(amount), date=str(F.today()), payer='ولي الأمر')
    preview = post(client, session, 'payments.preview', payload)
    assert preview.status_code == 200, preview.text
    q = preview.json()
    saved = post(client, session, 'payments.create', {**payload, 'confirmed':True,
        'revision':q['revision'], 'tariff':q['tariff'], 'request_token':str(uuid.uuid4())})
    assert saved.status_code == 200, saved.text
    return saved.json()['id']


def records(conn, table, order='1'):
    with conn.cursor() as c:
        c.execute('SELECT * FROM '+table+' ORDER BY '+order)
        return [dict(r) for r in c.fetchall()]


@pytest.mark.parametrize('anchor_day', [1, 8, 10, 11, 17, 18, 29, 31])
def test_every_october_live_enrollee_first_owes_on_november_tenth(browser, monkeypatch, anchor_day):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 9))
    anchor = date(2026, 10, anchor_day)
    sid = enroll(client, session, anchor)
    before = F.projection(conn, sid)
    assert before['account']['calendar_due_day'] == 10
    assert before['account']['calendar_due_from'] is None
    assert before['due_now'] == 0
    assert before['next_due'] == date(2026, 11, 10)
    assert followup(client, session) == []
    p0 = before['periods'][0]
    assert (p0['start'], p0['end']) == (anchor, F.anniversary(anchor, 1))
    on(monkeypatch, date(2026, 11, 10))
    current = F.projection(conn, sid)
    assert current['due_now'] == 3000
    assert current['periods'][0]['due_date'] == date(2026, 11, 10)
    visible = followup(client, session)
    assert len(visible) == 1 and visible[0]['id'] == sid
    assert visible[0]['status'] == 'due' and visible[0]['due_total'] == 3000
    assert visible[0]['earliest_due'] == '2026-11-10'
    on(monkeypatch, date(2026, 12, 9))
    assert F.projection(conn, sid)['due_now'] == 3000
    on(monkeypatch, date(2026, 12, 10))
    assert F.projection(conn, sid)['due_now'] == 6000
    assert F.projection(conn, sid)['cash_paid'] == 0
    assert not records(conn, 'monthly_receipts')


def test_single_bulk_overview_period_reports_file_and_followup_have_identical_debt(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 10))
    ids = [enroll(client, session, date(2026, 10, d), name='تقويم '+str(d))
           for d in (1, 8, 10, 11, 17, 18, 29, 31)]
    bulk = F.projections(conn)
    assert set(bulk) == set(ids)
    assert sum(p['due_now'] for p in bulk.values()) == 24000
    for sid in ids:
        assert F.projection(conn, sid, materialize=False)['due_now'] == bulk[sid]['due_now'] == 3000
        row = student(client, sid)
        assert row['account']['due'] == 3000 and row['account']['next_due'] == '2026-11-10'
    overview = F.financial_overview(conn, materialize=False)
    report = F.financial_report(conn, date(2026, 11, 1), date(2026, 11, 10), materialize=False)
    assert overview['due_now'] == report['due_now'] == 24000
    live = post(client, session, 'reports.finance', dict(start='2026-11-01', end='2026-11-10'))
    assert live.status_code == 200, live.text
    assert live.json()['debt']['students_total'] == 24000
    assert sum(r['amount'] for r in live.json()['debt']['students']) == 24000
    assert sum(r['due_total'] for r in followup(client, session)) == 24000
    # The prior day is not backfilled with a debt merely because today's
    # public snapshot has already materialized the same service periods.
    before = post(client, session, 'reports.finance', dict(start='2026-11-01', end='2026-11-09'))
    assert before.status_code == 200, before.text
    assert before.json()['debt']['students_total'] == 0


def test_partial_prepaid_and_selected_fees_remain_exact(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 9))
    partial = enroll(client, session, date(2026, 10, 29), amount='1000')
    prepaid = enroll(client, session, date(2026, 10, 31), amount='18000')
    fees = enroll(client, session, date(2026, 10, 29), registration=True, gilet=True)
    assert F.projection(conn, partial)['due_now'] == 0
    assert F.projection(conn, prepaid)['due_now'] == 0
    assert F.projection(conn, fees)['due_now'] == 3000  # Immediate nonmonthly fees unchanged.
    on(monkeypatch, date(2026, 11, 10))
    assert F.projection(conn, partial)['due_now'] == 2000
    assert F.projection(conn, prepaid)['due_now'] == 0
    assert F.projection(conn, fees)['due_now'] == 6000
    assert F.projection(conn, prepaid)['paid_periods'] == 6
    on(monkeypatch, date(2027, 4, 10))
    assert F.projection(conn, prepaid)['due_now'] == 0
    on(monkeypatch, date(2027, 5, 9))
    assert F.projection(conn, prepaid)['due_now'] == 0
    on(monkeypatch, date(2027, 5, 10))
    assert F.projection(conn, prepaid)['due_now'] == 3000
    assert F.projection(conn, prepaid)['cash_paid'] == 18000


def test_calendar_debt_is_independent_from_reminder_settings_and_client_payload(browser, monkeypatch):
    import followup_settings as S
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 10))
    sid = enroll(client, session, date(2026, 10, 29), calendar_due_day=31, calendar_due_from='2999-01-01')
    initial = F.projection(conn, sid)
    assert initial['account']['calendar_due_day'] == 10 and initial['account']['calendar_due_from'] is None
    for day in (20, 1, 10):
        setting = S.read(conn)
        S.save(conn, dict(day=day, revision=setting['revision'], reason='موعد متابعة فقط', confirmed=True))
        after = F.projection(conn, sid)
        assert after['due_now'] == 3000 and after['periods'] == initial['periods']


def test_monthly_waiver_and_archive_guard_agree_after_the_tenth(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 10))
    sid = enroll(client, session, date(2026, 10, 29))
    current = student(client, sid)
    archive = dict(type='students', id=sid, mode='cancel', reason='اختبار الأرشفة', confirmed=True,
                   revision=current['revision'], request_token=str(uuid.uuid4()))
    rejected = post(client, session, 'records.change', archive)
    assert rejected.status_code == 422, rejected.text
    assert not student(client, sid)['cancelled']
    waived = post(client, session, 'students.waive', dict(student=sid, revision=current['ledger_revision'],
        due=3000, reason='إسقاط غير نقدي موثق', confirmed=True, request_token=str(uuid.uuid4())))
    assert waived.status_code == 200 and waived.json()['waived'] == 3000, waived.text
    assert F.projection(conn, sid)['due_now'] == 0 and F.projection(conn, sid)['cash_paid'] == 0
    assert not records(conn, 'monthly_receipts')
    archive['revision'] = student(client, sid)['revision']
    archive['request_token'] = str(uuid.uuid4())
    saved = post(client, session, 'records.change', archive)
    assert saved.status_code == 200, saved.text
    assert student(client, sid)['cancelled'] and followup(client, session) == []


def test_receipt_correction_preview_matches_commit_and_cancellation(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 10))
    sid = enroll(client, session, date(2026, 10, 29))
    rid = pay(client, session, sid, 3000)
    assert F.projection(conn, sid)['due_now'] == 0
    impact = H.receipt_impact(conn, rid, new_amount=1000)
    assert impact['currently_due'] == 0 and impact['projected_due'] == 2000
    corrected, _ = F.correct_receipt(rid, 1000, 'تصحيح مبلغ الاختبار', actor='owner',
        token=str(uuid.uuid4()), expected_revision=impact['revision'])
    assert F.projection(conn, sid)['due_now'] == impact['projected_due']
    cancel_revision = F.receipt_revision(conn, sid)
    F.cancel_receipt(corrected, 'إلغاء إدخال الاختبار', actor='owner', token=str(uuid.uuid4()),
                     expected_revision=cancel_revision)
    assert F.projection(conn, sid)['due_now'] == 3000
    assert F.projection(conn, sid)['cash_paid'] == 0


def test_correcting_anchor_keeps_frozen_receipt_text_prices_and_cash(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026, 11, 10))
    sid = enroll(client, session, date(2026, 10, 29), amount='6000')
    s = student(client, sid)
    receipts = records(conn, 'monthly_receipts')
    frozen = records(conn, 'monthly_allocation_snapshots')
    allocations = records(conn, 'monthly_allocations')
    rid = receipts[0]['receipt_id']
    before_pdf = client.get('/api/receipt/'+str(rid))
    assert before_pdf.status_code == 200
    before_text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(before_pdf.content)).pages)
    with conn.cursor() as c:
        c.execute('SELECT period_id,price FROM monthly_periods WHERE student_id=%s ORDER BY period_id',(sid,))
        prices = c.fetchall()
    meta = s['subscription_edit']
    corrected = post(client, session, 'students.edit', dict(id=sid, revision=s['revision'],
        parent_revision=s['parent_revision'], account_revision=meta['revision'], ledger_revision=meta['ledger_revision'],
        reason='تصحيح بداية الاشتراك مع تثبيت الوصل', values=dict(start_date='2026-09-28')))
    assert corrected.status_code == 200, corrected.text
    assert records(conn, 'monthly_receipts') == receipts
    assert records(conn, 'monthly_allocation_snapshots') == frozen
    assert records(conn, 'monthly_allocations') == allocations
    assert F.projection(conn, sid)['cash_paid'] == 6000
    assert F.projection(conn, sid)['account']['calendar_due_day'] == 10
    assert F.projection(conn, sid)['account']['calendar_due_from'] is None
    assert F.projection(conn, sid)['periods'][0]['due_date'] == date(2026, 10, 10)
    assert F.projection(conn, sid)['periods'][1]['due_date'] == date(2026, 11, 10)
    after_pdf = client.get('/api/receipt/'+str(rid))
    assert after_pdf.status_code == 200
    assert '\n'.join(p.extract_text() for p in PdfReader(BytesIO(after_pdf.content)).pages) == before_text
    with conn.cursor() as c:
        c.execute('SELECT period_id,price FROM monthly_periods WHERE student_id=%s ORDER BY period_id',(sid,))
        assert c.fetchall() == prices


@pytest.mark.parametrize('anchor,first_due,second_due', [
    (date(2024,1,31),date(2024,2,10),date(2024,3,10)),
    (date(2025,1,31),date(2025,2,10),date(2025,3,10)),
    (date(2026,12,31),date(2027,1,10),date(2027,2,10))])
def test_january_leap_and_year_end_use_calendar_months(browser, monkeypatch, anchor, first_due, second_due):
    client, conn = browser
    session = login(client)
    on(monkeypatch, first_due-timedelta(days=1))
    sid = enroll(client, session, anchor)
    assert F.projection(conn, sid)['due_now'] == 0
    on(monkeypatch, first_due)
    assert F.projection(conn, sid)['due_now'] == 3000
    pay(client, session, sid, 3000)
    on(monkeypatch, second_due-timedelta(days=1))
    assert F.projection(conn, sid)['due_now'] == 0
    on(monkeypatch, second_due)
    assert F.projection(conn, sid)['due_now'] == 3000


def test_python_and_sql_deadlines_match_calendar_and_legacy_boundaries(access):
    import billing_schedule as B
    conn, *_ = access
    effective = date(2026,11,10)
    cases = []
    for start in (date(2024,1,31),date(2025,1,31),date(2026,10,1),date(2026,10,29),date(2026,12,31)):
        end = F.anniversary(start,1)
        for chosen in (10,29,30,31,None):
            for boundary in (None,effective):
                if chosen is None and boundary is not None:
                    continue
                for day in (effective-timedelta(days=1),effective,effective+timedelta(days=20)):
                    for due_at_end in (True,False):
                        cases.append((start,end,chosen,boundary,day,due_at_end))
    for start,end,chosen,boundary,day,due_at_end in cases:
        account = dict(due_at_period_end=due_at_end,calendar_due_day=chosen,calendar_due_from=boundary)
        py = B.period_due_date(account,start,end,day)
        with conn.cursor() as c:
            c.execute('SELECT '+B.due_sql(as_of='%(as_of)s')+''' AS due
                FROM (SELECT %(due_at_end)s::boolean AS due_at_period_end,%(chosen)s::smallint AS calendar_due_day,
                      %(boundary)s::date AS calendar_due_from) a
                CROSS JOIN (SELECT %(start)s::date AS starts,%(end)s::date AS ends) p''',
                dict(as_of=day,chosen=chosen,boundary=boundary,start=start,end=end,due_at_end=due_at_end))
            assert c.fetchone()['due'] == py
    assert B.period_due(dict(due_at_period_end=True,calendar_due_day=10,calendar_due_from=None),
        dict(start=date(2026,10,29),end=date(2026,11,29)),effective) == effective
    assert B.period_due(dict(due_at_period_end=True,calendar_due_day=10,calendar_due_from=effective),
        dict(start=date(2026,10,1),end=date(2026,11,1)),effective) == date(2026,11,1)
    assert B.period_due(dict(due_at_period_end=False,calendar_due_day=None,calendar_due_from=None),
        dict(start=date(2026,10,29),end=date(2026,11,29)),effective) == date(2026,10,29)


@pytest.mark.parametrize('paused,due_at_end', [(False, True), (True, True), (False, False)])
def test_explicit_reactivation_adopts_calendar_without_restarting_paused_billing(browser, monkeypatch, paused, due_at_end):
    from account_records import change_account
    client, conn = browser
    session = login(client)
    on(monkeypatch, date(2026,11,10))
    sid = enroll(client,session,date(2026,10,29),mode='exempt')
    with conn.cursor() as c:
        A.require(c,'accounts.edit')
        c.execute('''UPDATE monthly_accounts SET calendar_due_day=NULL,calendar_due_from=NULL,
            due_at_period_end=%s,departure_on=%s WHERE student_id=%s''',
            (due_at_end,date(2026,11,9) if paused else None,sid))
    change_account(sid,status='regular',actor='owner',reason='إعادة تفعيل حساب قديم صراحة')
    p=F.projection(conn,sid)
    assert p['account']['status']=='regular' and p['cash_paid']==0
    assert p['account']['due_at_period_end'] is due_at_end
    if paused:
        assert p['account']['calendar_due_day'] is None
        assert p['account']['calendar_due_from'] is None
        assert p['due_now']==1000  # Existing reactivation registration fee only.
    else:
        assert p['account']['calendar_due_day']==10
        assert p['account']['calendar_due_from']==date(2026,11,10)
        assert p['due_now']==4000  # Registration plus October's calendar tuition.
        assert F.period_due_date(p['account'],date(2026,11,29),date(2026,12,29),F.today())==date(2026,12,10)


def test_upgrade20_preserves_business_evidence_and_legacy_report_cutoff(browser, access):
    client, conn = browser
    session = login(client)
    # Seed real paid evidence and active unpaid accounts before reconstructing
    # the structural schema20 difference. Dates relative to deployment make
    # this rehearsal independent of the CI runner's current calendar date.
    with conn.cursor() as c:
        c.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nouakchott')::date AS day")
        effective = c.fetchone()['day']
    early_anchor = F.anniversary(effective.replace(day=1),-1)
    late_anchor = early_anchor.replace(day=28)
    if late_anchor >= effective:
        late_anchor = F.anniversary(late_anchor,-1)
    early = enroll(client,session,early_anchor)
    late = enroll(client,session,late_anchor)
    import base64
    from PIL import Image
    portrait=BytesIO();Image.new('RGB',(20,20),'teal').save(portrait,format='PNG')
    funded = enroll(client,session,early_anchor,amount='6000',photo=base64.b64encode(portrait.getvalue()).decode())
    closed = enroll(client,session,effective-timedelta(days=1))
    exempt = enroll(client,session,effective-timedelta(days=1))
    archived = enroll(client,session,effective-timedelta(days=1))
    child_archived = enroll(client,session,effective-timedelta(days=1))
    from tests.test_access_control import PASSWORD
    A.save_user(employee_name='قارئ ترقية التقويم',name='calendar_migration_reader',
        password=PASSWORD,permissions=['students.view','payments.view'])
    with conn.cursor() as c:
        A.require(c,'accounts.edit')
        c.execute('UPDATE monthly_accounts SET due_at_period_end=false WHERE student_id=%s',(funded,))
        c.execute('UPDATE monthly_accounts SET departure_on=%s WHERE student_id=%s',(effective,closed))
        c.execute("UPDATE monthly_accounts SET status='exempt',exempt_from=%s WHERE student_id=%s",(effective,exempt))
        c.execute('UPDATE monthly_accounts SET archived_at=now() WHERE student_id=%s',(archived,))
        # Some older sources archived the child without closing the financial
        # account. Deployment must not silently revive its collection policy.
        A.require(c,'students.delete')
        c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(child_archived,))
        A.require(c,'accounts.edit')
        c.execute('ALTER TABLE monthly_accounts DROP COLUMN calendar_due_day, DROP COLUMN calendar_due_from')
        c.execute('DELETE FROM app_schema_migrations WHERE version>=21')
        c.execute('INSERT INTO app_schema_migrations(version) VALUES(20) ON CONFLICT DO NOTHING')
    tables = ('students','parents','student_photos','monthly_tariffs','monthly_periods','monthly_receipts',
              'monthly_allocations','monthly_allocation_snapshots','monthly_fees','monthly_waivers','app_users')
    original = {table:records(conn,table) for table in tables}
    accounts = records(conn,'monthly_accounts')
    audit = records(conn,'monthly_audit')
    history = records(conn,'record_changes')
    migration = access[1]()
    try:
        assert M.upgrade(migration)
        assert not M.upgrade(migration)
    finally:
        migration.close()
    assert {table:records(conn,table) for table in tables} == original
    after_accounts = records(conn,'monthly_accounts')
    for row in after_accounts:
        old = next(a for a in accounts if a['student_id']==row['student_id'])
        assert {k:v for k,v in row.items() if k not in ('calendar_due_day','calendar_due_from')} == old
        if row['student_id'] in (closed,exempt,archived,child_archived):
            assert row['calendar_due_day'] is None and row['calendar_due_from'] is None
        else:
            assert row['calendar_due_day']==10 and row['calendar_due_from']==effective
    import billing_schedule as B
    funded_account=next(a for a in after_accounts if a['student_id']==funded)
    assert funded_account['due_at_period_end'] is False
    future=F.anniversary(funded_account['start_date'],3)
    following=future.replace(day=10)
    following=F.anniversary(following,1)
    assert B.period_due_date(funded_account,future,F.anniversary(future,1),effective)==following
    for sid in (closed,exempt,archived,child_archived):
        p=F.projection(conn,sid,effective,materialize=False)
        assert p['due_now']==0 and p['cash_paid']==0
    child_account=next(a for a in after_accounts if a['student_id']==child_archived)
    assert child_account['archived_at'] is None and child_account['departure_on'] is None
    assert next(s for s in records(conn,'students') if s['student_id']==child_archived)['archived_at'] is not None
    assert records(conn,'monthly_audit')[:len(audit)] == audit
    assert records(conn,'record_changes')[:len(history)] == history
    before = effective-timedelta(days=1)
    for sid in (early,late):
        current = F.projection(conn,sid,materialize=False)
        account = current['account']
        for period in current['periods']:
            assert B.period_due(account,period,before)==period['end']
            if period['end']<=effective:
                assert B.period_due(account,period,effective)==period['end']
    old_due = sum(F.projection(conn,sid,before,materialize=False)['due_now']
                  for sid in (early,late,funded,closed,exempt,archived,child_archived))
    assert F.financial_report(conn,before,before,materialize=False)['due_now']==old_due
    with conn.cursor() as c:
        c.execute('SELECT MAX(version) AS version FROM app_schema_migrations')
        assert c.fetchone()['version']==21
