"""Real HTTP authorization/ledger integration on a disposable PostgreSQL schema."""
import uuid
import pytest
from starlette.testclient import TestClient
from tests.test_access_control import access, PASSWORD
import access_control as A
from live_pages import make_app, COOKIE, DESIGN_ROOT

ORIGIN='https://kindergarten.test'


@pytest.fixture
def browser(access):
    app=make_app('unused-by-isolated-fixture',ORIGIN)
    with TestClient(app,base_url=ORIGIN) as client:
        yield client,access[0]


def login(client,name='owner',password=PASSWORD):
    r=client.post('/api/login',json={'username':name,'password':password},headers={'Origin':ORIGIN})
    assert r.status_code==200,r.text
    session=client.get('/api/session')
    assert session.status_code==200,session.text
    return session.json()


def post(client,session,operation,data):
    return client.post('/api/'+operation,json=data,headers={'Origin':ORIGIN,'X-CSRF-Token':session['csrf']})


def intake(**changes):
    result=dict(name='طفل فعلي للاختبار',birth='2022-01-01',gender='ذكر',father='',fatherPhone='',
        mother='أم الطفل',motherPhone='22334455',mode='none',amount='0',registration=False,gilet=False,
        request_token=str(uuid.uuid4()))
    result.update(changes)
    return result


