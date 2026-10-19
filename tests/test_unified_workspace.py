"""Real HTTP + PostgreSQL scenarios for the single owner workspace."""
from datetime import timedelta
from io import BytesIO
import uuid
import pytest
from openpyxl import load_workbook
from tests.test_live_pages_http import browser,login,post,intake
from tests.test_access_control import access,PASSWORD
import access_control as A
import monthly_finance as F
import records as R


def test_restore_waive_rearchive_preserves_absence_cutoff_and_cash(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=True,gilet=True)).json()['id']
    import account_records as AR
    with conn.cursor() as c:
        c.execute('SELECT * FROM monthly_accounts WHERE student_id=%s',(sid,));account=dict(c.fetchone())
    AR.change_account(sid,actor='owner',reason='تهيئة عينة قديمة',start_date=F.today()-timedelta(days=90),status='regular',expected=R.revision(account))
    cutoff=F.today()-timedelta(days=45)
    # Reproduce a legacy archived debtor. Current normal archive correctly refuses it.
    with conn.cursor() as c:
        A.require(c,'students.delete')
        c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(sid,))
        A.require(c,'accounts.edit')
        c.execute('UPDATE monthly_accounts SET archived_at=now(),departure_on=%s WHERE student_id=%s',(cutoff,sid))
    before=client.get('/api/snapshot').json();s=next(s for s in before['students'] if s['id']==sid)
    assert s['cancelled'] and s['account']['due']>0
    payload=dict(student=sid,revision=s['revision'],account_revision=s['account_revision'],reason='استرجاع لمراجعة الدين',confirmed=True)
    restored=post(client,session,'students.restore',payload);assert restored.status_code==200,restored.text
    assert post(client,session,'students.restore',payload).status_code==422
    data=client.get('/api/snapshot').json();s=next(s for s in data['students'] if s['id']==sid)
    assert not s['cancelled'] and s['paused']
    assert s['account']['due']==next(s for s in before['students'] if s['id']==sid)['account']['due']
    waiver=dict(student=sid,revision=s['ledger_revision'],due=s['account']['due'],reason='إسقاط موثق دون قبض',confirmed=True,request_token=str(uuid.uuid4()))
    wrong=post(client,session,'students.waive',{**waiver,'due':waiver['due']+1});assert wrong.status_code==422
    saved=post(client,session,'students.waive',waiver);assert saved.status_code==200,saved.text
    assert saved.json()['waived']==waiver['due']
    replay=post(client,session,'students.waive',waiver);assert replay.status_code==200 and not replay.json()['created']
    data=client.get('/api/snapshot').json();s=next(s for s in data['students'] if s['id']==sid)
    assert s['account']['due']==0 and data['overview']['total_cash']==before['overview']['total_cash']
    # Cancelling the subscription through tools must also retain the absence cutoff.
    stopped=post(client,session,'tools.change',dict(table='monthly_accounts',id=sid,mode='cancel',revision=s['account_revision'],values={},reason='إيقاف اشتراك بعد المراجعة',confirmed=True))
    assert stopped.status_code==200,stopped.text
    stopped_data=client.get('/api/snapshot').json()
    assert next(x for x in stopped_data['students'] if x['id']==sid)['account']['due']==0
    assert stopped_data['overview']['total_cash']==before['overview']['total_cash']
    cancel=post(client,session,'records.change',dict(type='students',id=sid,mode='cancel',reason='أرشفة بعد التسوية',revision=s['revision'],confirmed=True,values={}))
    assert cancel.status_code==200,cancel.text
    final=client.get('/api/snapshot').json();s=next(s for s in final['students'] if s['id']==sid)
    assert s['cancelled'] and s['account']['due']==0
    with conn.cursor() as c:
        c.execute('SELECT departure_on FROM monthly_accounts WHERE student_id=%s',(sid,));assert c.fetchone()['departure_on']==cutoff
        c.execute('SELECT COUNT(*) AS n FROM record_changes WHERE table_name=%s AND record_key=%s AND action=%s',('students',sid,'updated'));assert c.fetchone()['n']>0


def test_unified_tools_permissions_reports_literal_export_and_fee_revision(browser):
    client,conn=browser;owner=login(client)
    post(client,owner,'students.create',intake(name='=1+1'))
    fee=client.get('/api/fees.read').json()
    change=post(client,owner,'fees.save',{**fee['values'],'tuition':'5000','revision':fee['revision'],'reason':'تغيير رسوم جديد','confirmed':True})
    assert change.status_code==200,change.text
    stale=post(client,owner,'fees.save',{**fee['values'],'revision':fee['revision'],'reason':'نافذة قديمة','confirmed':True});assert stale.status_code==422
    dates=dict(start=str(F.today().replace(day=1)),end=str(F.today()))
    export=post(client,owner,'reports.export',dict(kind='students',**dates))
    assert export.status_code==200,export.text
    book=load_workbook(BytesIO(export.content));assert any(c.value=='=1+1' and c.data_type=='s' for row in book.active for c in row);book.close()
    A.save_user(employee_name='تقارير إجمالية',name='aggregate_only',password=PASSWORD,permissions=['reports.view'])
    restricted=login(client,'aggregate_only')
    assert post(client,restricted,'reports.read',dict(kind='finance',**dates)).status_code==200
    for kind in ('students','debt','salaries','expenses'):
        assert post(client,restricted,'reports.read',dict(kind=kind,**dates)).status_code==403
    assert client.get('/api/teachers.options').status_code==403
    assert client.get('/api/download/backup').status_code==403
    assert post(client,restricted,'tools.list',dict(table='app_users')).status_code==422
    assert post(client,restricted,'tools.list',dict(table='parents')).status_code==403


