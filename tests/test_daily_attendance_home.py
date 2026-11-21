"""Today's home cards aggregate authorized registers without changing records."""
from datetime import date, datetime, timedelta
import json
import uuid
from zoneinfo import ZoneInfo

import pytest

import access_control as A
import attendance as AT
import db
import monthly_finance as F
from tests.test_access_control import access
from tests.test_attendance import save
from tests.test_live_pages_http import browser, intake, login, post


TODAY = date(2026, 11, 18)
SUMMARY_KEYS = {'present','absent','excused','total','attendance_rate','absence_rate',
                'roster_total','unmarked','complete'}


def freeze(monkeypatch, day=TODAY):
    monkeypatch.setattr(F,'today',lambda:day)


def student(client,session,**values):
    payload=intake(**{'name':'طالب حضور خاص','mode':'pay','registration':False,**values})
    response=post(client,session,'students.create',payload)
    assert response.status_code==200,response.text
    return response.json()['id']


def teacher(client,session,**values):
    details={'department_id':1,'national_id':uuid.uuid4().hex[:12],
             'full_name':'معلم حضور خاص','salary':'12000','hire_date':'2020-01-01',**values}
    response=post(client,session,'tools.change',dict(table='teachers',mode='create',values=details,
        confirmed=True,reason='تجهيز فحص مستقل',request_token=str(uuid.uuid4())))
    assert response.status_code==200,response.text
    return response.json()['id']


def daily(client,session,**payload):
    response=post(client,session,'attendance.daily',payload)
    assert response.status_code==200,response.text
    body=response.json()
    assert set(body)=={'date','refresh_after_ms','students','teachers'}
    assert type(body['refresh_after_ms']) is int and 1000<=body['refresh_after_ms']<=86401000
    for kind in ('students','teachers'):
        if body[kind] is not None:
            assert set(body[kind])==SUMMARY_KEYS
    return body


def summary(present=0,absent=0,excused=0,roster=0):
    counts=AT.percentages(dict(present=present,absent=absent,excused=excused))
    unmarked=roster-counts['total']
    return dict(counts,roster_total=roster,unmarked=unmarked,complete=unmarked==0)


def batch(client,session,kind,entries,on=None):
    response=post(client,session,'attendance.save',dict(kind=kind,date=str(on or F.today()),entries=[
        dict(person=person,status=status,revision=0,excuse='PRIVATE_MEDICAL_REASON' if status=='excused' else '')
        for person,status in entries]))
    assert response.status_code==200,response.text


