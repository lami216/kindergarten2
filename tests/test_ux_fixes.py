"""Audit findings reproduced through real HTTP/transactions, not mocked saves."""
from copy import deepcopy
from datetime import date
import hashlib
import uuid
import pytest
import access_control as A
from tests.test_live_pages_http import browser, login, post, intake, ORIGIN
from tests.test_access_control import access


def teacher(client, session):
    response=post(client,session,'tools.change',dict(table='teachers',mode='create',
        values=dict(full_name='معلم سجل واضح',national_id='UX-TEACHER',salary='2000',department_id=1),
        reason='إنشاء معلم الاختبار',confirmed=True,request_token=str(uuid.uuid4())))
    assert response.status_code==200,response.text
    return response.json()['id']


@pytest.mark.parametrize('kind,table,key',[('salary','teacher_payments','payment_id'),('advance','teacher_advances','advance_id')])
def test_payroll_reason_is_atomic_in_both_audits_and_bound_to_retry(browser,kind,table,key):
    client,conn=browser;session=login(client);ident=teacher(client,session)
    payload=dict(kind=kind,teacher=ident,month=str(date.today())[:7],date=str(date.today()),
        base='2000',bonus='500',deductions='100',amount='500',notes='ملاحظة مستقلة',
        reason='صرف اختباري بسبب واضح',confirmed=True,request_token=str(uuid.uuid4()))
    created=post(client,session,'payroll.save',payload)
    assert created.status_code==200,created.text
    saved=created.json()['id']
    assert post(client,session,'payroll.save',payload).json()=={'id':saved,'created':False}
    conflict=post(client,session,'payroll.save',{**payload,'reason':'سبب مختلف'})
    assert conflict.status_code==422,conflict.text
    with conn.cursor() as c:
        c.execute(f'SELECT amount,cash_amount,notes FROM {table} WHERE {key}=%s',(saved,))
        row=c.fetchone();assert row['amount']==row['cash_amount']==(2400 if kind=='salary' else 500)
        assert row['notes']=='ملاحظة مستقلة'
        c.execute(f'SELECT reason,actor FROM payroll_audit WHERE {key}=%s',(saved,))
        assert c.fetchall()==[dict(reason=payload['reason'],actor='owner')]
        c.execute('SELECT reason,actor FROM record_changes WHERE table_name=%s AND record_key=%s',(table,str(saved)))
        assert c.fetchall()==[dict(reason=payload['reason'],actor='owner')]
    snapshot=client.get('/api/snapshot').json()
    event=next(e for e in snapshot['changes'] if e['type']==table and str(e['key'])==str(saved))
    assert event['subject']=='معلم سجل واضح · UX-TEACHER'
    assert event['after_labels']['national_id']=='معلم سجل واضح · UX-TEACHER'


@pytest.mark.parametrize('reason',[None,'','   '])
def test_missing_payroll_reason_never_disburses_money(browser,reason):
    client,conn=browser;session=login(client);ident=teacher(client,session)
    payload=dict(kind='salary',teacher=ident,month=str(date.today())[:7],date=str(date.today()),
        base='2000',confirmed=True,request_token=str(uuid.uuid4()))
    if reason is not None:payload['reason']=reason
    response=post(client,session,'payroll.save',payload)
    assert response.status_code==422 and 'سبب الصرف' in response.json()['error']
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM teacher_payments');assert c.fetchone()['n']==0


def test_expired_session_and_forbidden_action_have_distinct_codes(browser):
    client,conn=browser;owner=login(client)
    A.save_user(employee_name='موظف بلا صرف',name='ux_worker',password='1234',permissions=['students.view'])
    session=login(client,'ux_worker','1234')
    forbidden=post(client,session,'payroll.save',dict(kind='salary',teacher='T1',month=str(date.today())[:7],date=str(date.today()),base='2000',reason='محاولة غير مسموحة',confirmed=True,request_token=str(uuid.uuid4())))
    assert forbidden.status_code==403 and forbidden.json()['code']=='permission_denied'
    private_forbidden=client.get('/api/download/backup')
    assert private_forbidden.status_code==403 and private_forbidden.json()['code']=='permission_denied'
    from live_pages import COOKIE
    token=client.cookies.get(COOKIE)
    with conn.cursor() as c:
        c.execute("UPDATE app_sessions SET last_seen=now()-interval '31 minutes' WHERE token_hash=%s",(hashlib.sha256(token.encode()).hexdigest(),))
    expired=post(client,session,'students.create',intake())
    assert expired.status_code==403 and expired.json()['code']=='session_expired'
    private_expired=client.get('/api/download/backup')
    assert private_expired.status_code==403 and private_expired.json()['code']=='session_expired'
    client.cookies.clear()
    absent=client.post('/api/students.create',json=intake(),headers={'Origin':ORIGIN})
    assert absent.status_code==401 and absent.json()['code']=='session_expired'


def test_history_names_resolve_for_history_only_without_mutating_snapshots(browser):
    client,conn=browser;session=login(client)
    created=post(client,session,'students.create',intake(name='طفل سجل واضح')).json()['id']
    with conn.cursor() as c:
        c.execute("SELECT change_id,before_state,after_state FROM record_changes ORDER BY change_id")
        original=deepcopy(c.fetchall())
    A.save_user(employee_name='قارئ السجل فقط',name='ux_history',password='1234',permissions=['history.view'])
    login(client,'ux_history','1234')
    snapshot=client.get('/api/snapshot').json()
    assert snapshot['students']==[] and snapshot['teachers']==[]
    account=next(e for e in snapshot['changes'] if e['type']=='monthly_accounts')
    assert account['subject']=='طفل سجل واضح'
    assert account['after_labels']['student_id']=='طفل سجل واضح'
    assert account['after']['student_id']==created
    with conn.cursor() as c:
        c.execute("SELECT change_id,before_state,after_state FROM record_changes ORDER BY change_id")
        assert c.fetchall()==original