def test_teacher_asset_idempotence_payroll_corrections_and_plain_search(browser):
    client,conn=browser;session=login(client)
    teacher=dict(table='teachers',mode='create',values=dict(department_id=1,national_id='123456',full_name='معلمة بنفس الاسم',salary='2000'),reason='إضافة معلمة',confirmed=True,request_token=str(uuid.uuid4()))
    first=post(client,session,'tools.change',teacher);assert first.status_code==200,first.text
    retry=post(client,session,'tools.change',teacher);assert retry.status_code==200 and str(retry.json()['id'])==str(first.json()['id'])
    second=post(client,session,'tools.change',{**teacher,'values':{**teacher['values'],'national_id':'999999'},'request_token':str(uuid.uuid4())});assert second.status_code==200,second.text
    options=client.get('/api/teachers.options').json();assert len(options)==2 and len({r['id'] for r in options})==2
    salary=dict(teacher=first.json()['id'],kind='salary',month=str(F.today())[:7],date=str(F.today()),base='2000',bonus='500',deductions='100',confirmed=True,request_token=str(uuid.uuid4()))
    saved=post(client,session,'payroll.save',salary);assert saved.status_code==200,saved.text
    assert post(client,session,'payroll.save',salary).json()['created'] is False
    assert post(client,session,'tools.list',dict(table='teacher_payments',query='(')).status_code==200
    item=post(client,session,'tools.list',dict(table='teacher_payments')).json()['items'][0]
    assert item['cash']==2400
    void=post(client,session,'tools.change',dict(table='teacher_payments',id=item['id'],revision=item['revision'],mode='void_document',values={},reason='إلغاء مستند دون رد النقد',confirmed=True))
    assert void.status_code==200,void.text
    item=post(client,session,'tools.list',dict(table='teacher_payments')).json()['items'][0]
    assert item['cash']==2400 and item['document']=='cancelled'
    removed=post(client,session,'tools.change',dict(table='teacher_payments',id=item['id'],revision=item['revision'],mode='cancel',values={},reason='إزالة إدخال نقد خاطئ',confirmed=True))
    assert removed.status_code==200,removed.text
    assert client.get('/api/snapshot').json()['overview']['salary_cash']==0
    asset=dict(table='assets',mode='create',values=dict(item_name='طاولة',category='أثاث',quantity='2',unit_cost='100'),reason='جرد فقط',confirmed=True,request_token=str(uuid.uuid4()))
    before=client.get('/api/snapshot').json()['overview']['expenses']
    a=post(client,session,'tools.change',asset);assert a.status_code==200,a.text
    assert post(client,session,'tools.change',asset).status_code==200
    assert client.get('/api/snapshot').json()['overview']['expenses']==before
    assert post(client,session,'tools.list',dict(table='assets')).json()['total']==1


def test_pickups_stale_edits_expense_settlement_and_archived_setup(browser):
    client,conn=browser;session=login(client)
    sid=post(client,session,'students.create',intake(mode='pay',registration=False)).json()['id']
    s=next(s for s in client.get('/api/snapshot').json()['students'] if s['id']==sid)
    edit=dict(id=sid,revision=s['revision'],parent_revision=s['parent_revision'],values=dict(pickups=[dict(name='خال الطفل',phone='22334455',relation='خال')]),reason='مخول استلام')
    saved=post(client,session,'students.edit',edit);assert saved.status_code==200,saved.text
    assert post(client,session,'students.edit',{**edit,'values':{'address':'نافذة قديمة'}}).status_code==422
    current=next(s for s in client.get('/api/snapshot').json()['students'] if s['id']==sid)
    assert current['pickups'][0]['name']=='خال الطفل'
    invalid=post(client,session,'students.edit',{**edit,'revision':current['revision'],'values':dict(pickups=[dict(name='ناقص',phone='')])})
    assert invalid.status_code==422
    exp=post(client,session,'expenses.create',dict(category='إصلاح',amount='1200',paid='1000',date=str(F.today()),request_token=str(uuid.uuid4())));assert exp.status_code==200,exp.text
    e=client.get('/api/snapshot').json()['expenses'][0]
    settle=dict(id=e['id'],amount='100',date=str(F.today()),reason='دفع إضافي',revision=e['revision'],confirmed=True,request_token=str(uuid.uuid4()))
    cash_before=client.get('/api/snapshot').json()['overview']['expenses']
    payment=post(client,session,'expenses.settle',settle);assert payment.status_code==200,payment.text
    assert post(client,session,'expenses.settle',settle).status_code==200
    assert post(client,session,'expenses.settle',{**settle,'request_token':str(uuid.uuid4())}).status_code==422
    after=client.get('/api/snapshot').json();assert after['overview']['expenses']==cash_before+100
    current=next(s for s in after['students'] if s['id']==sid)
    archived=post(client,session,'records.change',dict(type='students',id=sid,mode='cancel',reason='أرشفة',revision=current['revision'],confirmed=True,values={}))
    assert archived.status_code==200,archived.text
    setup=post(client,session,'accounts.setup',dict(student=sid,start=str(F.today()),status='regular',confirmed=True))
    assert setup.status_code==422


