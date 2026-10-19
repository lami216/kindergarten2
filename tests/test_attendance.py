"""Actual PostgreSQL: placement, audit, permission boundaries and conflicting edits."""
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
import access_control as A
import monthly_finance as F
from tests.test_live_pages_http import browser,access,login,post,intake
from tests.test_access_control import PASSWORD


def student(client,session):
    r=post(client,session,'students.create',intake(mode='pay',registration=False))
    assert r.status_code==200,r.text
    return r.json()['id']


def teacher(client,session,**values):
    payload=dict(table='teachers',mode='create',values=dict(department_id=1,national_id=uuid.uuid4().hex[:12],full_name='معلم اختبار',salary='12000',hire_date='2020-01-01',**values),confirmed=True,reason='إضافة اختبار',request_token=str(uuid.uuid4()))
    r=post(client,session,'tools.change',payload);assert r.status_code==200,r.text
    return r.json()['id']


def save(client,session,kind,ident,status='present',revision=0,on=None,excuse=''):
    return post(client,session,'attendance.save',dict(kind=kind,date=str(on or F.today()),entries=[dict(person=ident,status=status,revision=revision,excuse=excuse)]))


def test_registration_requires_a_real_department_and_rolls_back(browser):
    client,conn=browser;s=login(client)
    for value in (None,99999,True):
        r=post(client,s,'students.create',intake(department_id=value))
        assert r.status_code==422,r.text
    assert client.get('/api/snapshot').json()['students']==[]
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM parents');assert c.fetchone()['n']==0
    ident=student(client,s)
    with conn.cursor() as c:
        c.execute('SELECT department_id FROM student_departments WHERE student_id=%s',(ident,));assert c.fetchone()['department_id']==1


def test_three_states_percentages_excuses_and_unmarked_days(browser):
    client,conn=browser;s=login(client);ident=student(client,s)
    for i,status in enumerate(('present','absent','excused')):
        assert save(client,s,'students',ident,status,on=F.today()-timedelta(days=i),excuse='إذن ولي الأمر' if i==2 else '').status_code==200
    result=post(client,s,'attendance.read',dict(kind='students',person=ident)).json()
    assert result['summary']==dict(present=1,absent=1,excused=1,total=3,attendance_rate=33.3,absence_rate=66.7)
    assert any(r['excuse']=='إذن ولي الأمر' for r in result['items'])
    current=client.get('/api/snapshot').json();assert current['attendance']['students'][ident]['total']==3
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n FROM record_changes WHERE table_name='student_attendance'");assert c.fetchone()['n']==3


@pytest.mark.parametrize('case',['excuse','future','duplicate','unknown'])
def test_invalid_batch_has_no_partial_writes(browser,case):
    client,conn=browser;s=login(client);ident=student(client,s)
    entries=[dict(person=ident,status='present',revision=0,excuse='')]
    on=F.today()
    if case=='excuse':entries.append(dict(person=student(client,s),status='excused',revision=0,excuse=' '))
    if case=='future':on+=timedelta(days=1)
    if case=='duplicate':entries*=2
    if case=='unknown':entries.append(dict(person='missing',status='present',revision=0,excuse=''))
    r=post(client,s,'attendance.save',dict(kind='students',date=str(on),entries=entries));assert r.status_code==422,r.text
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM student_attendance');assert c.fetchone()['n']==0


def test_correction_cancellation_and_stale_revision(browser):
    client,conn=browser;s=login(client);ident=student(client,s)
    assert save(client,s,'students',ident).status_code==200
    assert save(client,s,'students',ident,'absent',0).status_code==422
    assert save(client,s,'students',ident,'excused',1,excuse='موعد طبي').status_code==200
    assert save(client,s,'students',ident,'',2).status_code==200
    result=post(client,s,'attendance.read',dict(kind='students',person=ident)).json()
    assert result['summary']['attendance_rate'] is None and result['items']==[]
    with conn.cursor() as c:
        c.execute("SELECT action FROM record_changes WHERE table_name='student_attendance' ORDER BY change_id");assert [r['action'] for r in c.fetchall()]==['created','updated','cancelled']
    assert save(client,s,'students',ident,'present',3).status_code==200


def test_simultaneous_corrections_accept_one_and_reject_one(browser):
    client,conn=browser;s=login(client);ident=student(client,s)
    assert save(client,s,'students',ident).status_code==200
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(save,client,s,'students',ident,'absent',1)
        b=pool.submit(save,client,s,'students',ident,'excused',1,excuse='عذر')
        codes=[a.result().status_code,b.result().status_code]
    assert sorted(codes)==[200,422]