def test_valid_cookie_session_opens_supplementary_tools_without_second_login(access,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from streamlit.runtime.context import ContextProxy
    import db
    conn,_,owner,token=access
    monkeypatch.setattr(ContextProxy,'cookies',property(lambda self:{'__Host-kg_session':token}))
    monkeypatch.setattr(db,'get_connection',lambda:conn)
    app=AppTest.from_string("""
import streamlit as st
import auth,db
if auth.check_authentication(db.get_connection()):
    st.success('REAL_COOKIE_AUTHENTICATED')
""").run(timeout=15)
    assert not app.exception
    assert any(s.value=='REAL_COOKIE_AUTHENTICATED' for s in app.success)
    assert app.session_state['auth_user']=='owner'


def test_report_only_identity_gets_real_counts_without_child_private_data(browser):
    client,conn=browser
    owner=login(client)
    post(client,owner,'students.create',intake())
    A.save_user(employee_name='قارئ التقارير',name='reports_only',password=PASSWORD,permissions=['reports.view'])
    login(client,'reports_only')
    response=client.get('/api/snapshot')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['students']==[] and data['receipts']==[]
    assert data['overview']['students_count']==1


def test_http_rejects_unauthenticated_csrf_foreign_origin_and_private_files(browser):
    client,_=browser
    assert client.get('/api/session').status_code==401
    assert client.get('/api/snapshot').status_code==401
    assert client.get('/api/photo/anything').status_code==401
    assert client.get('/api/receipt/1').status_code==401
    assert client.post('/api/login',json={'username':'owner','password':PASSWORD},headers={'Origin':'https://evil.test'}).status_code==403
    session=login(client)
    cookie=client.cookies[COOKIE]
    assert cookie and 'password' not in str(session) and 'token_hash' not in str(session)
    r=client.post('/api/expenses.create',json={},headers={'Origin':ORIGIN})
    assert r.status_code==403
    assert client.get('/api/session',headers={'Host':'evil.test'}).status_code==400
    assert client.get('/.streamlit/secrets.toml').status_code==404
    assert client.get('/preview.css').content==(DESIGN_ROOT/'preview.css').read_bytes()
    assert client.get('/').headers['content-security-policy'].startswith("default-src 'self'")


def test_http_committed_intake_idempotence_and_real_snapshot(browser):
    client,conn=browser;session=login(client)
    payload=intake()
    first=post(client,session,'students.create',payload)
    assert first.status_code==200,first.text
    ident=first.json()['id']
    assert ident.startswith('S') and first.json()['created']
    second=post(client,session,'students.create',payload)
    assert second.status_code==200 and not second.json()['created']
    snapshot=client.get('/api/snapshot')
    assert snapshot.status_code==200,snapshot.text
    s=next(s for s in snapshot.json()['students'] if s['id']==ident)
    assert s['motherName']=='أم الطفل' and s['account']['paid']==0
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s',(ident,))
        assert c.fetchone()['n']==0
        c.execute('SELECT actor FROM record_changes WHERE table_name=%s AND record_key=%s',('students',ident))
        assert c.fetchone()['actor']=='owner'


def test_http_payment_preview_save_correct_cancel_pdf_and_expenses(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake()).json()['id']
    preview=post(client,session,'payments.preview',{'student':sid,'amount':'3000'})
    assert preview.status_code==200,preview.text
    p=preview.json()
    pay={'student':sid,'amount':'3000','confirmed':True,'revision':p['revision'],'tariff':p['tariff'],'request_token':str(uuid.uuid4())}
    result=post(client,session,'payments.create',pay)
    assert result.status_code==200,result.text
    data=client.get('/api/snapshot')
    assert data.status_code==200,data.text
    r=next(r for r in data.json()['receipts'] if r['student']==sid)
    pdf=client.get('/api/receipt/'+str(r['id']))
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    correction=post(client,session,'records.change',{'type':'receipts','id':r['id'],'mode':'edit',
        'reason':'تصحيح المبلغ الفعلي','confirmed':True,'revision':r['revision'],
        'values':{'amount':'2000','date':r['date']},'request_token':str(uuid.uuid4())})
    assert correction.status_code==200,correction.text
    corrected=correction.json()
    assert type(corrected['id']) is int and corrected['created'] is True
    data=client.get('/api/snapshot').json()
    active=next(r for r in data['receipts'] if r['student']==sid and not r['cancelled'])
    cancelled=post(client,session,'records.change',{'type':'receipts','id':active['id'],'mode':'cancel',
        'reason':'إلغاء إدخال خاطئ','confirmed':True,'revision':active['revision'],
        'request_token':str(uuid.uuid4())})
    assert cancelled.status_code==200,cancelled.text
    assert cancelled.json()=={'id':active['id'],'cancelled':True}
    payload={'category':'مصروف فعلي','amount':'100','paid':'40','payee':'مورد','notes':'ملاحظة تبقى',
        'date':data['today'],'request_token':str(uuid.uuid4())}
    expense=post(client,session,'expenses.create',payload)
    assert expense.status_code==200,expense.text
    fresh=client.get('/api/snapshot')
    assert fresh.status_code==200,fresh.text
    e=next(e for e in fresh.json()['expenses'] if e['category']=='مصروف فعلي')
    assert e['amount']==100 and e['paid']==40
    assert fresh.json()['overview']['total_cash']==0
    assert fresh.json()['overview']['expenses']==40


def test_http_department_create_transfer_and_student_atomic_edit(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake()).json()['id']
    dep=post(client,session,'departments.create',{'name':'قسم فعلي'})
    assert dep.status_code==200,dep.text
    transfer=post(client,session,'departments.transfer',{'ids':[sid],'department_id':dep.json()['id']})
    assert transfer.status_code==200,transfer.text
    data=client.get('/api/snapshot').json();s=next(s for s in data['students'] if s['id']==sid)
    assert s['class']=='قسم فعلي'
    change={'id':sid,'revision':s['revision'],'parent_revision':s['parent_revision'],'reason':'تعديل حقيقي',
        'values':{'name':'اسم جديد','motherName':'الأم الجديدة','motherPhone':'99887766'}}
    result=post(client,session,'students.edit',change)
    assert result.status_code==200,result.text
    stale=post(client,session,'students.edit',change)
    assert stale.status_code==422,stale.text
    s=next(s for s in client.get('/api/snapshot').json()['students'] if s['id']==sid)
    invalid={**change,'revision':s['revision'],'parent_revision':s['parent_revision'],
        'values':{'name':'اسم لا يجب حفظه','motherName':'','motherPhone':'99887766'}}
    result=post(client,session,'students.edit',invalid)
    assert result.status_code==422,result.text
    s=next(s for s in client.get('/api/snapshot').json()['students'] if s['id']==sid)
    assert s['name']=='اسم جديد' and s['motherName']=='الأم الجديدة'


def test_http_worker_visibility_server_rejection_revocation_and_logout(browser):
    client,conn=browser;owner=login(client)
    uid=A.save_user(employee_name='عامل محدود',name='limited',password=PASSWORD,permissions=['students.create'])
    worker=login(client,'limited')
    data=client.get('/api/snapshot')
    assert data.status_code==200,data.text
    assert data.json()['students']==[] and data.json()['receipts']==[] and data.json()['overview'] is None
    r=post(client,worker,'expenses.create',{'category':'ممنوع','amount':'10','paid':'10','date':'2026-10-01','request_token':str(uuid.uuid4())})
    assert r.status_code==403,r.text
    r=post(client,worker,'users.save',{'name':'هجوم','username':'attack','password':PASSWORD,'permissions':[]})
    assert r.status_code==403,r.text
    r=post(client,worker,'students.create',intake())
    assert r.status_code==200,r.text
    # Management changes invalidate every existing session immediately.
    A.save_user(user_id=uid,employee_name='عامل محدود',active=False,permissions=[],expected_version=1)
    assert client.get('/api/session').status_code==403
    owner=login(client)
    assert post(client,owner,'logout',{}).status_code==200
    assert client.get('/api/session').status_code==401


def test_siblings_link_existing_family_without_overwriting_it_and_retry_once(browser):
    client,conn=browser;session=login(client)
    first=post(client,session,'students.create',intake()).json()['id']
    data=client.get('/api/snapshot').json()
    family=data['families'][0]
    payload=intake(name='أخت الطفل',existing_parent_id=family['id'],mother='اسم لن يستبدل الأم',
                   motherPhone='99999999',mode='pay',registration=True,amount='1000')
    saved=post(client,session,'students.create',payload)
    assert saved.status_code==200,saved.text
    duplicate=post(client,session,'students.create',payload)
    assert duplicate.status_code==200 and duplicate.json()=={'id':saved.json()['id'],'created':False}
    data=client.get('/api/snapshot').json()
    assert len(data['families'])==1
    assert {s['parent_id'] for s in data['students']}=={family['id']}
    assert {s['motherName'] for s in data['students']}=={'أم الطفل'}
    assert data['overview']['total_cash']==1000
    with conn.cursor() as c:
        c.execute('SELECT payer FROM monthly_receipts WHERE student_id=%s',(saved.json()['id'],))
        assert c.fetchone()['payer']=='أم الطفل'
    # A create-only worker cannot discover or forge links to existing families.
    A.save_user(employee_name='مسجل فقط',name='intake_only',password=PASSWORD,permissions=['students.create'])
    worker=login(client,'intake_only')
    assert client.get('/api/snapshot').json()['families']==[]
    denied=post(client,worker,'students.create',intake(existing_parent_id=family['id']))
    assert denied.status_code==403
    owner=login(client)
    unknown=post(client,owner,'students.create',intake(existing_parent_id='P-missing'))
    assert unknown.status_code==422
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM students')
        assert c.fetchone()['n']==2


def test_fee_receipt_contract_and_retry_return_scalar_identity(browser):
    client,_=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=True)).json()['id']
    payload=dict(student=sid,kind='registration',due=1000,confirmed=True,request_token=str(uuid.uuid4()))
    saved=post(client,session,'fees.collect',payload)
    assert saved.status_code==200,saved.text
    assert type(saved.json()['id']) is int and saved.json()['created'] is True
    retry=post(client,session,'fees.collect',payload)
    assert retry.status_code==200 and retry.json()=={'id':saved.json()['id'],'created':False}
