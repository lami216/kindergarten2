"""Financial reports work before an academic year is configured (real PG)."""
import os
import uuid
from unittest.mock import patch
import pytest
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from streamlit.testing.v1 import AppTest
import db

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_DSN'),reason='Disposable PostgreSQL required')
@pytest.mark.parametrize('section',['reports','dashboard'])
def test_financial_reports_without_academic_year(monkeypatch,section):
    schema='report_test_'+uuid.uuid4().hex
    admin=psycopg2.connect(os.environ['TEST_POSTGRES_DSN']);admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('REPORT_TEST_SCHEMA',schema)
    monkeypatch.setenv('REPORT_TEST_SECTION',section)
    def connection():
        con=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
        con.autocommit=True
        with con.cursor() as c:c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        return con
    boot=connection()
    original_factory=db.new_transaction_connection
    try:
        with patch.object(db,'get_connection',return_value=boot):db.init_db()
        app=AppTest.from_string('''import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import db
from sections import reports,dashboard
def connection():
 c=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
 c.autocommit=True
 with c.cursor() as q:q.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(os.environ['REPORT_TEST_SCHEMA'])))
 return c
c=connection()
db.new_transaction_connection=connection
(dashboard if os.environ['REPORT_TEST_SECTION']=='dashboard' else reports).render(c)
c.close()
''').run(timeout=20)
        assert not app.exception
        if section=='dashboard':
            assert any('الباقي من المداخيل' in m.value for m in app.markdown)
            assert any('الباقي على الطلاب' in m.value for m in app.markdown)
        else:
            assert any(m.label=='الباقي من المداخيل' for m in app.metric)
        if section=='reports':
            app.radio[0].set_value('📅 تقرير الحسابات الشهرية (أوقية قديمة)').run(timeout=20)
            assert not app.exception
            assert any(m.label=='الباقي من المداخيل' for m in app.metric)
        with boot.cursor() as c:
            c.execute('SELECT COUNT(*) AS n FROM academic_years')
            assert c.fetchone()['n']==0
    finally:
        db.new_transaction_connection=original_factory
        boot.close()
        with admin.cursor() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()