def test_teacher_register_separate_and_payroll_is_unchanged(browser):
    client,conn=browser;s=login(client);tid=teacher(client,s);sid=student(client,s)
    assert save(client,s,'teachers',tid,'absent').status_code==200
    assert save(client,s,'students',sid).status_code==200
    result=client.get('/api/snapshot').json()
    assert result['attendance']['students'][sid]['present']==1
    assert result['attendance']['teachers'][tid]['absent']==1
    assert result['teachers'][0]['salary']==12000
    assert result['overview']['salary_cash']==0


def test_department_creation_with_teacher_is_atomic_and_retryable(browser):
    client,conn=browser;s=login(client)
    payload=dict(table='teachers',mode='create',new_department='قسم جديد من المعلم',values=dict(full_name='معلم بقسمه',national_id='NEW-1',salary='-1'),confirmed=True,reason='تسجيل',request_token=str(uuid.uuid4()))
    r=post(client,s,'tools.change',payload);assert r.status_code==422,r.text
    assert len(client.get('/api/snapshot').json()['departments'])==1
    payload['values']['salary']='5000'
    r=post(client,s,'tools.change',payload);assert r.status_code==200,r.text
    duplicate=post(client,s,'tools.change',payload);assert duplicate.status_code==200 and duplicate.json()['id']==r.json()['id']
    data=client.get('/api/snapshot').json();assert len(data['teachers'])==1 and len(data['departments'])==2
    assert data['teachers'][0]['department_id']==data['departments'][1]['id']


def test_attendance_view_only_and_creation_permissions_are_enforced(browser):
    client,conn=browser;owner=login(client);ident=student(client,owner)
    A.save_user(employee_name='مشاهد حضور',name='attendance_reader',password='1234',permissions=['student_attendance.view'])
    worker=login(client,'attendance_reader','1234')
    assert post(client,worker,'attendance.read',dict(kind='students',date=str(F.today()))).status_code==200
    assert save(client,worker,'students',ident).status_code==403
    assert post(client,worker,'attendance.read',dict(kind='teachers',date=str(F.today()))).status_code==403
    private=client.get('/api/snapshot').json()
    assert private['teachers']==[] and private['students']==[] and private['receipts']==[] and private['families']==[]
    assert 'students.view' not in A.validate_permissions(['student_attendance.view'])


def test_inline_department_requires_its_own_permission(browser):
    client,conn=browser;s=login(client)
    A.save_user(employee_name='مسجل معلمين',name='teacher_creator',password='1234',permissions=['teachers.create'])
    worker=login(client,'teacher_creator','1234')
    result=post(client,worker,'tools.change',dict(table='teachers',mode='create',values=dict(full_name='معلم',national_id='T-1',salary='5000'),new_department='غير مصرح',confirmed=True,reason='تجربة',request_token=str(uuid.uuid4())))
    assert result.status_code==403,result.text
    assert teacher(client,worker)


def test_historical_department_survives_transfer_and_archive(browser):
    client,conn=browser;s=login(client);ident=student(client,s)
    assert save(client,s,'students',ident).status_code==200
    section=post(client,s,'departments.create',dict(name='القسم الثاني')).json()['id']
    assert post(client,s,'departments.transfer',dict(ids=[ident],department_id=section)).status_code==200
    result=post(client,s,'attendance.read',dict(kind='students',person=ident)).json();assert result['items'][0]['department_name']=='قسم الاختبار'
    child=client.get('/api/snapshot').json()['students'][0]
    archive=post(client,s,'records.change',dict(type='students',id=ident,mode='cancel',reason='أرشفة',revision=child['revision'],confirmed=True,values={}))
    assert archive.status_code==200,archive.text
    assert save(client,s,'students',ident,'absent',on=F.today()-timedelta(days=1)).status_code==422
    assert save(client,s,'students',ident,'excused',1,excuse='تصحيح تاريخي').status_code==200


def test_department_with_teacher_needs_valid_destination(browser):
    client,conn=browser;s=login(client);tid=teacher(client,s)
    dept=client.get('/api/snapshot').json()['departments'][0]
    payload=dict(type='departments',id=dept['id'],mode='cancel',revision=dept['revision'],reason='تنظيم',confirmed=True,values={})
    for destination in (None,99999):
        r=post(client,s,'records.change',{**payload,'destination':destination});assert r.status_code==422,r.text
    target=post(client,s,'departments.create',dict(name='بديل المعلمين')).json()['id']
    r=post(client,s,'records.change',{**payload,'destination':target});assert r.status_code==200,r.text
    assert client.get('/api/snapshot').json()['teachers'][0]['department_id']==target


