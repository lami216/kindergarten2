"""Salary/advance lifecycle codes stay internal; operator tables are Arabic."""
import os, uuid
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest
from streamlit.testing.v1 import AppTest
import db
import payroll_finance as P

DSN=os.getenv('TEST_POSTGRES_DSN')

@pytest.mark.skipif(not DSN,reason='requires disposable PostgreSQL')
def test_salary_and_advance_tables_show_arabic_states_without_changing_ledger():
    def connect():
        return psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    admin=connect();admin.autocommit=True
    tid='T'+uuid.uuid4().hex[:19]
    try:
        with patch.object(db,'get_connection',return_value=admin):db.init_db()
        with admin.cursor() as c:
            c.execute("INSERT INTO teachers(national_id,full_name) VALUES(%s,'معلمة حالات عربية')",(tid,))
        with patch.object(db,'new_transaction_connection',side_effect=connect):
            active,_=P.save_salary(tid,'2026-10',4000,actor='qa')
            cancelled,_=P.save_salary(tid,'2026-09',4000,actor='qa')
            P.amend('teacher_payments',cancelled,actor='qa',reason='اختبار',cancel=True)
            aid,_=P.save_advance(tid,'2026-10',500,actor='qa')
            void,_=P.save_advance(tid,'2026-09',500,actor='qa')
            P.amend('teacher_advances',void,actor='qa',reason='اختبار',cancel=True)
        source='''import os,psycopg2
from psycopg2.extras import RealDictCursor
from sections import salaries
c=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
c.autocommit=True
salaries.render(c)
c.close()
'''
        app=AppTest.from_string(source);app.session_state['auth_user']='qa';app.run(timeout=30)
        assert not app.exception
        frames=[frame.value for frame in app.dataframe if 'الحالة' in frame.value.columns]
        assert len(frames)==2
        for frame in frames:
            states=set(frame['الحالة'])
            assert {'نشطة','ملغاة'}<=states
            assert not {'active','cancelled'}&states
        with admin.cursor() as c:
            c.execute('SELECT record_state,cash_amount FROM teacher_payments WHERE payment_id IN (%s,%s) ORDER BY payment_id',(active,cancelled))
            rows=c.fetchall();assert [r['record_state'] for r in rows]==['active','cancelled']
            assert sum(r['cash_amount'] for r in rows)==8000
            c.execute('SELECT record_state,cash_amount FROM teacher_advances WHERE advance_id IN (%s,%s) ORDER BY advance_id',(aid,void))
            rows=c.fetchall();assert [r['record_state'] for r in rows]==['active','cancelled']
            assert sum(r['cash_amount'] for r in rows)==1000
    finally:admin.close()
