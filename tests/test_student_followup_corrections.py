"""Follow-up reflects corrected real cash and waivers without writing another ledger."""
from datetime import date
import uuid

import db
import monthly_finance as F
from tests.test_student_followup import child, entries
from tests.test_live_pages_http import browser, login, post
from tests.test_access_control import access


def payment(client, session, student, amount):
    payload = dict(student=student, amount=str(amount), date='2026-11-10', payer='الأم')
    preview = post(client, session, 'payments.preview', payload)
    assert preview.status_code == 200, preview.text
    q = preview.json()
    saved = post(client, session, 'payments.create', dict(**payload, confirmed=True,
        request_token=str(uuid.uuid4()), revision=q['revision'], tariff=q['tariff']))
    assert saved.status_code == 200, saved.text
    return saved.json()['id']


def active_receipt(client, student):
    snapshot = client.get('/api/snapshot')
    assert snapshot.status_code == 200, snapshot.text
    return next(r for r in snapshot.json()['receipts'] if r['student'] == student and not r['cancelled'])


def business_state(conn):
    # Settings, account dates, cash and audit records must survive repeated reads.
    tables = ('monthly_accounts', 'monthly_tariffs', 'monthly_periods',
              'monthly_receipts', 'monthly_allocations', 'monthly_waivers',
              'monthly_waiver_batches', 'monthly_audit', 'record_changes')
    with conn.cursor() as c:
        result = {}
        for table in tables:
            c.execute('SELECT * FROM ' + table + ' ORDER BY 1')
            result[table] = [dict(r) for r in c.fetchall()]
    return result


def test_full_payment_removes_reminder_and_receipt_correction_cancel_restore_exact_debt(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    monkeypatch.setattr(F, 'today', lambda: date(2026, 11, 10))
    sid = child(client, session, '2026-10-08')
    assert entries(client, session)[0]['due_total'] == 3000
    payment(client, session, sid, 3000)
    assert entries(client, session) == []
    receipt = active_receipt(client, sid)
    correction = post(client, session, 'records.change', dict(type='receipts', id=receipt['id'],
        mode='edit', reason='تصحيح القبض الفعلي', confirmed=True, revision=receipt['revision'],
        values=dict(amount='1000', date=receipt['date']), request_token=str(uuid.uuid4())))
    assert correction.status_code == 200, correction.text
    rows = entries(client, session)
    assert len(rows) == 1 and rows[0]['id'] == sid
    assert rows[0]['due_total'] == rows[0]['due_monthly'] == 2000
    assert rows[0]['due_fees'] == 0
    active = active_receipt(client, sid)
    cancelled = post(client, session, 'records.change', dict(type='receipts', id=active['id'],
        mode='cancel', reason='إلغاء قبض الاختبار', confirmed=True, revision=active['revision'],
        request_token=str(uuid.uuid4())))
    assert cancelled.status_code == 200, cancelled.text
    rows = entries(client, session)
    assert len(rows) == 1 and rows[0]['due_total'] == 3000
    assert F.projection(conn, sid, materialize=False)['cash_paid'] == 0


def test_explicit_non_cash_waiver_removes_followup_without_creating_receipt(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    monkeypatch.setattr(F, 'today', lambda: date(2026, 11, 10))
    sid = child(client, session, '2026-10-08')
    assert entries(client, session)[0]['due_total'] == 3000
    snapshot = client.get('/api/snapshot').json()
    student = next(s for s in snapshot['students'] if s['id'] == sid)
    waiver = post(client, session, 'students.waive', dict(student=sid,
        revision=student['ledger_revision'], due=student['account']['due'],
        reason='إسقاط موثق دون قبض', confirmed=True, request_token=str(uuid.uuid4())))
    assert waiver.status_code == 200, waiver.text
    assert waiver.json()['waived'] == 3000
    assert entries(client, session) == []
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s', (sid,))
        assert c.fetchone()['n'] == 0
        c.execute('SELECT SUM(amount) AS n FROM monthly_waivers WHERE student_id=%s', (sid,))
        assert c.fetchone()['n'] == 3000


def test_repeated_read_has_no_business_side_effects_and_connection_count_stays_constant(browser, monkeypatch):
    client, conn = browser
    session = login(client)
    monkeypatch.setattr(F, 'today', lambda: date(2026, 11, 10))
    first = child(client, session, '2026-10-08', name='متابعة طفل واحد')
    # Materialize only through the same official read used by the application.
    assert entries(client, session)[0]['id'] == first
    small_state = business_state(conn)
    original_connect = db.new_transaction_connection
    connections = []
    def counted_connect():
        connection = original_connect()
        connections.append(connection)
        return connection
    monkeypatch.setattr(db, 'new_transaction_connection', counted_connect)
    assert len(entries(client, session)) == 1
    small_count = len(connections)
    assert business_state(conn) == small_state
    for index in range(25):
        child(client, session, '2026-10-08', name='متابعة طفل ' + str(index))
    assert len(entries(client, session)) == 26
    large_state = business_state(conn)
    for _ in range(3):
        connections.clear()
        rows = entries(client, session)
        assert len(rows) == 26
        assert sum(r['due_total'] for r in rows) == 26 * 3000
        assert len(connections) == small_count
        assert 1 <= small_count <= 3
        assert business_state(conn) == large_state
