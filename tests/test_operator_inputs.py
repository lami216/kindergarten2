"""Ordinary operator inputs: visible payroll, recoverable expenses, literal search."""
from decimal import Decimal
import uuid
import pytest
from streamlit.testing.v1 import AppTest
import payroll_finance as P
import monthly_finance as F
from tests.test_record_management import ledger, row, scalar


def app_for(section):
    app=AppTest.from_string(f'''import os,psycopg2,streamlit as st
from psycopg2.extras import RealDictCursor
from sections import {section}
conn=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
conn.autocommit=True
try: {section}.render(conn)
finally: conn.close()
''')
    app.session_state['auth_user']='operator input QA'
    return app.run(timeout=30)


def widget(app,kind,label):
    return next(w for w in getattr(app,kind) if w.label==label)


def teacher(conn,marker):
    tid='T'+uuid.uuid4().hex[:19]
    name=f'معلمة {marker} ([أ])+ . \\ نهاية'
    with conn.cursor() as c:
        c.execute('INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,2000)',(tid,name))
    return tid,name


def salary_app(conn,marker):
    tid,name=teacher(conn,marker)
    app=app_for('salaries')
    option=next(s for s in app.selectbox(key='salary_teacher').options if tid in s)
    app.selectbox(key='salary_teacher').select(option).run(timeout=30)
    assert not app.exception
    return app,tid,name


def has_net(app,value):
    assert any('صافي الراتب المستحق' in x.value and f'{value:,.2f}' in x.value for x in app.info)


def test_live_salary_2000_500_100_shows_and_saves_2400(ledger):
    conn,marker=ledger;app,tid,_=salary_app(conn,marker)
    has_net(app,2000)
    app.number_input(key='salary_bonus_v0').set_value(500).run(timeout=30)
    has_net(app,2500)
    app.number_input(key='salary_deductions_v0').set_value(100).run(timeout=30)
    has_net(app,2400)
    assert scalar(conn,'SELECT COUNT(*) FROM teacher_payments WHERE national_id=%s',(tid,))==0
    # Notes do not change the amount approved in the preview.
    app.text_input(key='salary_notes_v0').set_value('ملاحظة قبل الحفظ مباشرة')
    app.button(key='salary_save_v0').click().run(timeout=30)
    assert not app.exception
    ident=scalar(conn,'SELECT payment_id FROM teacher_payments WHERE national_id=%s',(tid,))
    saved=row(conn,'teacher_payments',ident)
    assert (saved['base_salary'],saved['bonus'],saved['deductions'],saved['cash_amount'])==(2000,500,100,2400)
    assert saved['notes']=='ملاحظة قبل الحفظ مباشرة'
    assert scalar(conn,'SELECT COUNT(*) FROM payroll_audit WHERE payment_id=%s',(ident,))==1
    # A separate intentional payment remains possible after the form reset.
    app.button(key='salary_save_v1').click().run(timeout=30)
    assert not app.exception
    assert scalar(conn,'SELECT COUNT(*) FROM teacher_payments WHERE national_id=%s',(tid,))==2
    assert scalar(conn,'SELECT SUM(cash_amount) FROM teacher_payments WHERE national_id=%s',(tid,))==4400


def test_salary_submit_with_unrendered_values_requires_review_before_cash(ledger):
    conn,marker=ledger;app,tid,_=salary_app(conn,marker)
    app.number_input(key='salary_bonus_v0').set_value(500)
    app.number_input(key='salary_deductions_v0').set_value(100)
    # Same event batch as clicking save while the last amount still has focus.
    app.button(key='salary_save_v0').click().run(timeout=30)
    has_net(app,2400)
    assert any('راجع صافي الراتب المحدّث' in x.value for x in app.error)
    assert scalar(conn,'SELECT COUNT(*) FROM teacher_payments WHERE national_id=%s',(tid,))==0
    app.button(key='salary_save_v0').click().run(timeout=30)
    assert not app.exception
    assert scalar(conn,'SELECT cash_amount FROM teacher_payments WHERE national_id=%s',(tid,))==2400


def test_salary_invalid_deduction_recovers_and_decimal_preview_matches_cash(ledger):
    conn,marker=ledger;app,tid,_=salary_app(conn,marker)
    for deductions in (2100,2000):
        app.number_input(key='salary_deductions_v0').set_value(deductions).run(timeout=30)
        assert not app.exception and app.error
        assert app.button(key='salary_save_v0').disabled
        assert scalar(conn,'SELECT COUNT(*) FROM teacher_payments WHERE national_id=%s',(tid,))==0
    app.number_input(key=f'salary_base_v0_{tid}').set_value(2000.01)
    app.number_input(key='salary_bonus_v0').set_value(0.10)
    app.number_input(key='salary_deductions_v0').set_value(0.02).run(timeout=30)
    has_net(app,2000.09)
    app.button(key='salary_save_v0').click().run(timeout=30)
    assert not app.exception
    assert scalar(conn,'SELECT cash_amount FROM teacher_payments WHERE national_id=%s',(tid,))==Decimal('2000.09')


