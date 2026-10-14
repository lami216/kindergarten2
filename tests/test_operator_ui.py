"""Operator journeys: documents are opt-in; partial cash intake reacts live."""
import os
import uuid

import pytest
import psycopg2
from streamlit.testing.v1 import AppTest


def test_dashboard_has_no_period_controls_or_sticky_shortcut_selection():
    source = '''
from unittest.mock import patch
import pandas as pd
import streamlit as st
import monthly_finance as F
import ui
from sections import dashboard
keys = ('total_cash', 'expenses', 'remaining_cash', 'due_now', 'registration_children',
        'gilet_count', 'registration_cash', 'gilet_cash', 'monthly_cash', 'prepaid_cash',
        'salary_cash', 'advance_cash', 'operational_cash')
with patch.object(F, 'financial_overview', return_value=dict.fromkeys(keys, 0)), \\
     patch.object(dashboard, '_get_scalar', return_value=0), \\
     patch.object(ui, 'df', return_value=pd.DataFrame()):
    dashboard.render(None)
'''
    app = AppTest.from_string(source).run(timeout=20)
    assert not app.exception
    assert not app.date_input
    assert app.button(key='home_payment').proto.type == 'secondary'
    app.button(key='home_payment').click().run(timeout=20)
    assert not app.exception
    assert app.session_state['current_page'] == 'payments'
    assert app.button(key='home_payment').proto.type == 'secondary'
    assert app.button(key='home_add_student').proto.type == 'secondary'
    app.button(key='home_expense').click().run(timeout=20)
    assert app.session_state['current_page'] == 'expenses'
    assert app.button(key='home_expense').proto.type == 'secondary'
    assert app.button(key='home_payment').proto.type == 'secondary'


PROFILE = '''
from unittest.mock import patch
import streamlit as st
from sections import monthly_payments as M
record = {"cash_paid": 6000, "due_now": 1500, "exempt": False,
          "account": {"start_date": "2026-10-01"}}
with patch.object(M.F, "projection", return_value=record), \\
     patch.object(M.RI, "render_receipt_list", side_effect=AssertionError("Unrequested document")):
    M.financial_panel(None, "S001", profile=True, student_name="طفل تجربة")
'''


def test_profile_never_mounts_payment_or_receipt_controls():
    app=AppTest.from_string(PROFILE).run(timeout=20)
    assert not app.exception
    assert not app.number_input
    assert not any(b.label in ("فتح الوصل", "تعديل الوصل", "تصدير PDF") for b in app.button)
    app.button(key="profile_payment_S001").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["current_page"] == "payments"
    assert app.session_state["monthly_finance_child"] == ("S001", "طفل تجربة")
    assert app.session_state["payments_requested_tab"] == "📅 حسابات الأطفال"


def test_profile_receipt_link_carries_exact_child_identity():
    app=AppTest.from_string(PROFILE).run(timeout=20)
    app.button(key="profile_receipts_S001").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["current_page"] == "payments"
    assert app.session_state["payments_receipt_child"] == "S001"
    assert app.session_state["payments_requested_tab"] == "🧾 الوصولات"


EXPENSE='''
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from sections import expenses
c=psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],cursor_factory=RealDictCursor)
c.autocommit=True
expenses.render(c)
c.close()
'''


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_DSN"),reason="Disposable PostgreSQL required")
def test_partial_expense_reacts_and_saves_actual_cash_then_resets():
    app=AppTest.from_string(EXPENSE).run(timeout=25)
    assert not app.exception
    app.number_input(key="expense_add_amount_0").set_value(5000).run(timeout=25)
    app.selectbox(key="expense_add_status_0").set_value("مدفوع جزئياً").run(timeout=25)
    assert not app.exception
    app.number_input(key="expense_add_paid_0").set_value(2000).run(timeout=25)
    # Reducing total preserves a valid partial amount rather than crashing.
    app.number_input(key="expense_add_amount_0").set_value(1000).run(timeout=25)
    assert not app.exception
    assert app.number_input(key="expense_add_paid_0").value == 1000
    app.number_input(key="expense_add_amount_0").set_value(5000).run(timeout=25)
    app.number_input(key="expense_add_paid_0").set_value(2000)
    payee="مورد واجهة "+uuid.uuid4().hex
    app.text_input(key="expense_add_payee_0").set_value(payee)
    app.button(key="expense_add_save_0").click().run(timeout=25)
    assert not app.exception
    assert app.number_input(key="expense_add_amount_1").value == 0
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"]) as c:
        with c.cursor() as q:
            q.execute("SELECT amount,amount_paid FROM expenses WHERE payee=%s",(payee,))
            rows=q.fetchall()
            assert len(rows)==1 and tuple(map(float,rows[0])) == (5000,2000)
            q.execute("SELECT amount FROM expense_cash_events WHERE expense_id IN "
                      "(SELECT expense_id FROM expenses WHERE payee=%s)",(payee,))
            assert [float(x[0]) for x in q.fetchall()] == [2000]
