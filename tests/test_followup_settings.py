"""Real permissions, audit, stale-window checks and nonfinancial migration."""
import pytest

import followup_settings as S
import schema_migrations as M
import access_control as A
import monthly_finance as F
from tests.test_access_control import access, child, sign, worker


def values(conn):
    with conn.cursor() as c:
        c.execute('SELECT registration,gilet,tuition,changed_by,changed_at FROM monthly_tariffs WHERE id=1')
        return dict(c.fetchone())


def test_default_save_is_audited_without_changing_prices_or_cash(access):
    conn, _, _, _ = access
    sid, _ = child()
    F.take_payment(sid, 6000, actor='owner')
    before = values(conn)
    with conn.cursor() as c:
        c.execute('SELECT SUM(amount) AS n FROM monthly_receipts')
        cash = c.fetchone()['n']
    setting = S.read(conn)
    assert setting['day'] == 10 and setting['editable']
    result = S.save(conn, dict(confirmed=True, day='١٢', revision=setting['revision'], reason='تعديل يوم المتابعة'))
    assert result['day'] == S.read(conn)['day'] == 12
    assert values(conn) == before
    with conn.cursor() as c:
        c.execute('SELECT SUM(amount) AS n FROM monthly_receipts')
        assert c.fetchone()['n'] == cash
        c.execute("SELECT actor,reason,before_state,after_state FROM record_changes WHERE table_name='monthly_tariffs' AND reason=%s", ('تعديل يوم المتابعة',))
        rows = c.fetchall()
    assert len(rows) == 1
    assert rows[0]['actor'] == 'owner'
    assert rows[0]['before_state']['followup_day'] == 10
    assert rows[0]['after_state']['followup_day'] == 12


@pytest.mark.parametrize('permissions', [['payments.view'], ['fees.view', 'fees.edit']])
def test_worker_cannot_change_school_policy_even_with_fee_edit(access, permissions):
    conn, _, _, owner = access
    _, token = worker(permissions)
    sign(token)
    setting = S.read(conn)
    assert setting['day'] == 10 and not setting['editable']
    with pytest.raises(A.AccessDenied):
        S.save(conn, dict(confirmed=True, day=15, revision=setting['revision'], reason='محاولة غير مسموحة'))
    sign(owner)
    assert S.read(conn)['day'] == 10


def test_stale_settings_window_and_missing_reason_are_rejected(access):
    conn, _, _, _ = access
    old = S.read(conn)
    S.save(conn, dict(confirmed=True, day=31, revision=old['revision'], reason='نهاية الشهر'))
    with pytest.raises(ValueError, match='تغيّر'):
        S.save(conn, dict(confirmed=True, day=20, revision=old['revision'], reason='نافذة قديمة'))
    with pytest.raises(ValueError, match='سبب'):
        S.save(conn, dict(confirmed=True, day=20, revision=S.read(conn)['revision'], reason=' '))
    assert S.read(conn)['day'] == 31


@pytest.mark.parametrize('day', [0, 32, -1, True, 10.0, '10.0', '10x', '', None])
def test_invalid_day_does_not_change_settings(access, day):
    conn, _, _, _ = access
    initial = S.read(conn)
    with pytest.raises(ValueError, match='يوم'):
        S.save(conn, dict(confirmed=True, day=day, revision=initial['revision'], reason='اختبار تحقق'))
    assert S.read(conn) == initial


def test_noop_does_not_create_a_fake_change(access):
    conn, _, _, _ = access
    initial = S.read(conn)
    S.save(conn, dict(confirmed=True, day=10, revision=initial['revision'], reason='لم يتغير اليوم'))
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n FROM record_changes WHERE reason='لم يتغير اليوم'")
        assert c.fetchone()['n'] == 0


@pytest.mark.parametrize('confirmed', [False, None, 'true', 1])
def test_explicit_confirmation_required(access, confirmed):
    conn, _, _, _ = access
    setting = S.read(conn)
    with pytest.raises(ValueError, match='أكّد'):
        S.save(conn, dict(day=15, revision=setting['revision'], reason='تعديل مقصود', confirmed=confirmed))
    assert S.read(conn)['day'] == 10


def test_official_upgrade_19_to_current_keeps_existing_data_and_access(access):
    conn, connect, _, _ = access
    sid, _ = child()
    F.take_payment(sid, 6000, actor='owner')
    before = values(conn)
    with conn.cursor() as c:
        c.execute('SELECT user_id,username,password_hash,permissions,active,auth_version FROM app_users ORDER BY user_id')
        users = c.fetchall()
        c.execute('SELECT receipt_id,student_id,amount,state FROM monthly_receipts ORDER BY receipt_id')
        receipts = c.fetchall()
        # Reconstruct the only structural difference of the prior schema.
        c.execute('ALTER TABLE monthly_tariffs DROP COLUMN followup_day')
        c.execute('DELETE FROM app_schema_migrations WHERE version>=20')
        c.execute('INSERT INTO app_schema_migrations(version) VALUES(19) ON CONFLICT DO NOTHING')
    upgrade = connect()
    try:
        assert M.upgrade(upgrade)
        assert not M.upgrade(upgrade)
    finally:
        upgrade.close()
    assert S.read(conn)['day'] == 10
    assert values(conn) == before
    with conn.cursor() as c:
        c.execute('SELECT MAX(version) AS n FROM app_schema_migrations')
        assert c.fetchone()['n'] == M.VERSION
        c.execute('SELECT user_id,username,password_hash,permissions,active,auth_version FROM app_users ORDER BY user_id')
        assert c.fetchall() == users
        c.execute('SELECT receipt_id,student_id,amount,state FROM monthly_receipts ORDER BY receipt_id')
        assert c.fetchall() == receipts
