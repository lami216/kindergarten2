"""Actual login and permissions, without the legacy finance QA identity."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
import streamlit as st
from streamlit.testing.v1 import AppTest
import access_control as A
import db
import schema_migrations as M
import monthly_finance as F
import expense_finance as E
import records as R
from tests.qa_auth import ORIGINAL

PASSWORD='A-strong-test-password-2026!'


@pytest.fixture
def access(monkeypatch,legacy_authorized_harness):
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn: pytest.skip('Disposable PostgreSQL required')
    from urllib.parse import urlparse
    parsed=urlparse(dsn)
    assert parsed.hostname in ('127.0.0.1','localhost') and parsed.path=='/kindergarten_test'
    schema='access_'+uuid.uuid4().hex
    admin=psycopg2.connect(dsn,cursor_factory=RealDictCursor);admin.autocommit=True
    with admin.cursor() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect(): return psycopg2.connect(dsn,options=f'-c search_path={schema}',cursor_factory=RealDictCursor)
    for name,function in ORIGINAL.items(): monkeypatch.setattr(A,name,function)
    monkeypatch.setattr(db,'new_transaction_connection',connect)
    conn=connect(); M.upgrade(conn);conn.autocommit=True
    owner=A.bootstrap('المدير الأول','owner',PASSWORD)
    token=A.login('owner',PASSWORD); assert token
    st.session_state.clear();st.session_state['auth_session']=token
    F.update_tariffs(1000,2000,3000,'owner')
    try: yield conn,connect,owner,token
    finally:
        st.session_state.clear();conn.close()
        with admin.cursor() as c: c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()


def worker(perms=(),name='worker'):
    ident=A.save_user(employee_name='العامل '+name,name=name,password=PASSWORD,permissions=perms)
    token=A.login(name,PASSWORD);assert token
    return ident,token


def sign(token):
    st.session_state['auth_session']=token


def child(token=None):
    data=dict(full_name='طفل صلاحيات',birth_date=F.today().replace(year=2022),gender='ذكر',birth_place='',address='',medical_details='خاص',allergies='',general_notes='',authorized_pickups=[])
    family=dict(father_name='أب الطفل',father_mobile='22334455',mother_name='',mother_mobile='',contact_email='')
    return db.save_child_with_family(data,family,None,token or str(uuid.uuid4()),finance=dict(mode='regular',cash=0,registration=False,gilet=False,start_date=str(F.today()),payer=''),actor='spoofed manager')


def test_passwords_login_identity_and_case_unique(access):
    conn,_,owner,token=access
    uid,worker_token=worker(['students.create'])
    with conn.cursor() as c:
        c.execute('SELECT password_hash FROM app_users WHERE user_id=%s',(uid,));hashed=c.fetchone()['password_hash']
    assert PASSWORD not in hashed and A.verify_password(PASSWORD,hashed)
    assert not A.verify_password(PASSWORD+'wrong',hashed)
    assert A.login('WORKER',PASSWORD)
    assert A.login('worker','wrong') is None
    assert A.login('missing',PASSWORD) is None
    with pytest.raises(ValueError,match='مستخدم'): worker(name='WORKER')
    sign(worker_token)
    with pytest.raises(A.AccessDenied): A.save_user(employee_name='صاعد',name='attacker',password=PASSWORD,is_admin=True)
    with pytest.raises(A.AccessDenied): A.list_users(conn)
    with pytest.raises(A.AccessDenied): A.employee_metrics(conn,owner)


def test_create_only_child_atomic_audited_idempotent_and_no_cash(access):
    conn,_,owner,owner_token=access
    uid,token=worker(['students.create']);sign(token)
    request=str(uuid.uuid4());sid,created=child(request)
    assert created and child(request)==(sid,False)
    with conn.cursor() as c:
        c.execute("SELECT actor,actor_user_id FROM record_changes WHERE table_name='students' AND record_key=%s",(sid,))
        history=c.fetchall()
    assert len(history)==1 and history[0]['actor']=='worker' and str(history[0]['actor_user_id'])==uid
    assert A.employee_metrics(conn,uid)['students']==1
    with pytest.raises(A.AccessDenied): F.take_payment(sid,1000,actor='owner')
    with pytest.raises(A.AccessDenied): R.edit('students',sid,{'address':'ممنوع'},actor='owner',reason='اختبار')
    with pytest.raises(A.AccessDenied):
        from data_export import build_export
        build_export()
    sign(owner_token)
    assert A.employee_metrics(conn,uid)['students']==1


def test_worker_expenses_no_double_count_and_net_after_correction_cancel(access):
    conn,_,_,owner_token=access
    uid,token=worker(['expenses.create','expenses.edit','expenses.delete']);sign(token)
    request=str(uuid.uuid4())
    args=dict(category='قرطاسية',amount_total=1200,amount_paid=1000,expense_date=F.today(),token=request)
    ident,new=E.create(**args);assert new and E.create(**args)==(ident,False)
    assert A.employee_metrics(conn,uid)['expenses']==dict(count=1,original_cash=1000,current_cash=1000)
    E.correct(ident,amount_total=1400,amount_paid=800,category='قرطاسية',expense_date=F.today(),payee='',notes='',actor='owner',reason='تصحيح')
    assert A.employee_metrics(conn,uid)['expenses']['current_cash']==800
    E.cancel(ident,actor='owner',reason='إلغاء إدخال')
    metrics=A.employee_metrics(conn,uid)
    assert metrics['expenses']==dict(count=1,original_cash=1000,current_cash=0)
    with conn.cursor() as c:
        c.execute('SELECT before_state::text,after_state::text FROM app_access_audit')
        assert all(PASSWORD not in str(r) and 'pbkdf2_' not in str(r) for r in c.fetchall())


def test_receipt_correction_chain_attributed_once_to_original_operator(access):
    conn,_,_,owner_token=access
    F.update_tariffs(0,0,3000,'owner');sid,_=child()
    uid,token=worker(['payments.create','payments.edit','payments.delete']);sign(token)
    original,_=F.take_payment(sid,6000,actor='owner')
    corrected,_=F.correct_receipt(original,4500,'تصحيح',actor='owner')
    metrics=A.employee_metrics(conn,uid)['payments']
    assert metrics==dict(count=1,original_cash=6000,current_cash=4500)
    sign(owner_token)
    F.cancel_receipt(corrected,'إلغاء',actor='worker')
    assert A.employee_metrics(conn,uid)['payments']==dict(count=1,original_cash=6000,current_cash=0)


def test_revoke_permission_reset_password_disable_and_old_form_sql(access):
    conn,connect,_,owner_token=access
    uid,token=worker(['students.create']);sign(token)
    profile=A.current();web=connect();web.autocommit=True;A.bind(web,profile)
    sign(owner_token)
    A.save_user(user_id=uid,employee_name='عامل محدث',permissions=[],expected_version=1)
    sign(token)
    with pytest.raises(A.AccessDenied): child()
    with web.cursor() as c:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("INSERT INTO parents(father_id,father_name) VALUES('blocked-parent','محاولة قديمة')")
    web.close()
    fresh=A.login('worker',PASSWORD);assert fresh
    sign(owner_token)
    A.save_user(user_id=uid,employee_name='عامل',password=PASSWORD+'new',permissions=[],active=False,expected_version=2)
    assert A.login('worker',PASSWORD) is None
    assert A.login('worker',PASSWORD+'new') is None
    sign(fresh)
    with pytest.raises(A.AccessDenied): A.current()


def test_last_admin_and_stale_account_editor(access):
    conn,_,owner,token=access
    with pytest.raises(ValueError,match='آخر مدير'):
        A.save_user(user_id=owner,employee_name='المدير',is_admin=False,expected_version=1)
    uid,_=worker([])
    A.save_user(user_id=uid,employee_name='عامل جديد',permissions=['students.create'],expected_version=1)
    with pytest.raises(ValueError,match='تغير الحساب'):
        A.save_user(user_id=uid,employee_name='نموذج قديم',permissions=['expenses.create'],expected_version=1)


def test_throttling_is_shared_and_session_expiry_clears_drafts(access):
    conn,_,_,token=access
    uid,_=worker([])
    for _ in range(5): assert A.login('worker','incorrect') is None
    assert A.login('worker',PASSWORD) is None
    with conn.cursor() as c: c.execute("UPDATE app_login_attempts SET blocked_until=now()-interval '1 second',updated_at=now()-interval '16 minutes'")
    fresh=A.login('worker',PASSWORD);assert fresh
    sign(fresh);st.session_state['private_draft']='secret';st.session_state['verified_export']=b'secret'
    with conn.cursor() as c: c.execute("UPDATE app_sessions SET last_seen=now()-interval '31 minutes' WHERE user_id=%s",(uid,))
    with pytest.raises(A.AccessDenied): A.refresh(conn)
    A.clear_state()
    assert 'private_draft' not in st.session_state and 'verified_export' not in st.session_state


def test_staff_ui_create_only_hides_records_finance_and_other_routes(access):
    conn,_,_,owner_token=access
    uid,token=worker(['students.create'])
    app=AppTest.from_string('''import streamlit as st
import db,access_control as A
from sections import staff_workspace
conn=db.new_transaction_connection();conn.autocommit=True
try:
 A.refresh(conn)
 staff_workspace.render(conn)
finally: conn.close()
''')
    app.session_state['auth_session']=token
    app.session_state['current_page']='students'
    app.run(timeout=30)
    assert not app.exception
    assert app.text_input(key='kid_name')
    assert not any(b.label in ('المصروفات التشغيلية','الرواتب والسلف','لوحة المدير','تجهيز ملف التصدير') for b in app.button)
    assert not app.selectbox or all(w.label not in ('نوع السجل','اختر السجل','ولي الأمر الموجود') for w in app.selectbox)
    assert app.session_state['kid_finance_mode']=='بلا دفعة'
    app.session_state['current_page']='salaries'
    app.run(timeout=30)
    assert not app.exception and app.session_state['current_page']=='home'


def test_revocation_serializes_with_inflight_write_and_preserves_actor(access):
    conn,connect,_,owner_token=access
    uid,token=worker(['expenses.create']);sign(token)
    profile=A.current();web=connect();web.autocommit=True;A.bind(web,profile);web.autocommit=False
    with web.cursor() as c:
        c.execute("INSERT INTO expenses(category,amount,amount_paid) VALUES('قبل سحب الإذن',100,100)")
    sign(owner_token);started=Event()
    def revoke():
        started.set()
        A.save_user(user_id=uid,employee_name='عامل',permissions=[],expected_version=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(revoke);assert started.wait(5)
        # The UPDATE cannot pass the account/session read lock held by the write.
        from time import sleep
        sleep(.2);assert not future.done()
        web.commit();future.result(timeout=10)
    with web.cursor() as c:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("INSERT INTO expenses(category,amount,amount_paid) VALUES('بعد سحب الإذن',100,100)")
    web.rollback();web.close()
    with conn.cursor() as c:
        c.execute("SELECT actor,actor_user_id FROM record_changes WHERE table_name='expenses'")
        rows=c.fetchall()
    assert len(rows)==1 and rows[0]['actor']=='worker' and str(rows[0]['actor_user_id'])==uid