def test_upgrade_14_to_current_preserves_ledger_and_secures_request_table(browser):
    client,conn=browser;session=login(client)
    assert post(client,session,'students.create',intake()).status_code==200
    before=client.get('/api/snapshot').json()
    import schema_migrations as M,db
    with conn.cursor() as c:
        c.execute('DROP TABLE app_tool_requests')
        c.execute('DELETE FROM app_schema_migrations WHERE version>=15')
        c.execute('INSERT INTO app_schema_migrations(version) VALUES(14) ON CONFLICT DO NOTHING')
    with pytest.raises(M.SchemaNotReady):db.assert_schema_ready(conn)
    M.upgrade(conn)
    db.assert_schema_ready(conn)
    after=client.get('/api/snapshot').json()
    assert before['overview']==after['overview'] and before['students']==after['students']
    with conn.cursor() as c:
        c.execute("SELECT relrowsecurity,relacl FROM pg_class WHERE oid='app_tool_requests'::regclass")
        row=c.fetchone();assert row['relrowsecurity']
        c.execute("SELECT COUNT(*) AS n FROM pg_class r CROSS JOIN LATERAL aclexplode(COALESCE(r.relacl,acldefault('r',r.relowner))) a WHERE r.oid='app_tool_requests'::regclass AND a.grantee=0")
        assert c.fetchone()['n']==0


def test_separate_expense_delete_and_teacher_asset_create_permissions(browser):
    client,conn=browser;owner=login(client)
    exp=post(client,owner,'expenses.create',dict(category='مصروف مراجعة',amount='100',paid='100',date=str(F.today()),request_token=str(uuid.uuid4()))).json()
    expense=client.get('/api/snapshot').json()['expenses'][0]
    A.save_user(employee_name='معدل مصاريف',name='expense_editor',password=PASSWORD,permissions=['expenses.edit'])
    A.save_user(employee_name='ملغي مصاريف',name='expense_deleter',password=PASSWORD,permissions=['expenses.delete'])
    editor=login(client,'expense_editor')
    cancel=dict(type='expenses',id=exp['id'],mode='cancel',revision=expense['revision'],reason='إلغاء إدخال خاطئ',confirmed=True,values={},request_token=str(uuid.uuid4()))
    assert post(client,editor,'records.change',cancel).status_code==403
    deleter=login(client,'expense_deleter')
    result=post(client,deleter,'records.change',cancel);assert result.status_code==200,result.text
    login(client)
    A.save_user(employee_name='مسجل معلمات وتجهيزات',name='tools_creator',password=PASSWORD,permissions=['teachers.create','assets.create'])
    A.save_user(employee_name='معدل معلمات',name='tools_editor',password=PASSWORD,permissions=['teachers.edit'])
    creator=login(client,'tools_creator')
    teacher=dict(table='teachers',mode='create',values=dict(department_id=1,national_id='C-111',full_name='معلمة بصلاحية إضافة',salary='2000'),reason='إضافة مصرح بها',confirmed=True,request_token=str(uuid.uuid4()))
    result=post(client,creator,'tools.change',teacher);assert result.status_code==200,result.text
    item=post(client,creator,'tools.list',dict(table='teachers')).json()['items'][0]
    assert post(client,creator,'tools.change',dict(table='teachers',id=item['id'],mode='edit',revision=item['revision'],values={'salary':'3000'},reason='غير مصرح',confirmed=True)).status_code==403
    asset=post(client,creator,'tools.change',dict(table='assets',mode='create',values=dict(item_name='كرسي',category='أثاث',quantity='1',unit_cost='100'),reason='إضافة جرد مصرح',confirmed=True,request_token=str(uuid.uuid4())))
    assert asset.status_code==200,asset.text
    editor=login(client,'tools_editor')
    assert post(client,editor,'tools.change',{**teacher,'request_token':str(uuid.uuid4())}).status_code==403
