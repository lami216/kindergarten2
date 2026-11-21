"""Historical person-day percentages in each authorized attendance register."""
from datetime import date, timedelta
import json

import pytest

import access_control as A
import attendance as AT
import db
import monthly_finance as F
import records as R
from tests.test_access_control import access
from tests.test_attendance import save
from tests.test_daily_attendance_home import (
    TODAY, CountedConnection, batch, business_state, freeze, student, teacher,
)
from tests.test_live_pages_http import browser, login, post


SUMMARY_KEYS={'present','absent','excused','total','attendance_rate','absence_rate'}


def stats(present=0,absent=0,excused=0):
    return AT.percentages(dict(present=present,absent=absent,excused=excused))


def overview(client,session,kind='students',on=None,department=None):
    response=post(client,session,'attendance.overview',dict(kind=kind,date=str(on or F.today()),department_id=department))
    assert response.status_code==200,response.text
    body=response.json()
    assert set(body)=={'kind','date','department','periods'}
    assert body['kind']==kind and body['date']==str(on or F.today())
    assert set(body['periods'])=={'day','week','month'}
    for period in body['periods'].values():
        assert set(period)=={'start','end','summary','recorded_days'}
        assert set(period['summary'])==SUMMARY_KEYS
        assert type(period['recorded_days']) is int
    return body


