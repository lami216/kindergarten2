from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

import live_pages
from tests.test_access_control import access
from tests.test_live_pages_http import browser, intake, login, post


def test_date_component_is_served_by_production_and_catalog():
    from scripts.check_translations import validate
    assert validate() == []
    with TestClient(live_pages.make_app('unused', 'https://testserver'), base_url='https://testserver') as client:
        html = client.get('/').text
        assert html.index('i18n.js') < html.index('date-entry.js') < html.index('preview.js')
        for name in ('date-entry.js', 'date-entry.css'):
            assert client.get('/' + name).status_code == 200


def test_cash_date_validation_retains_today_default(monkeypatch):
    monkeypatch.setattr(live_pages.F, 'today', lambda: date(2026, 10, 22))
    assert live_pages.cash_date({}) is None
    assert live_pages.cash_date({'date': '2024-02-29'}) == date(2024, 2, 29)
    for value in ('2025-02-29', '2026-04-31', '', '20261020', '2026-10-23'):
        with pytest.raises(ValueError):
            live_pages.cash_date({'date': value})


def test_explicit_payment_date_is_persisted_and_bound_to_retry(browser):
    import uuid
    client, conn = browser
    session = login(client)
    student = post(client, session, 'students.create', intake()).json()['id']
    on = live_pages.F.today() - timedelta(days=1)
    preview = post(client, session, 'payments.preview', {'student': student, 'amount': '3000', 'date': str(on)}).json()
    data = {'student': student, 'amount': '3000', 'date': str(on), 'revision': preview['revision'],
            'tariff': preview['tariff'], 'confirmed': True, 'request_token': str(uuid.uuid4())}
    result = post(client, session, 'payments.create', data)
    assert result.status_code == 200, result.text
    with conn.cursor() as c:
        c.execute('SELECT received_on FROM monthly_receipts WHERE receipt_id=%s', (result.json()['id'],))
        assert c.fetchone()['received_on'] == on
    # A fresh preview avoids the revision guard; changing the date still cannot reuse a token.
    current = post(client, session, 'payments.preview', {'student': student, 'amount': '3000'}).json()
    changed = post(client, session, 'payments.create', {**data, 'date': str(on - timedelta(days=1)), 'revision': current['revision']})
    assert changed.status_code == 422, changed.text
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s', (student,))
        assert c.fetchone()['n'] == 1


def test_fee_date_is_saved_retry_is_safe_and_changed_date_is_rejected(browser):
    import uuid
    client, conn = browser
    session = login(client)
    student = post(client, session, 'students.create', intake(mode='pay', registration=True)).json()['id']
    on = live_pages.F.today() - timedelta(days=1)
    data = {'student': student, 'kind': 'registration', 'due': 1000, 'date': str(on),
            'confirmed': True, 'request_token': str(uuid.uuid4())}
    saved = post(client, session, 'fees.collect', data)
    assert saved.status_code == 200, saved.text
    assert post(client, session, 'fees.collect', data).json() == {'id': saved.json()['id'], 'created': False}
    assert post(client, session, 'fees.collect', {**data, 'date': str(on - timedelta(days=1))}).status_code == 422
    with conn.cursor() as c:
        c.execute('SELECT received_on FROM monthly_receipts WHERE receipt_id=%s', (saved.json()['id'],))
        assert c.fetchone()['received_on'] == on