def test_empty_rosters_are_distinct_from_zero_percent_attendance(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    body=daily(client,session)
    assert {k:v for k,v in body.items() if k!='refresh_after_ms'}==dict(date=str(TODAY),students=summary(),teachers=summary())
    direct=AT.daily(conn)
    assert direct['date']==TODAY and direct['students']['attendance_rate'] is None
    assert direct['students']['absence_rate'] is None and direct['students']['complete'] is True


def test_refresh_delay_uses_server_business_timezone_and_never_client_clock(access,monkeypatch):
    conn,*_=access
    clock=[None]
    class ServerClock(datetime):
        @classmethod
        def now(cls,tz=None):
            assert tz is F.BUSINESS_TZ
            return clock[0].astimezone(tz)
    monkeypatch.setattr(AT,'datetime',ServerClock)
    cases=[
        (datetime(2026,11,18,0,0,tzinfo=F.BUSINESS_TZ),86401000),
        # The same instant is02:00 on a Hawaiian clock,12:00 at school.
        (datetime(2026,11,18,2,0,tzinfo=ZoneInfo('Pacific/Honolulu')),43201000),
        (datetime(2026,11,18,23,59,59,999999,tzinfo=F.BUSINESS_TZ),1000),
    ]
    for instant,expected in cases:
        clock[0]=instant
        monkeypatch.setattr(F,'today',lambda:clock[0].astimezone(F.BUSINESS_TZ).date())
        result=AT.daily(conn,dict(date='2999-01-01',timezone='Asia/Tokyo',refresh_after_ms=0))
        assert result['date']==date(2026,11,18)
        assert type(result['refresh_after_ms']) is int
        assert result['refresh_after_ms']==expected
        assert 1000<=result['refresh_after_ms']<=86401000


def test_midnight_between_clock_and_business_date_keeps_refresh_short(access,monkeypatch):
    conn,*_=access
    events=[]
    class CrossingClock(datetime):
        @classmethod
        def now(cls,tz=None):
            assert tz is F.BUSINESS_TZ
            events.append('clock')
            return datetime(2026,11,18,23,59,59,750000,tzinfo=tz)
    def next_business_day():
        assert events==['clock']
        events.append('day')
        return date(2026,11,19)
    monkeypatch.setattr(AT,'datetime',CrossingClock)
    monkeypatch.setattr(F,'today',next_business_day)
    result=AT.daily(conn)
    assert events==['clock','day']
    assert result['date']==date(2026,11,19)
    assert result['refresh_after_ms']==1250
    assert result['students']==result['teachers']==summary()


def test_unmarked_people_never_become_absent_or_zero_percent(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    student(client,session);student(client,session);teacher(client,session)
    body=daily(client,session)
    assert body['students']==summary(roster=2)
    assert body['teachers']==summary(roster=1)
    assert body['students']['attendance_rate'] is None and body['students']['absence_rate'] is None
    assert body['students']['absent']==0 and body['students']['complete'] is False


def test_partial_register_counts_three_statuses_and_keeps_missing_separate(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    ids=[student(client,session) for _ in range(4)]
    teacher(client,session)
    batch(client,session,'students',zip(ids,('present','absent','excused')))
    body=daily(client,session)
    assert body['students']==summary(present=1,absent=1,excused=1,roster=4)
    assert body['students']['attendance_rate']==33.3 and body['students']['absence_rate']==66.7
    assert body['teachers']==summary(roster=1)
    encoded=json.dumps(body,ensure_ascii=False)
    assert not any(value in encoded for value in (*ids,'PRIVATE_MEDICAL_REASON','طالب حضور خاص'))


def test_all_sections_use_one_weighted_denominator_and_kinds_stay_separate(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    ids=[student(client,session) for _ in range(8)]
    department=post(client,session,'departments.create',dict(name='قسم حضور كبير'))
    assert department.status_code==200,department.text
    moved=post(client,session,'departments.transfer',dict(ids=ids[1:],department_id=department.json()['id']))
    assert moved.status_code==200,moved.text
    tids=[teacher(client,session) for _ in range(3)]
    batch(client,session,'students',[(ids[0],'absent'),*[(sid,'present') for sid in ids[1:]]])
    batch(client,session,'teachers',zip(tids,('present','absent','excused')))
    body=daily(client,session,department_id=1,kind='students')
    assert body['students']==summary(present=7,absent=1,roster=8)
    assert body['students']['attendance_rate']==87.5  # Never average section rates (0% and100%).
    assert body['teachers']==summary(present=1,absent=1,excused=1,roster=3)


def test_saved_corrections_cancellations_and_stale_revisions_refresh_today(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    sid=student(client,session);tid=teacher(client,session)
    assert save(client,session,'students',sid,'absent').status_code==200
    assert save(client,session,'teachers',tid,'present').status_code==200
    assert daily(client,session)['students']==summary(absent=1,roster=1)
    assert save(client,session,'students',sid,'excused',1,excuse='PRIVATE_CORRECTED_REASON').status_code==200
    assert daily(client,session)['students']==summary(excused=1,roster=1)
    assert save(client,session,'students',sid,'present',0).status_code==422
    assert daily(client,session)['students']==summary(excused=1,roster=1)
    assert save(client,session,'students',sid,'present',2).status_code==200
    assert daily(client,session)['students']==summary(present=1,roster=1)
    assert save(client,session,'students',sid,'',3).status_code==200
    body=daily(client,session)
    assert body['students']==summary(roster=1) and body['teachers']==summary(present=1,roster=1)
    assert save(client,session,'students',sid,'absent',4).status_code==200
    assert daily(client,session)['students']==summary(absent=1,roster=1)


def test_server_today_ignores_client_dates_and_other_days_records(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    today_student=student(client,session);past_student=student(client,session);tid=teacher(client,session)
    assert save(client,session,'students',today_student,'present').status_code==200
    assert save(client,session,'students',past_student,'absent',on=TODAY-timedelta(days=1)).status_code==200
    freeze(monkeypatch,TODAY+timedelta(days=1))
    assert save(client,session,'teachers',tid,'excused',on=TODAY+timedelta(days=1),excuse='فحص مستقبلي معزول').status_code==200
    freeze(monkeypatch)
    for requested in ('2020-01-01','2999-12-31','not-a-date'):
        body=daily(client,session,date=requested,kind='teachers',person=tid,department_id=999999)
        assert body['date']==str(TODAY)
        assert body['students']==summary(present=1,roster=2)
        assert body['teachers']==summary(roster=1)


def test_active_eligible_rosters_match_daily_read_and_exclude_future_or_archived_people(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    ids=[student(client,session) for _ in range(4)]
    tids=[teacher(client,session) for _ in range(4)]
    batch(client,session,'students',[(sid,'present') for sid in ids])
    batch(client,session,'teachers',[(tid,'absent') for tid in tids])
    with conn.cursor() as c:
        A.require(c,'students.edit')
        for sid,birth in zip(ids[:3],(None,TODAY,TODAY+timedelta(days=1))):
            c.execute('UPDATE students SET birth_date=%s WHERE student_id=%s',(birth,sid))
        A.require(c,'students.delete')
        c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(ids[3],))
        A.require(c,'teachers.edit')
        for tid,hire in zip(tids[:3],(None,TODAY,TODAY+timedelta(days=1))):
            c.execute('UPDATE teachers SET hire_date=%s WHERE national_id=%s',(hire,tid))
        A.require(c,'teachers.delete')
        c.execute('UPDATE teachers SET archived_at=now() WHERE national_id=%s',(tids[3],))
    body=daily(client,session)
    assert body['students']==summary(present=2,roster=2)
    assert body['teachers']==summary(absent=2,roster=2)
    for kind,expected in (('students',set(ids[:2])),('teachers',set(tids[:2]))):
        read=post(client,session,'attendance.read',dict(kind=kind,date=str(TODAY)))
        assert read.status_code==200,read.text
        assert {row['id'] for row in read.json()['items']}==expected
        assert len(read.json()['items'])==body[kind]['roster_total']


@pytest.mark.parametrize('permissions,visible', [
    (['student_attendance.view'],'students'),
    (['teacher_attendance.view'],'teachers'),
    (['student_attendance.create'],'students'),  # Existing grant validation includes view.
    ([],None),
    (['reports.view'],None),
])
def test_daily_kind_permissions_are_independent_and_never_leak_private_people(browser,monkeypatch,permissions,visible):
    client,_=browser;owner=login(client);freeze(monkeypatch)
    sid=student(client,owner);tid=teacher(client,owner)
    assert save(client,owner,'students',sid,'excused',excuse='PRIVATE_STUDENT_EXCUSE').status_code==200
    assert save(client,owner,'teachers',tid,'absent').status_code==200
    A.save_user(employee_name='قارئ الملخص اليومي',name='daily_reader',password='1234',permissions=permissions)
    session=login(client,'daily_reader','1234')
    response=post(client,session,'attendance.daily',dict(kind='students',date=str(TODAY)))
    if visible is None:
        assert response.status_code==403,response.text
    else:
        assert response.status_code==200,response.text
        body=response.json()
        assert body[visible]==summary(excused=1,roster=1) if visible=='students' else body[visible]==summary(absent=1,roster=1)
        assert body['teachers' if visible=='students' else 'students'] is None
        assert set(body[visible])==SUMMARY_KEYS
    assert not any(value in response.text for value in (sid,tid,'PRIVATE_STUDENT_EXCUSE','طالب حضور خاص','معلم حضور خاص'))


def business_state(conn):
    tables=('students','teachers','student_attendance','teacher_attendance','monthly_accounts','monthly_periods',
            'monthly_fees','monthly_receipts','monthly_allocations','monthly_audit','record_changes',
            'monthly_tariffs','app_users','app_schema_migrations')
    with conn.cursor() as c:
        result={}
        for table in tables:
            c.execute('SELECT * FROM '+table+' ORDER BY 1')
            result[table]=[dict(row) for row in c.fetchall()]
    return result


class CountedConnection:
    def __init__(self,conn):
        self.conn=conn
        self.queries=[]
    def cursor(self,*args,**kwargs):
        owner=self
        class Cursor:
            def __init__(self):self.inner=owner.conn.cursor(*args,**kwargs)
            def __enter__(self):self.inner.__enter__();return self
            def __exit__(self,*exc):return self.inner.__exit__(*exc)
            def execute(self,query,params=None):
                owner.queries.append(query.as_string(owner.conn) if hasattr(query,'as_string') else str(query))
                return self.inner.execute(query,params)
            def __getattr__(self,name):return getattr(self.inner,name)
        return Cursor()


def test_daily_read_is_constant_query_and_creates_no_attendance_or_financial_records(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    sid=student(client,session);teacher(client,session)
    assert save(client,session,'students',sid,'present').status_code==200
    counted=CountedConnection(conn)
    before=business_state(conn)
    small=AT.daily(counted)
    small_count=len(counted.queries)
    assert small['students']==summary(present=1,roster=1)
    assert small_count<=4 and all(q.lstrip().upper().startswith('SELECT') for q in counted.queries)
    assert business_state(conn)==before
    for _ in range(14):student(client,session)
    for _ in range(8):teacher(client,session)
    before=business_state(conn)
    with monkeypatch.context() as guarded:
        def forbidden():raise AssertionError('A summary opened an extra connection')
        guarded.setattr(db,'new_transaction_connection',forbidden)
        for _ in range(3):
            counted.queries.clear()
            result=AT.daily(counted)
            assert len(counted.queries)==small_count
            assert all(q.lstrip().upper().startswith('SELECT') for q in counted.queries)
            assert result['students']==summary(present=1,roster=15)
            assert result['teachers']==summary(roster=9)
    assert business_state(conn)==before
    for _ in range(2):daily(client,session)
    assert business_state(conn)==before


def test_revoked_session_cannot_reuse_a_previous_daily_summary_request(browser,monkeypatch):
    client,_=browser;owner=login(client);freeze(monkeypatch)
    student(client,owner)
    uid=A.save_user(employee_name='صلاحية مؤقتة',name='daily_revoked',password='1234',permissions=['student_attendance.view'])
    session=login(client,'daily_revoked','1234')
    assert daily(client,session)['students']==summary(roster=1)
    A.save_user(user_id=uid,employee_name='صلاحية مؤقتة',permissions=[],expected_version=1)
    denied=post(client,session,'attendance.daily',{})
    assert denied.status_code==403,denied.text
    assert 'roster_total' not in denied.text and 'attendance_rate' not in denied.text
