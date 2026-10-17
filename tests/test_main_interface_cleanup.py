"""Current placement and debt reports must not depend on legacy registrations."""
import os
import uuid
from unittest.mock import patch

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from sections import reports
import monthly_finance as F


@pytest.mark.parametrize('department,gender,params', [
    (-1, 'الكل', ()), (0, 'الكل', ()), (17, 'أنثى', (17, 'أنثى')),
])
def test_current_student_report_uses_current_department_and_both_contacts(department,gender,params):
    with patch.object(reports.ui,'df',return_value=pd.DataFrame()) as read:
        reports._current_students(None,department,gender)
    _,query,actual=read.call_args.args
    assert actual==params
    assert 'student_departments' in query and 'school_departments' in query
    assert 'registrations' not in query and 'academic_years' not in query
    assert 'LEFT JOIN parents' in query and 'mother_mobile' in query and 'father_mobile' in query
    if department==0: assert 'd.department_id IS NULL' in query
    assert 's.archived_at IS NULL' in query


def test_printed_values_remain_text_not_html():
    with patch.object(reports.components,'html') as html:
        reports._render_printable_report_pdf('<img src=x onerror=alert(1)>',
            {'القسم':'<b>أ</b>'},pd.DataFrame({'الطالب':['<script>alert(1)</script>']}),
            {'الإجمالي':'<b>1</b>'})
    content=html.call_args.args[0]
    assert '<script>alert(1)</script>' not in content
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in content
    assert '<img src=x onerror=alert(1)>' not in content
    assert '&lt;b&gt;أ&lt;/b&gt;' in content


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_DSN'),reason='Disposable PostgreSQL required')
def test_exempt_and_archived_debts_and_current_placement_remain_reportable():
    dsn=os.environ['TEST_POSTGRES_DSN']
    conn=psycopg2.connect(dsn,cursor_factory=RealDictCursor);conn.autocommit=True
    prefix=uuid.uuid4().hex[:10]
    day=F.today()
    ids=['cln'+prefix+str(i) for i in range(3)]
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO parents(father_id,mother_name,mother_mobile) VALUES(%s,%s,%s)',
                      ('par'+prefix,'أم مراجعة','00000987'))
            c.execute('INSERT INTO school_departments(name) VALUES(%s) RETURNING department_id',
                      ('قسم حالي '+prefix,))
            department=c.fetchone()['department_id']
            for i,sid in enumerate(ids):
                c.execute('INSERT INTO students(student_id,full_name,father_id) VALUES(%s,%s,%s)',
                          (sid,'طفل تنظيف '+prefix+str(i),'par'+prefix))
                c.execute('''INSERT INTO monthly_accounts(student_id,status,start_date,exempt_from,created_by)
                    VALUES(%s,%s,%s,%s,'QA')''',(sid,'exempt',day,day))
                c.execute("INSERT INTO monthly_fees(student_id,kind,price) VALUES(%s,'registration',%s)",
                          (sid,1000 if i<2 else 0))
            c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(ids[1],))
            c.execute('UPDATE monthly_accounts SET archived_at=now(),departure_on=%s WHERE student_id=%s',
                      (day,ids[1]))
            c.execute('INSERT INTO student_departments(student_id,department_id) VALUES(%s,%s)',
                      (ids[0],department))
        with patch.object(F,'_ensure_all_started') as materialize:
            debt=reports._current_debts(conn)
        materialize.assert_called_once_with(day)
        matched=[r for r in debt if prefix in r['اسم الطالب']]
        assert len(matched)==2 and sum(r['الباقي على الطالب'] for r in matched)==2000
        assert {r['حالة الملف'] for r in matched}=={'نشط','مؤرشف'}
        assert {r['الرسوم'] for r in matched}=={'معفي'}
        assert all(r['جوال الأم']=='00000987' and not r['جوال الأب'] for r in matched),matched
        assert all(r['موعد القسط التالي'] is None for r in matched)
        current=reports._current_students(conn,department)
        assert list(current['رقم الطالب'])==[ids[0]]
        assert current.iloc[0]['القسم']=='قسم حالي '+prefix
        assert current.iloc[0]['جوال الأم']=='00000987'
        unassigned=reports._current_students(conn,0)
        assert ids[2] in set(unassigned['رقم الطالب']) and ids[1] not in set(unassigned['رقم الطالب'])
    finally:
        conn.close()
