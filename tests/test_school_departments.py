"""Real PG: repeatable placements, atomic batches, and unchanged child finances."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
import db
import school_departments as D
import monthly_finance as F


@pytest.fixture
def placement(monkeypatch):
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn:
        pytest.skip('Disposable PostgreSQL required')
    def connection():
        return psycopg2.connect(dsn,cursor_factory=RealDictCursor)
    monkeypatch.setattr(db,'new_transaction_connection',connection)
    admin=connection()
    admin.autocommit=True
    F.update_tariffs(1000,2000,3000,'department-fixture')
    suffix=uuid.uuid4().hex[:8]
    groups=[D.create('قسم '+suffix+' '+str(i)) for i in (1,2)]
    children=[]
    for i in (1,2):
        child=dict(full_name='طفل أقسام '+suffix+str(i),birth_date=F.today().replace(year=2022),gender='ذكر',birth_place='',address='',medical_details='',allergies='',general_notes='',authorized_pickups=[])
        family=dict(father_name='',father_mobile='',mother_name='أم القسم',mother_mobile='22220000',contact_email='')
        student,_=db.save_child_with_family(child,family,None,str(uuid.uuid4()),finance=dict(mode='regular',cash=4000 if i==1 else 0,registration=i==1,gilet=False,start_date=str(F.today()),payer='أم القسم'),actor='department-fixture')
        children.append(student)
    yield admin,children,groups
    admin.close()


def test_repeated_and_bulk_transfers_keep_financial_records(placement):
    conn,children,groups=placement
    before=[F.projection(conn,s) for s in children]
    assert D.transfer(children,groups[0],actor='fixture')==2
    assert D.transfer(children,groups[0],actor='fixture')==0
    assert D.transfer([children[0]],groups[1],actor='fixture')==1
    assert D.transfer([children[1]],groups[1],actor='fixture')==1
    assert D.transfer(children,groups[0],actor='fixture')==2
    D.migrate(conn)  # A later startup must not restore an older placement.
    with conn.cursor() as c:
        c.execute('SELECT student_id,department_id FROM student_departments WHERE student_id=ANY(%s)',(children,))
        assert len(c.fetchall())==2
        c.execute('SELECT COUNT(*) AS n FROM department_transfers WHERE student_id=ANY(%s)',(children,))
        assert c.fetchone()['n']==6
    after=[F.projection(conn,s) for s in children]
    for old,new in zip(before,after):
        assert old['cash_paid']==new['cash_paid']
        assert old['due_now']==new['due_now']
        assert old['receipts']==new['receipts']


def test_invalid_member_rolls_back_the_whole_batch(placement):
    conn,children,groups=placement
    with pytest.raises(ValueError):
        D.transfer([children[0],'missing-child'],groups[0],actor='fixture')
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM student_departments WHERE student_id=ANY(%s)',(children,))
        assert c.fetchone()['n']==0
    with pytest.raises(ValueError):
        D.create('  ')


def test_double_submission_creates_one_placement_and_one_transfer(placement):
    conn,children,groups=placement
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:D.transfer([children[0]],groups[0],actor='fixture'),range(2)))
    assert sorted(results)==[0,1]
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM department_transfers WHERE student_id=%s',(children[0],))
        assert c.fetchone()['n']==1


def test_legacy_placement_is_imported_once_and_does_not_reset_a_transfer(monkeypatch):
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn:
        pytest.skip('Disposable PostgreSQL required')
    from psycopg2 import sql
    schema='departments_'+uuid.uuid4().hex
    admin=psycopg2.connect(dsn)
    admin.autocommit=True
    with admin.cursor() as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connection():
        conn=psycopg2.connect(dsn,cursor_factory=RealDictCursor)
        with conn.cursor() as c:
            c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        conn.commit()
        return conn
    boot=connection()
    boot.autocommit=True
    monkeypatch.setattr(db,'get_connection',lambda:boot)
    monkeypatch.setattr(db,'new_transaction_connection',connection)
    try:
        db.init_db()
        with boot.cursor() as c:
            c.execute("INSERT INTO parents(father_id,mother_name,mother_mobile) VALUES('P1','أم قسم','11111111')")
            c.execute("INSERT INTO students(student_id,full_name,father_id) VALUES('S1','طفل قديم','P1')")
            c.execute("INSERT INTO classes(class_type,section,class_name) VALUES('تمهيدي','أ','الورود') RETURNING class_id")
            old_class=c.fetchone()['class_id']
            c.execute("INSERT INTO academic_years(year_id,start_date) VALUES('2026-2027','2026-09-01')")
            c.execute("INSERT INTO registrations(student_id,class_id,year_id,status,annual_tuition) VALUES('S1',%s,'2026-2027','مسجل',12000)",(old_class,))
            c.execute("DELETE FROM department_migrations WHERE migration_id='legacy_placement_v1'")
        D.migrate(boot)
        with boot.cursor() as c:
            c.execute('SELECT d.name FROM student_departments m JOIN school_departments d USING(department_id) WHERE student_id=%s',('S1',))
            assert c.fetchone()['name']=='تمهيدي أ · الورود'
        destination=D.create('قسم النجوم')
        assert D.transfer(['S1'],destination,actor='fixture')==1
        D.migrate(boot)
        with boot.cursor() as c:
            c.execute("SELECT department_id FROM student_departments WHERE student_id='S1'")
            assert c.fetchone()['department_id']==destination
            c.execute("SELECT class_id,annual_tuition FROM registrations WHERE student_id='S1'")
            row=c.fetchone()
            assert row['class_id']==old_class and row['annual_tuition']==12000
    finally:
        boot.close()
        with admin.cursor() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()