def test_salary_search_is_literal_for_punctuation_arabic_and_month(ledger):
    conn,marker=ledger;tid,_=teacher(conn,marker)
    P.save_salary(tid,'2026-10',2000,actor='operator input QA')
    app=app_for('salaries')
    def frame(): return next(d.value for d in app.dataframe if 'الصافي المدفوع' in d.value.columns)
    baseline=frame().copy()
    for term in ('(',')','[',']','+','.', '\\','معلمة','2026-10','لا نتيجة '+marker,''):
        widget(app,'text_input','🔍 ابحث باسم المعلمة أو الشهر').set_value(term).run(timeout=30)
        assert not app.exception,term
        expected=baseline[[term in str(r['المعلمة']) or term in str(r['عن شهر']) for _,r in baseline.iterrows()]]
        assert frame()['المعلمة'].tolist()==expected['المعلمة'].tolist(),term
        assert frame()['الصافي المدفوع'].sum()==expected['الصافي المدفوع'].sum(),term


def expense(conn,marker):
    with conn.cursor() as c:
        c.execute("""INSERT INTO expenses(expense_date,category,amount,amount_paid,payment_status)
            VALUES(%s,%s,1200,1000,'مدفوع جزئياً') RETURNING expense_id""",(F.today(),marker))
        return c.fetchone()['expense_id']


def test_expense_lower_total_preserves_paid_and_recovers_in_same_form(ledger):
    conn,marker=ledger;ident=expense(conn,marker);before=row(conn,'expenses',ident)
    app=app_for('expenses')
    widget(app,'selectbox','اختر المصروف لتعديله، تسديد الدين، أو الحذف:').set_value(ident).run(timeout=30)
    widget(app,'button','تصحيح المصروف').click().run(timeout=30)
    assert widget(app,'text_input','المورد').value==''
    assert widget(app,'text_area','ملاحظات').value==''
    counts=[scalar(conn,f'SELECT COUNT(*) FROM {table} WHERE expense_id=%s',(ident,))
            for table in ('expense_audit','expense_cash_events','expense_cash_amendments','expense_request_log')]
    widget(app,'number_input','إجمالي الفاتورة').set_value(800)
    widget(app,'text_input','سبب تصحيح القيد *').set_value('تصحيح إجمالي الفاتورة')
    widget(app,'button','حفظ تصحيح القيد').click().run(timeout=30)
    assert not app.exception
    assert any('المدفوع أكبر من قيمة الفاتورة' in x.value for x in app.error)
    assert widget(app,'number_input','المبلغ المدفوع فعلياً').value==1000
    assert widget(app,'number_input','إجمالي الفاتورة').value==800
    assert row(conn,'expenses',ident)==before
    assert [scalar(conn,f'SELECT COUNT(*) FROM {table} WHERE expense_id=%s',(ident,))
            for table in ('expense_audit','expense_cash_events','expense_cash_amendments','expense_request_log')]==counts
    widget(app,'number_input','إجمالي الفاتورة').set_value(1400)
    widget(app,'button','حفظ تصحيح القيد').click().run(timeout=30)
    assert not app.exception
    saved=row(conn,'expenses',ident)
    assert (saved['amount'],saved['amount_paid'])==(1400,1000)
    assert saved['payee'] in (None,'') and saved['notes'] in (None,'')
    assert scalar(conn,'SELECT SUM(amount) FROM expense_cash_events WHERE expense_id=%s',(ident,))==1000
    assert scalar(conn,'SELECT COUNT(*) FROM expense_audit WHERE expense_id=%s',(ident,))==1


def test_new_partial_expense_does_not_silently_lower_entered_paid_cash(ledger):
    conn,marker=ledger;app=app_for('expenses')
    app.text_input(key='expense_add_category_0').set_value(marker)
    app.number_input(key='expense_add_amount_0').set_value(1200)
    app.selectbox(key='expense_add_status_0').select('مدفوع جزئياً').run(timeout=30)
    app.number_input(key='expense_add_paid_0').set_value(1000).run(timeout=30)
    app.number_input(key='expense_add_amount_0').set_value(800).run(timeout=30)
    assert app.number_input(key='expense_add_paid_0').value==1000
    app.button(key='expense_add_save_0').click().run(timeout=30)
    assert not app.exception
    assert any('المدفوع أكبر' in x.value for x in app.error)
    assert scalar(conn,'SELECT COUNT(*) FROM expenses WHERE category=%s',(marker,))==0
    app.number_input(key='expense_add_paid_0').set_value(700).run(timeout=30)
    app.button(key='expense_add_save_0').click().run(timeout=30)
    assert not app.exception
    ident=scalar(conn,'SELECT expense_id FROM expenses WHERE category=%s',(marker,))
    saved=row(conn,'expenses',ident)
    assert (saved['amount'],saved['amount_paid'])==(800,700)


def test_expense_modal_rejects_stale_correction_without_erasing_new_notes(ledger):
    conn,marker=ledger;ident=expense(conn,marker)
    app=app_for('expenses')
    widget(app,'selectbox','اختر المصروف لتعديله، تسديد الدين، أو الحذف:').set_value(ident).run(timeout=30)
    widget(app,'button','تصحيح المصروف').click().run(timeout=30)
    import expense_finance as E
    E.correct(ident,amount_total=1400,amount_paid=1000,category=marker,expense_date=row(conn,'expenses',ident)['expense_date'],
        notes='معلومة أحدث',reason='تعديل من جلسة أخرى',actor='other operator')
    widget(app,'number_input','إجمالي الفاتورة').set_value(1500)
    widget(app,'text_input','سبب تصحيح القيد *').set_value('مسودة قديمة')
    widget(app,'button','حفظ تصحيح القيد').click().run(timeout=30)
    assert not app.exception and any('تغيّر' in e.value for e in app.error)
    saved=row(conn,'expenses',ident)
    assert saved['amount']==1400 and saved['notes']=='معلومة أحدث'
