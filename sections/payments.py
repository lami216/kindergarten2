"""Single-currency operator finance: monthly child accounts and audited receipts.

Historical annual receipts remain in protected storage and audit tables, never
converted or deleted, but have no active cash-intake screen.
"""
import streamlit as st
import ui
from sections import monthly_payments


def render(conn):
    ui.section_header("💵", "الدفعات المالية", "المقبوضات والأرصدة بالأوقية القديمة")
    tabs=st.tabs(["📅 حسابات الأطفال", "🧾 الوصولات", "📜 سجل العمليات", "⚙️ إعدادات الرسوم", "📊 تقرير النقدية"])
    with tabs[0]:
        monthly_payments.render_accounts(conn)
    with tabs[1]:
        monthly_payments.render_receipts(conn)
    with tabs[2]:
        monthly_payments.render_history(conn)
    with tabs[3]:
        monthly_payments.render_settings(conn)
    with tabs[4]:
        monthly_payments.render_report(conn)