def test_upgrade_from_15_adds_registers_without_touching_existing_cash(browser):
    client,conn=browser;s=login(client);ident=student(client,s)
    before=client.get('/api/snapshot').json()
    import schema_migrations as M
    with conn.cursor() as c:
        c.execute('DROP TABLE student_attendance,teacher_attendance')
        c.execute('ALTER TABLE teachers DROP COLUMN department_id')
        c.execute('DELETE FROM app_schema_migrations WHERE version=16')
        c.execute('INSERT INTO app_schema_migrations(version) VALUES(15) ON CONFLICT DO NOTHING')
    assert M.upgrade(conn)
    after=client.get('/api/snapshot').json()
    assert before['students']==after['students'] and before['overview']==after['overview']
    assert after['attendance']=={'students':{},'teachers':{}}
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n FROM pg_class WHERE relname IN ('student_attendance','teacher_attendance') AND relnamespace=current_schema()::regnamespace AND relrowsecurity")
        assert c.fetchone()['n']==2


def test_historical_roster_dates_and_minimal_attendance_view(browser):
    client,conn=browser;s=login(client);sid=student(client,s);tid=teacher(client,s)
    past=post(client,s,'attendance.read',dict(kind='students',date='2021-01-01'))
    assert past.status_code==200 and past.json()['items']==[]
    past=post(client,s,'attendance.read',dict(kind='teachers',date='2019-01-01'))
    assert past.status_code==200 and past.json()['items']==[]
    A.save_user(employee_name='مسجل حضور فقط',name='attendance_only',password='1234',permissions=['teacher_attendance.create'])
    worker=login(client,'attendance_only','1234')
    roster=post(client,worker,'attendance.read',dict(kind='teachers',date=str(F.today())))
    assert roster.status_code==200,roster.text
    assert all('salary' not in r and 'hire_date' not in r and 'address' not in r for r in roster.json()['items'])
    assert save(client,worker,'teachers',tid).status_code==200
    private=client.get('/api/snapshot').json()
    assert private['students']==[] and private['teachers']==[] and private['overview'] is None


def test_attendance_portrait_is_private_scoped_and_removed_with_archive(browser):
    import base64
    from tests.test_student_photos import picture
    client,conn=browser;owner=login(client);ident=student(client,owner)
    uploaded=post(client,owner,'photos.save',dict(student=ident,revision=0,photo=base64.b64encode(picture()).decode(),reason='صورة اختبار'))
    assert uploaded.status_code==200,uploaded.text
    A.save_user(employee_name='مسجل حضور',name='portrait_reader',password='1234',permissions=['student_attendance.view'])
    worker=login(client,'portrait_reader','1234')
    roster=post(client,worker,'attendance.read',dict(kind='students',date=str(F.today()))).json()
    child=next(r for r in roster['items'] if r['id']==ident)
    url=child['photo']['data'];assert child['photo']['revision']==1 and url.startswith('/api/attendance-photo/')
    assert not any(k in child for k in ('health','address','account','phone','image_data'))
    image=client.get(url)
    assert image.status_code==200 and image.headers['content-type']=='image/jpeg' and image.content.startswith(b'\xff\xd8')
    assert image.headers['cache-control']=='no-store'
    assert client.get('/api/photo/'+ident).status_code==403
    assert client.get('/api/snapshot').json()['students']==[]
    assert client.get('/api/attendance-photo/missing').status_code==404
    owner=login(client)
    assert post(client,owner,'photos.save',dict(student=ident,revision=1,remove=True,confirmed=True,reason='حذف الصورة')).status_code==200
    assert client.get(url).status_code==404
    removed=post(client,owner,'attendance.read',dict(kind='students',date=str(F.today()))).json()['items'][0]
    assert removed['photo']=={'revision':2,'data':None}
    assert post(client,owner,'photos.save',dict(student=ident,revision=2,photo=base64.b64encode(picture()).decode(),reason='إعادة الصورة')).status_code==200
    child=client.get('/api/snapshot').json()['students'][0]
    archived=post(client,owner,'records.change',dict(type='students',id=ident,mode='cancel',revision=child['revision'],reason='أرشفة اختبار',confirmed=True,values={}))
    assert archived.status_code==200,archived.text
    worker=login(client,'portrait_reader','1234')
    assert client.get(url).status_code==404
    assert post(client,worker,'attendance.read',dict(kind='students',date=str(F.today()))).json()['items']==[]
    owner=login(client)
    A.save_user(employee_name='حضور المعلمين',name='teacher_portraits',password='1234',permissions=['teacher_attendance.view'])
    login(client,'teacher_portraits','1234')
    assert client.get(url).status_code==403
    client.cookies.clear()
    assert client.get(url).status_code==401