def test_empty_and_unmarked_rosters_have_no_assumed_absence(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    for kind in ('students','teachers'):
        body=overview(client,session,kind)
        assert body['department'] is None
        for period in body['periods'].values():
            assert period['summary']==stats() and period['recorded_days']==0
            assert period['summary']['attendance_rate'] is None and period['summary']['absence_rate'] is None
    student(client,session);teacher(client,session)
    assert overview(client,session)['periods']['month']['summary']==stats()
    assert overview(client,session,'teachers')['periods']['month']['summary']==stats()
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM student_attendance')
        assert c.fetchone()['n']==0


def test_weighted_saved_person_days_are_not_average_people_or_sections(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    one=student(client,session);two=student(client,session);student(client,session)
    department=post(client,session,'departments.create',dict(name='قسم ثان للتقرير'))
    assert department.status_code==200,department.text
    dep=department.json()['id']
    moved=post(client,session,'departments.transfer',dict(ids=[two],department_id=dep))
    assert moved.status_code==200,moved.text
    for offset in (2,1,0):
        assert save(client,session,'students',one,'present',on=TODAY-timedelta(days=offset)).status_code==200
    assert save(client,session,'students',two,'absent').status_code==200
    t1=teacher(client,session);t2=teacher(client,session)
    assert save(client,session,'teachers',t1,'absent').status_code==200
    assert save(client,session,'teachers',t2,'excused',excuse='PRIVATE_OVERVIEW_EXCUSE').status_code==200
    body=overview(client,session)
    assert body['periods']['day']['summary']==stats(present=1,absent=1)
    for key in ('week','month'):
        assert body['periods'][key]['summary']==stats(present=3,absent=1)
        assert body['periods'][key]['summary']['attendance_rate']==75.0
        assert body['periods'][key]['recorded_days']==3
    assert overview(client,session,department=1)['periods']['week']['summary']==stats(present=3)
    assert overview(client,session,department=str(dep))['periods']['week']['summary']==stats(absent=1)
    teachers=overview(client,session,'teachers')
    assert teachers['periods']['day']['summary']==stats(absent=1,excused=1)
    assert teachers['periods']['day']['summary']['absence_rate']==100.0
    assert teachers['periods']['week']['recorded_days']==1


@pytest.mark.parametrize('selected,week_start,month_start', [
    (date(2026,11,18),date(2026,11,16),date(2026,11,1)),
    (date(2027,1,3),date(2026,12,28),date(2027,1,1)),
    (date(2024,3,1),date(2024,2,26),date(2024,3,1)),
])
def test_inclusive_day_monday_week_and_month_windows_ignore_later_records(browser,monkeypatch,selected,week_start,month_start):
    client,_=browser;session=login(client);freeze(monkeypatch,selected+timedelta(days=1))
    sid=student(client,session)
    marks={month_start-timedelta(days=1):'absent',week_start-timedelta(days=1):'excused',
           min(week_start,month_start):'present',month_start:'present',week_start:'present',
           selected-timedelta(days=1):'excused',selected:'present',selected+timedelta(days=1):'absent'}
    for on,status in sorted(marks.items()):
        saved=save(client,session,'students',sid,status,on=on,excuse='إذن موثق' if status=='excused' else '')
        assert saved.status_code==200,saved.text
    body=overview(client,session,on=selected)
    for key,start in (('day',selected),('week',week_start),('month',month_start)):
        p=body['periods'][key]
        assert p['start']==str(start) and p['end']==str(selected)
        included=[status for on,status in marks.items() if start<=on<=selected]
        assert p['summary']==stats(**{status:included.count(status) for status in AT.STATUSES})
        assert p['recorded_days']==len(included)
    assert body['periods']['day']['summary']==stats(present=1)


def test_correction_and_cancellation_update_every_relevant_period_without_missing_absences(browser,monkeypatch):
    client,_=browser;session=login(client);freeze(monkeypatch)
    sid=student(client,session);first=TODAY.replace(day=1);yesterday=TODAY-timedelta(days=1)
    assert save(client,session,'students',sid,'present',on=first).status_code==200
    assert save(client,session,'students',sid,'excused',on=yesterday,excuse='زيارة طبية').status_code==200
    assert save(client,session,'students',sid,'absent').status_code==200
    assert overview(client,session)['periods']['month']['summary']==stats(present=1,absent=1,excused=1)
    assert save(client,session,'students',sid,'',1,on=first).status_code==200
    assert save(client,session,'students',sid,'present',1,on=yesterday).status_code==200
    assert save(client,session,'students',sid,'absent',1,on=yesterday).status_code==422
    body=overview(client,session)
    assert body['periods']['month']['summary']==stats(present=1,absent=1)
    assert body['periods']['month']['recorded_days']==2
    assert save(client,session,'students',sid,'',1).status_code==200
    body=overview(client,session)
    assert body['periods']['day']['summary']==stats() and body['periods']['day']['recorded_days']==0
    assert body['periods']['week']['summary']==stats(present=1)
    assert body['periods']['month']['recorded_days']==1


def test_archived_people_and_sections_retain_saved_historical_placement(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    sid=student(client,session);past=TODAY-timedelta(days=2)
    assert save(client,session,'students',sid,'present',on=past).status_code==200
    created=post(client,session,'departments.create',dict(name='قسم بعد النقل'))
    assert created.status_code==200,created.text
    dep=created.json()['id']
    assert post(client,session,'departments.transfer',dict(ids=[sid],department_id=dep)).status_code==200
    assert save(client,session,'students',sid,'excused',excuse='PRIVATE_ARCHIVED_EXCUSE').status_code==200
    R.cancel('students',sid,actor='owner',reason='أرشفة بعد الحضور')
    with conn.cursor() as c:
        A.require(c,'departments.delete')
        c.execute('UPDATE school_departments SET archived_at=now() WHERE department_id=1')
    body=overview(client,session)
    assert body['periods']['day']['summary']==stats(excused=1)
    assert body['periods']['week']['summary']==stats(present=1,excused=1)
    old=overview(client,session,department=1)
    assert old['department']==1 and old['periods']['day']['summary']==stats()
    assert old['periods']['week']['summary']==stats(present=1)
    assert overview(client,session,department=dep)['periods']['week']['summary']==stats(excused=1)
    assert AT.daily(conn)['students']['roster_total']==0  # Home deliberately uses active roster.
    encoded=json.dumps(body,ensure_ascii=False)
    assert sid not in encoded and 'PRIVATE_ARCHIVED_EXCUSE' not in encoded and 'طالب حضور خاص' not in encoded


def test_invalid_dates_kinds_and_department_values_are_recoverable_and_read_only(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    original=business_state(conn)
    base=dict(kind='students',date=str(TODAY))
    for invalid in (None,True,20261118,[],{},'not-a-date','2026-02-30','1989-12-31',str(TODAY+timedelta(days=1))):
        rejected=post(client,session,'attendance.overview',{**base,'date':invalid})
        assert rejected.status_code==422,rejected.text
    for invalid in (None,True,[],{},'assets'):
        rejected=post(client,session,'attendance.overview',{**base,'kind':invalid})
        assert rejected.status_code==422,rejected.text
    for invalid in (True,False,[],{},0,-1,1.5,'1.0','abc',2147483648,'9999999999999',999999):
        rejected=post(client,session,'attendance.overview',{**base,'department_id':invalid})
        assert rejected.status_code==422,rejected.text
    for chosen,expected in ((None,None),('',None),(1,1),('1',1)):
        assert overview(client,session,department=chosen)['department']==expected
    assert business_state(conn)==original


@pytest.mark.parametrize('permissions,allowed_kind', [
    (['student_attendance.view'],'students'),
    (['teacher_attendance.view'],'teachers'),
    (['reports.view'],None),
    (['students.view'],None),
    ([],None),
])
def test_only_the_requested_register_permission_authorizes_historical_aggregate(browser,monkeypatch,permissions,allowed_kind):
    client,_=browser;owner=login(client);freeze(monkeypatch)
    sid=student(client,owner);tid=teacher(client,owner)
    assert save(client,owner,'students',sid,'excused',excuse='PRIVATE_SCOPE_EXCUSE').status_code==200
    assert save(client,owner,'teachers',tid,'present').status_code==200
    A.save_user(employee_name='قارئ فترات الحضور',name='overview_reader',password='1234',permissions=permissions)
    session=login(client,'overview_reader','1234')
    for kind in ('students','teachers'):
        response=post(client,session,'attendance.overview',dict(kind=kind,date=str(TODAY)))
        if kind==allowed_kind:
            assert response.status_code==200,response.text
            body=response.json()
            expected=stats(excused=1) if kind=='students' else stats(present=1)
            assert body['periods']['day']['summary']==expected
            assert set(body)=={'kind','date','department','periods'}
        else:
            assert response.status_code==403,response.text
        assert not any(private in response.text for private in (sid,tid,'PRIVATE_SCOPE_EXCUSE','طالب حضور خاص','معلم حضور خاص'))


def test_overview_queries_are_bounded_and_repeated_reads_preserve_all_business_records(browser,monkeypatch):
    client,conn=browser;session=login(client);freeze(monkeypatch)
    sid=student(client,session);teacher(client,session)
    assert save(client,session,'students',sid,'present').status_code==200
    counted=CountedConnection(conn)
    payload=dict(kind='students',date=str(TODAY))
    before=business_state(conn)
    initial=AT.overview(counted,payload)
    small_count=len(counted.queries)
    assert initial['periods']['day']['summary']==stats(present=1)
    assert small_count<=4 and business_state(conn)==before
    ids=[student(client,session) for _ in range(11)]
    for _ in range(7):teacher(client,session)
    batch(client,session,'students',[(person,'absent' if i%2==0 else 'present') for i,person in enumerate(ids)])
    before=business_state(conn)
    with monkeypatch.context() as guard:
        def forbidden():raise AssertionError('An attendance overview opened an extra connection')
        guard.setattr(db,'new_transaction_connection',forbidden)
        for _ in range(3):
            counted.queries.clear()
            result=AT.overview(counted,payload)
            assert len(counted.queries)==small_count
            assert all(q.lstrip().upper().startswith(('SELECT','WITH')) for q in counted.queries)
            assert result['periods']['day']['summary']==stats(present=6,absent=6)
            assert result['periods']['day']['recorded_days']==1
    for _ in range(2):overview(client,session)
    assert business_state(conn)==before
