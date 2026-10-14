"""Real PostgreSQL mutation, cash readback, references, stale and race scenarios."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest
import db
import records as R
import school_departments as D
import expense_finance as E
import payroll_finance as P
import monthly_finance as F


@pytest.fixture
def ledger(monkeypatch):
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn: pytest.skip('Disposable PostgreSQL required')
    def connect(): return psycopg2.connect(dsn,cursor_factory=RealDictCursor)
    monkeypatch.setattr(db,'new_transaction_connection',connect)
    conn=connect(); conn.autocommit=True
    marker=uuid.uuid4().hex[:10]
    yield conn,marker
    conn.close()


def row(conn,table,ident):
    with conn.cursor() as c:
        c.execute(f'SELECT * FROM {table} WHERE {R.H.TABLES[table]}=%s',(ident,))
        return dict(c.fetchone())


def scalar(conn,query,params=()):
    with conn.cursor() as c:
        c.execute(query,params); return next(iter(c.fetchone().values()))


def child(conn,marker,cash=0):
    data=dict(full_name='طفل اختبار '+marker,birth_date=F.today().replace(year=2022),gender='ذكر',birth_place='',address='',medical_details='',allergies='',general_notes='',authorized_pickups=[])
    family=dict(father_name='أب '+marker,father_mobile='22220000',mother_name='',mother_mobile='',contact_email='')
    return db.save_child_with_family(data,family,None,str(uuid.uuid4()),finance=dict(mode='regular',cash=cash,registration=bool(cash),gilet=False,start_date=str(F.today()),payer='اختبار'),actor='record QA')[0]


@pytest.mark.parametrize('destination',[False,True])
def test_department_rename_delete_with_children_and_cash(ledger,destination):
    conn,marker=ledger; a=D.create(marker+' A'); b=D.create(marker+' B')
    sid=child(conn,marker,cash=4000); before=F.projection(conn,sid)
    D.transfer([sid],a,actor='record QA')
    R.edit('school_departments',a,{'name':marker+' new'},actor='record QA',reason='تصحيح اسم')
    assert D.transfer([sid],a,actor='record QA')==0
    R.cancel('school_departments',a,actor='record QA',reason='إغلاق القسم',destination=b if destination else None)
    assert R.cancel('school_departments',a,actor='record QA',reason='تكرار') is False
    assert scalar(conn,'SELECT COUNT(*) FROM student_departments WHERE student_id=%s',(sid,))==int(destination)
    if destination: assert scalar(conn,'SELECT department_id FROM student_departments WHERE student_id=%s',(sid,))==b
    with pytest.raises(ValueError): D.transfer([sid],a,actor='record QA')
    after=F.projection(conn,sid)
    assert (before['cash_paid'],before['due_now'])==(after['cash_paid'],after['due_now'])
    assert D.create(marker+' new')!=a # deleted names can be reused


def test_stale_edit_duplicate_and_history_no_partial_writes(ledger):
    conn,marker=ledger; a=D.create(marker+' A'); b=D.create(marker+' B')
    previous=row(conn,'school_departments',a)
    R.edit('school_departments',a,{'name':marker+' C'},actor='record QA',reason='تعديل')
    with pytest.raises(ValueError,match='تغيّر'): R.edit('school_departments',a,{'name':'lost'},actor='record QA',reason='نافذة قديمة',expected=R.revision(previous))
    with pytest.raises(ValueError): R.edit('school_departments',a,{'name':marker+' B'},actor='record QA',reason='اسم مكرر')
    assert row(conn,'school_departments',a)['name']==marker+' C'
    with conn.cursor() as c:
        c.execute("SELECT * FROM record_changes WHERE table_name='school_departments' AND record_key=%s AND action='updated'",(str(a),))
        audit=c.fetchone(); assert audit['before_state']['name']==marker+' A'; assert audit['after_state']['name']==marker+' C'; assert audit['actor']=='record QA'
    with pytest.raises(psycopg2.Error):
        with conn.cursor() as c: c.execute('DELETE FROM record_changes WHERE change_id=%s',(audit['change_id'],))


def test_department_delete_races_transfer_without_orphan(ledger):
    conn,marker=ledger; dept=D.create(marker); sid=child(conn,marker)
    def move():
        try: return D.transfer([sid],dept,actor='record QA')
        except ValueError: return 'deleted'
    def remove(): return R.cancel('school_departments',dept,actor='record QA',reason='إغلاق')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(move),pool.submit(remove)]
        results=[f.result(timeout=15) for f in futures]
    assert results[1] is True
    assert scalar(conn,'SELECT COUNT(*) FROM student_departments WHERE department_id=%s',(dept,))==0


def test_child_placement_edit_and_remove_does_not_delete_child(ledger):
    conn,marker=ledger; a=D.create(marker+' A'); b=D.create(marker+' B'); sid=child(conn,marker,cash=4000)
    D.transfer([sid],a,actor='record QA')
    R.edit('student_departments',sid,{'department_id':b},actor='record QA',reason='تصحيح التوزيع')
    assert row(conn,'student_departments',sid)['department_id']==b
    R.cancel('student_departments',sid,actor='record QA',reason='إلغاء توزيع')
    assert scalar(conn,'SELECT COUNT(*) FROM student_departments WHERE student_id=%s',(sid,))==0
    assert row(conn,'students',sid)['archived_at'] is None
    assert F.projection(conn,sid)['cash_paid']==4000


def test_legacy_registration_edit_and_cancel_preserves_history(ledger):
    conn,marker=ledger; sid=child(conn,marker); year='Y'+marker
    with conn.cursor() as c:
        c.execute('INSERT INTO academic_years(year_id,start_date,end_date) VALUES(%s,%s,%s)',(year,'2025-09-01','2026-06-30'))
        c.execute("INSERT INTO classes(class_type,section) VALUES(%s,'أ') RETURNING class_id",(marker,)); cid=c.fetchone()['class_id']
        c.execute("INSERT INTO registrations(student_id,class_id,year_id,status,annual_tuition) VALUES(%s,%s,%s,'مسجل',900) RETURNING registration_id",(sid,cid,year)); rid=c.fetchone()['registration_id']
        c.execute('INSERT INTO payments(registration_id,amount,payer_name) VALUES(%s,100,%s) RETURNING receipt_number',(rid,marker)); receipt=c.fetchone()['receipt_number']
    R.edit('academic_years',year,{'year_id':'N'+marker,'start_date':'2025-08-01'},actor='record QA',reason='تصحيح اسم السنة')
    assert row(conn,'registrations',rid)['year_id']==year
    assert row(conn,'academic_years',year)['display_year_id']=='N'+marker
    R.edit('classes',cid,{'class_type':marker+' corrected','section':'ب'},actor='record QA',reason='تصحيح الصف')
    R.edit('registrations',rid,{'annual_tuition':800,'status':'مسجل'},actor='record QA',reason='تصحيح الرسوم السابقة')
    R.cancel('classes',cid,actor='record QA',reason='حذف صف سابق مرتبط')
    R.cancel('academic_years',year,actor='record QA',reason='حذف سنة مرتبطة')
    assert row(conn,'payments',receipt)['amount']==100
    R.cancel('registrations',rid,actor='record QA',reason='إلغاء التسجيل ووصولاته')
    assert row(conn,'payments',receipt)['receipt_state']=='cancelled'
    assert row(conn,'registrations',rid)['archived_at'] is not None


def test_parent_delete_keeps_children_and_receipts(ledger):
    conn,marker=ledger; sid=child(conn,marker,cash=4000); pid=row(conn,'students',sid)['father_id']
    R.cancel('parents',pid,actor='record QA',reason='ملف ولي مكرر')
    assert row(conn,'students',sid)['father_id']==pid
    assert F.projection(conn,sid)['cash_paid']==4000
    R.edit('students',sid,{'full_name':'اسم مصحح'},actor='record QA',reason='تصحيح')
    assert row(conn,'students',sid)['full_name']=='اسم مصحح'


def test_student_delete_debt_confirmation_is_atomic(ledger):
    conn,marker=ledger; sid=child(conn,marker)
    with pytest.raises(ValueError,match='على الطالب'): R.cancel('students',sid,actor='record QA',reason='إلغاء')
    assert row(conn,'students',sid)['archived_at'] is None
    R.cancel('students',sid,actor='record QA',reason='إلغاء الملف والمتبقي',waive_student_debt=True)
    result=F.projection(conn,sid,materialize=False)
    assert result['due_now']==0 and result['cash_paid']==0
    assert scalar(conn,'SELECT COUNT(*) FROM monthly_waivers WHERE student_id=%s',(sid,))>=1


@pytest.mark.parametrize('paid',[0,25,100])
def test_expense_cash_correct_settlements_cancel_replay_and_restart(ledger,paid):
    conn,marker=ledger
    with conn.cursor() as c:
        c.execute('INSERT INTO expenses(category,amount,amount_paid,expense_date) VALUES(%s,100,%s,%s) RETURNING expense_id',(marker,paid,F.today())); ident=c.fetchone()['expense_id']
    if paid<100: E.settle(ident,100-paid,actor='record QA',reason='تسوية')
    E.correct(ident,amount_total=80,amount_paid=10,category=marker+' corrected',expense_date=F.today(),actor='record QA',reason='إدخال خاطئ',include_settlements=True)
    effective='''SELECT SUM(x.amount+COALESCE((SELECT SUM(a.delta) FROM expense_cash_amendments a WHERE a.event_id=x.event_id),0)) FROM expense_cash_events x WHERE x.expense_id=%s'''
    assert scalar(conn,effective,(ident,))==Decimal('10')
    snapshot=row(conn,'expenses',ident)
    E.correct(ident,amount_total=80,amount_paid=15,category=marker,expense_date=F.today(),actor='record QA',reason='تصحيح آخر',include_settlements=True)
    with pytest.raises(ValueError,match='تغيّر'): E.cancel(ident,actor='record QA',reason='نافذة قديمة',expected=R.revision(snapshot))
    token=str(uuid.uuid4()); assert E.cancel(ident,actor='record QA',reason='حذف إدخال خاطئ',token=token)
    assert E.cancel(ident,actor='record QA',reason='حذف إدخال خاطئ',token=token) is False
    assert E.cancel(ident,actor='record QA',reason='طلب مكرر') is False
    assert scalar(conn,effective,(ident,))==0
    assert row(conn,'expenses',ident)['amount']==0
    with pytest.raises(ValueError): E.settle(ident,1,actor='record QA',reason='بعد الإلغاء')
    F.migrate(conn) # cancelled zero entries must survive a later app startup


@pytest.mark.parametrize('table',['teacher_payments','teacher_advances'])
def test_payroll_amount_date_correction_and_financial_cancel(ledger,table):
    conn,marker=ledger; teacher='T'+marker
    with conn.cursor() as c: c.execute("INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,'معلمة اختبار',1000)",(teacher,))
    ident,_=(P.save_salary(teacher,'2026-10',1000,actor='record QA') if table=='teacher_payments' else P.save_advance(teacher,'2026-10',100,actor='record QA'))
    P.correct_cash_entry(table,ident,amount=70,base=1200,bonus=50,deductions=100,month='2026-09',on_date=F.today(),actor='record QA',reason='تصحيح المبلغ')
    assert row(conn,table,ident)['cash_amount']==(1150 if table=='teacher_payments' else 70)
    P.amend(table,ident,actor='record QA',reason='إلغاء الوثيقة فقط',cancel=True)
    assert row(conn,table,ident)['cash_amount']>0
    P.correct_cash_entry(table,ident,cancel=True,actor='record QA',reason='إلغاء الإدخال الخاطئ')
    assert row(conn,table,ident)['cash_amount']==0
    assert P.correct_cash_entry(table,ident,cancel=True,actor='record QA',reason='طلب مكرر') is False


def test_teacher_manual_identity_changes_keep_salary_reference(ledger):
    conn,marker=ledger; teacher='T'+marker; new='N'+marker
    with conn.cursor() as c: c.execute("INSERT INTO teachers(national_id,full_name) VALUES(%s,'معلمة اختبار')",(teacher,))
    pid,_=P.save_salary(teacher,'2026-10',100,actor='record QA')
    R.edit('teachers',teacher,{'national_id':new,'hire_date':F.today(),'degree':'شهادة'},actor='record QA',reason='تصحيح الهوية')
    assert row(conn,'teacher_payments',pid)['national_id']==teacher
    assert row(conn,'teachers',teacher)['display_national_id']==new
    R.cancel('teachers',teacher,actor='record QA',reason='ملف مكرر')
    assert row(conn,'teacher_payments',pid)['cash_amount']==100


def test_asset_recalculation_and_invalid_dates_rollback(ledger):
    conn,marker=ledger
    with conn.cursor() as c:
        c.execute("INSERT INTO assets(item_name,category,quantity,unit_cost,total_cost) VALUES(%s,'معدات',2,10,20) RETURNING asset_id",(marker,)); ident=c.fetchone()['asset_id']
        c.execute('INSERT INTO academic_years(year_id,start_date,end_date) VALUES(%s,%s,%s)',('Y'+marker,'2025-09-01','2026-07-01'))
    R.edit('assets',ident,{'quantity':3,'unit_cost':12,'purchase_date':F.today()},actor='record QA',reason='تعديل')
    assert row(conn,'assets',ident)['total_cost']==36
    with pytest.raises(ValueError): R.edit('assets',ident,{'quantity':Decimal('2.5')},actor='record QA',reason='كمية خاطئة')
    with pytest.raises(ValueError): R.edit('academic_years','Y'+marker,{'end_date':'2024-01-01'},actor='record QA',reason='تاريخ خاطئ')
    R.cancel('assets',ident,actor='record QA',reason='إزالة أصل')
    assert row(conn,'assets',ident)['archived_at'] is not None


def test_account_correction_requires_resolving_dependent_receipts(ledger):
    from datetime import timedelta
    from account_records import change_account
    conn,marker=ledger
    F.update_tariffs(1000,2000,1000,'record QA fixture')
    sid=child(conn,marker,cash=4000) # creates three periods, including future credit
    anchor=F.today()-timedelta(days=3)
    with pytest.raises(ValueError,match='ألغِ الوصولات'): change_account(sid,start_date=anchor,status='regular',actor='record QA',reason='تصحيح البداية')
    assert row(conn,'monthly_accounts',sid)['start_date']==F.today()
    rid=scalar(conn,"SELECT receipt_id FROM monthly_receipts WHERE student_id=%s AND state='active'",(sid,))
    F.cancel_receipt(rid,'إدخال خاطئ',actor='record QA')
    change_account(sid,start_date=anchor,status='regular',actor='record QA',reason='تصحيح البداية')
    assert row(conn,'monthly_accounts',sid)['start_date']==anchor
    with pytest.raises(ValueError,match='دين سابق'):
        change_account(sid,start_date=anchor,status='exempt',actor='record QA',reason='الطفل معفي')
    import student_debt as SD
    SD.waive_debt(sid,'إعفاء صريح للدين',True,actor='record QA')
    change_account(sid,start_date=anchor,status='exempt',actor='record QA',reason='الطفل معفي')
    assert F.projection(conn,sid,materialize=False)['due_now']==0
    assert F.projection(conn,sid,as_of=F.today()+timedelta(days=80),materialize=False)['due_now']==0
    F.update_tariffs(1000,2000,3000,'record QA fixture reset')


def test_waiver_correction_and_cancellation_restore_debt_without_cash(ledger):
    from account_records import change_waiver
    import student_debt as SD
    conn,marker=ledger; sid=child(conn,marker)
    before=F.projection(conn,sid)['due_now']
    SD.waive_debt(sid,'إعفاء اختبار',True,actor='record QA')
    ident=scalar(conn,'SELECT waiver_id FROM monthly_waivers WHERE student_id=%s ORDER BY waiver_id LIMIT 1',(sid,))
    old=row(conn,'monthly_waivers',ident)
    replacement=change_waiver(ident,new_amount=100,on_date=F.today(),actor='record QA',reason='تعديل قيمة الإعفاء')
    assert F.projection(conn,sid)['due_now']==old['amount']-100
    change_waiver(replacement,cancel=True,actor='record QA',reason='إلغاء الإعفاء الخاطئ')
    assert F.projection(conn,sid)['due_now']==old['amount']
    assert F.projection(conn,sid)['cash_paid']==0


def test_record_manager_forms_all_types_and_stale_snapshot(ledger,monkeypatch):
    from streamlit.testing.v1 import AppTest
    conn,marker=ledger; sid=child(conn,marker)
    dept=D.create(marker+' UI')
    script='''import os, streamlit as st, psycopg2
from psycopg2.extras import RealDictCursor
from sections import record_manager
st.session_state['auth_user']='record UI QA'
conn=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
conn.autocommit=True
record_manager.render(conn)
conn.close()
'''
    app=AppTest.from_string(script).run(timeout=40)
    app.selectbox(key='records_type').set_value('school_departments').run(timeout=40)
    app.selectbox(key='records_pick_school_departments').set_value(dept).run(timeout=40)
    assert not app.exception
    label=next(t for t in app.text_input if t.label=='اسم القسم')
    label.set_value(marker+' UI edited')
    next(t for t in app.text_input if t.label=='سبب التعديل *').set_value('تصحيح الاسم')
    next(b for b in app.button if b.label=='حفظ التعديل').click().run(timeout=40)
    assert not app.exception
    assert row(conn,'school_departments',dept)['name']==marker+' UI edited'
    app.selectbox(key='records_type').set_value('students').run(timeout=40)
    app.selectbox(key='records_pick_students').set_value(sid).run(timeout=40)
    assert not app.exception
    assert any(t.label=='الاسم' for t in app.text_input)
    for table in ('assets','expenses','teachers','classes','academic_years','registrations','monthly_receipts','payments','teacher_payments','teacher_advances','monthly_accounts','monthly_waivers','monthly_tariffs'):
        app.selectbox(key='records_type').set_value(table).run(timeout=40)
        assert not app.exception,table
