"""Real PostgreSQL: concurrent upgrades, audit continuity and read-only pages."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
import os

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

import db
import records as R
import schema_migrations as M
from tests.test_record_management import ledger, child, row, scalar


def connection(cursor=RealDictCursor):
    return psycopg2.connect(os.environ['TEST_POSTGRES_DSN'], cursor_factory=cursor)


def test_three_concurrent_upgrade_commands_are_idempotent(ledger):
    conn,_=ledger
    with conn.cursor() as c:
        c.execute('DELETE FROM app_schema_migrations WHERE version=%s',(M.VERSION,))
    def run():
        c = connection()
        try:
            return M.upgrade(c)
        finally:
            c.close()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:run(),range(3)))
        assert sorted(results)==[False,False,True]
    finally:
        M.upgrade(conn)
    assert scalar(ledger[0], 'SELECT COUNT(*) FROM app_schema_migrations WHERE version=%s',(M.VERSION,))==1


def test_real_app_entrypoint_never_invokes_migrations(ledger,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import auth
    conn,_=ledger
    def forbidden(*args,**kwargs):
        raise AssertionError('A user page attempted a schema migration')
    monkeypatch.setattr(db,'get_connection',lambda:conn)
    monkeypatch.setattr(db,'init_db',forbidden)
    monkeypatch.setattr(db,'_apply_schema',forbidden)
    monkeypatch.setattr(auth,'check_authentication',lambda:True)
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py')
    app.session_state['auth_user']='readiness AppTest'
    app.run(timeout=30)
    assert not app.exception
    assert any('ملخص الروضة' in item.value for item in app.markdown)


def test_pages_only_check_schema_and_fail_closed_when_not_ready(ledger):
    conn,_=ledger
    statements=[]
    class Cursor(RealDictCursor):
        def execute(self, query, vars=None):
            statements.append(str(query))
            return super().execute(query,vars)
    c=connection(Cursor); c.autocommit=True
    try:
        db.assert_schema_ready(c)
        assert len(statements)==2 and all(s.startswith('SELECT') for s in statements)
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM app_schema_migrations WHERE version=%s',(M.VERSION,))
        with pytest.raises(M.SchemaNotReady):
            db.assert_schema_ready(c)
    finally:
        with conn.cursor() as cursor:
            cursor.execute('INSERT INTO app_schema_migrations(version) VALUES(%s) ON CONFLICT DO NOTHING',(M.VERSION,))
        c.close()


@pytest.mark.parametrize('fail',[False,True])
def test_write_during_trigger_replacement_waits_and_is_always_audited(ledger,monkeypatch,fail):
    conn,marker=ledger
    student=child(conn,marker)
    previous=row(conn,'students',student)
    dropped=Event(); release=Event(); writing=Event()
    original=db._apply_schema

    class BarrierCursor(RealDictCursor):
        def execute(self,query,vars=None):
            result=super().execute(query,vars)
            text=query.as_string(self.connection) if hasattr(query,'as_string') else str(query)
            if 'DROP TRIGGER IF EXISTS record_change_audit ON "students"' in text:
                dropped.set()
                if not release.wait(15): raise RuntimeError('test barrier timed out')
            return result

    def body(c):
        original(c)
        if fail: raise RuntimeError('injected deployment failure')
    monkeypatch.setattr(db,'_apply_schema',body)
    with conn.cursor() as c:
        c.execute('DELETE FROM app_schema_migrations WHERE version=%s',(M.VERSION,))

    def upgrade():
        c=connection(BarrierCursor)
        try:
            return M.upgrade(c)
        except RuntimeError as error:
            if not fail: raise
            assert 'injected deployment failure' in str(error)
            return 'rolled back'
        finally:
            c.close()

    def edit():
        writing.set()
        return R.edit('students',student,{'general_notes':'ملاحظة أثناء التحديث'},
            actor='concurrent writer',reason='اختبار التدقيق',expected=R.revision(previous))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            migration=pool.submit(upgrade)
            assert dropped.wait(15)
            mutation=pool.submit(edit)
            assert writing.wait(5)
            # A committed DROP is impossible: table locks hold the mutation.
            assert not mutation.done()
            release.set()
            assert migration.result(timeout=20)==('rolled back' if fail else True)
            mutation.result(timeout=20)
        assert row(conn,'students',student)['general_notes']=='ملاحظة أثناء التحديث'
        assert scalar(conn,"""SELECT COUNT(*) FROM record_changes WHERE table_name='students'
            AND record_key=%s AND actor='concurrent writer'
            AND after_state->>'general_notes'='ملاحظة أثناء التحديث'""",(student,))==1
    finally:
        release.set()
        monkeypatch.setattr(db,'_apply_schema',original)
        M.upgrade(conn)
        db.assert_schema_ready(conn)


def test_migration_refuses_to_commit_callers_pending_work(ledger):
    c=connection()
    try:
        with c.cursor() as cursor: cursor.execute('SELECT 1')
        with pytest.raises(RuntimeError,match='idle'):
            M.upgrade(c)
        assert not c.autocommit
    finally:
        c.rollback();c.close()
