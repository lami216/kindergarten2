"""500 synthetic accounts in a disposable schema; bulk debt equals child debt."""
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter
import uuid
from datetime import date, timedelta

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor, execute_values
import pytest
import db
import monthly_finance as F
import schema_migrations as M


def test_500_children_one_connection_and_same_debt_across_account_states(monkeypatch):
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn: pytest.skip('Disposable PostgreSQL required')
    schema='qa_performance_'+uuid.uuid4().hex
    admin=psycopg2.connect(dsn,cursor_factory=RealDictCursor); admin.autocommit=True
    with admin.cursor() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    statements=[]; connections=[]
    class Cursor(RealDictCursor):
        def execute(self,query,vars=None):
            statements.append(str(query))
            return super().execute(query,vars)
    def connect():
        c=psycopg2.connect(dsn,cursor_factory=Cursor,options=f'-c search_path={schema}')
        connections.append(c)
        return c
    conn=connect();conn.autocommit=True
    monkeypatch.setattr(db,'new_transaction_connection',connect)
    try:
        M.upgrade(conn)
        F.update_tariffs(1000,2000,3000,'performance fixture')
        with conn.cursor() as c:
            execute_values(c,'INSERT INTO students(student_id,full_name) VALUES %s',
                           [(f'perf{i}',f'طفل أداء {i}') for i in range(500)])
            execute_values(c,"INSERT INTO monthly_accounts(student_id,status,start_date,created_by) VALUES %s",
                           [(f'perf{i}','regular',date(2024,1,31),'performance fixture') for i in range(500)])
            execute_values(c,'INSERT INTO monthly_fees(student_id,kind,price) VALUES %s',
                           [(f'perf{i}','registration',1000) for i in range(500)])
        fixed=date(2024,4,15)
        monkeypatch.setattr(F,'today',lambda:fixed)
        # Includes Jan 31 -> leap Feb -> Mar 31, partial prepayment and voids.
        receipt,_=F.take_payment('perf0',4500,actor='performance fixture',as_of=fixed)
        F.cancel_receipt(receipt,'إلغاء',actor='performance fixture')
        F.take_payment('perf1',12000,actor='performance fixture',as_of=fixed)
        F._ensure_all_started(fixed)
        with conn.cursor() as c:
            c.execute("UPDATE monthly_accounts SET status='exempt',exempt_from='2024-03-01' WHERE student_id='perf2'")
            c.execute("UPDATE monthly_accounts SET departure_on='2024-02-29',archived_at=now() WHERE student_id='perf3'")
            c.execute("""INSERT INTO monthly_waivers(student_id,fee_id,amount,effective_on,actor,reason,
                request_token,request_hash,before_state,after_state)
                SELECT student_id,fee_id,500,'2024-04-01','QA','إسقاط جزئي',%s,'qa','{}','{}'
                FROM monthly_fees WHERE student_id='perf4'""",(str(uuid.uuid4()),))
        timings=[]; counts=[]
        for _ in range(3):
            statements.clear();connections.clear()
            started=perf_counter();result=F.financial_overview(conn);timings.append(perf_counter()-started)
            counts.append({'connections':len(connections),'statements':len(statements)})
        assert all(x['connections']==1 for x in counts),counts
        assert all(x['statements']<=15 for x in counts),counts
        expected=sum(F.projection(conn,f'perf{i}',fixed,materialize=False)['due_now'] for i in range(500))
        assert result['due_now']==expected
        assert result['new_cash']==12000
        statements.clear();connections.clear()
        bulk=F.projections(conn,fixed,materialize=False)
        assert len(bulk)==500 and len(statements)==4 and not connections
        for i in range(500):
            assert bulk[f'perf{i}']==F.projection(conn,f'perf{i}',fixed,materialize=False)
        # Exercise the actual authenticated snapshot, including roster, photos,
        # parents, receipt revisions, overview and activity, not only a helper.
        import live_pages as L
        statements.clear();connections.clear()
        snapshot_started=perf_counter()
        live=L.snapshot(conn,{'is_admin':False,'user_id':'00000000-0000-0000-0000-000000000001'})
        snapshot_seconds=perf_counter()-snapshot_started
        assert len(live['students'])==500
        assert len(connections)==1, len(connections)
        assert len(statements)<=40, len(statements)
        assert sum(s['account']['due'] for s in live['students'])==result['due_now']
        assert live['overview']['total_cash']==result['total_cash']
        snapshot_evidence=dict(children=500,connections=len(connections),statements=len(statements),seconds=snapshot_seconds)
        with conn.cursor() as c:
            c.execute("SELECT starts FROM monthly_periods WHERE student_id='perf0' ORDER BY period_no")
            assert [x['starts'] for x in c.fetchall()]==[date(2024,1,31),date(2024,2,29),date(2024,3,31)]
        # Historical/future cutoff and prior prices remain identical to child projection.
        for end in (date(2024,1,1),date(2024,2,29),date(2024,6,1)):
            actual=F.financial_report(conn,date.min,end)
            expected=sum(F.projection(conn,f'perf{i}',end,materialize=False)['due_now'] for i in range(500))
            assert actual['due_now']==expected
        evidence={'children':500,'seconds':timings,'median_seconds':median(timings),'counts':counts,
                  'due_matches_500_individual_projections':True,'live_snapshot':snapshot_evidence}
        Path('visual-evidence').mkdir(exist_ok=True)
        Path('visual-evidence/overview-500.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence))
        # Generous CI budget; count assertions enforce the actual scalability fix.
        assert median(timings)<5,evidence
    finally:
        conn.close()
        with admin.cursor() as c:
            # Only this test's randomly named schema, never public/application data.
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()
