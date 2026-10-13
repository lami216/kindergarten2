"""Regression: finance tabs must not render colliding receipt widgets."""
import os
import uuid
from unittest.mock import patch
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit.testing.v1 import AppTest
import db
import monthly_finance as F

SCRIPT='''import os
import psycopg2
from psycopg2.extras import RealDictCursor
from sections import payments
c=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
c.autocommit=True
payments.render(c)
c.close()
'''

def connect():
    return psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_DSN'),reason='Requires disposable PostgreSQL')
def test_open_finance_receipt_renders_without_duplicate_widgets():
    con=connect();con.autocommit=True
    try:
        with patch.object(db,'get_connection',return_value=con):db.init_db()
        suffix=uuid.uuid4().hex[:19];sid='S'+suffix;pid='P'+suffix
        with con.cursor() as c:
            c.execute('INSERT INTO parents(father_id,mother_name) VALUES(%s,%s)',(pid,'أم فحص التعارض'))
            c.execute('INSERT INTO students(student_id,full_name,father_id) VALUES(%s,%s,%s)',(sid,'فحص وصل '+suffix,pid))
            c.execute('INSERT INTO monthly_accounts(student_id,status,start_date,created_by) VALUES(%s,%s,%s,%s)',(sid,'regular',F.today(),'qa'))
        with patch.object(db,'new_transaction_connection',side_effect=connect):
            F.update_tariffs(0,0,3000,'qa')
            rid,_=F.take_payment(sid,3000,actor='qa')
            app=AppTest.from_string(SCRIPT)
            app.session_state['auth_ok']=True
            app.session_state['auth_user']='qa'
            app.session_state['finance_receipt_receipt_open']=rid
            app.run(timeout=20)
            assert not app.exception
            assert len([b for b in app.button if b.label=='تعديل الوصل'])==1
            # The same actual document can be opened independently in both tabs.
            app.session_state['finance_audit_receipt_open']=rid
            app.run(timeout=20)
            assert not app.exception
            assert len([b for b in app.button if b.label=='تعديل الوصل'])==2
            # A source-child link must also coexist with the selected account.
            app.session_state['monthly_finance_child']=(sid,'فحص وصل '+suffix)
            app.session_state['finance_audit_history_child']=sid
            app.run(timeout=20)
            assert not app.exception
    finally:
        con.close()
