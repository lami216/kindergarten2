"""
sections/dashboard.py — لوحة التحكم (الرئيسية)
Organized into clear visual sections with subheadings for improved UI/UX.
"""

import streamlit as st
import ui
from sections.monthly_payments import money_number


def _get_scalar(conn, query, params=()):
    """Executes a scalar SQL query directly via cursor safely."""
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone()
        cur.close()
        if res is None:
            return 0
        if isinstance(res, dict):
            val = list(res.values())[0]
        elif isinstance(res, (tuple, list)):
            val = res[0]
        else:
            val = res
        return val if val is not None else 0
    except Exception:
        return 0


def render(conn):
    ui.section_header("📊", "الرئيسية", "كل ما تحتاجه لإدارة يومك، في مكان واحد")
    actions = st.columns(3)
    if actions[0].button("➕ إضافة طالب", key="home_add_student", type="secondary", use_container_width=True):
        ui.navigate("students")
    if actions[1].button("💵 تسجيل دفعة", key="home_payment", type="secondary", use_container_width=True):
        ui.navigate("payments", payments_requested_tab="📅 حسابات الأطفال")
    if actions[2].button("📦 إضافة مصروف", key="home_expense", type="secondary", use_container_width=True):
        ui.navigate("expenses")

    from monthly_finance import financial_overview, CURRENCY
    try:
        financial = financial_overview(conn)
    except Exception:
        st.error("تعذّر تحميل الملخص المالي. أعد المحاولة.")
        return
    money = money_number
    st.markdown("##### ملخص الروضة")
    st.caption("إجمالي الحركة المسجلة حتى الآن · تقارير الفترات متاحة من صفحة التقارير")
    with st.container(key="dashboard_summary"):
        total_students = int(_get_scalar(conn, "SELECT COUNT(*) FROM students WHERE archived_at IS NULL"))
        c1, c2 = st.columns(2)
        ui.kpi(c1, "🎒", "الطلاب الحاليون", total_students, unit="طالب")
        ui.kpi(c2, "💵", "إجمالي المقبوضات", money(financial["total_cash"]), hint=CURRENCY)
        c3, c4 = st.columns(2)
        ui.kpi(c3, "📦", "إجمالي المصروفات", money(financial["expenses"]),
               bg="#FFF1F2", fg="#BE123C", hint=CURRENCY)
        ui.kpi(c4, "💰", "الباقي من المداخيل", money(financial["remaining_cash"]),
               bg="#E0F2FE", fg="#0369A1", hint=CURRENCY)
        a, b = st.columns(2)
        ui.kpi(a, "⏳", "الباقي على الطلاب", money(financial["due_now"]),
               bg="#FFFBEB", fg="#B45309", unit=CURRENCY)
        ui.kpi(b, "📝", "أطفال سددوا التسجيل", financial["registration_children"], unit="طفل")
        c, _ = st.columns(2)
        ui.kpi(c, "🧥", "جيليه مدفوعة", financial["gilet_count"],
               bg="#F5F3FF", fg="#7C3AED", unit="قطعة")

    with st.expander("تفاصيل المقبوضات", expanded=False):
        a, b, c = st.columns(3)
        ui.kpi(a, "📝", "قبض التسجيل", money(financial["registration_cash"]), hint=CURRENCY)
        ui.kpi(b, "🧥", "قبض الجيليه", money(financial["gilet_cash"]), hint=CURRENCY)
        ui.kpi(c, "📅", "قبض الشهرية", money(financial["monthly_cash"]), hint=CURRENCY)

    with st.container(border=True):
        st.markdown("##### آخر الدفعات")
        recent = ui.df(conn, """
            SELECT s.full_name AS "الطالب", r.amount AS "المبلغ", r.received_on AS "التاريخ"
            FROM monthly_receipts r JOIN students s ON s.student_id=r.student_id
            WHERE r.state='active' AND r.received_on<=%s
            ORDER BY r.received_on DESC,r.receipt_id DESC LIMIT 8
        """, (__import__('monthly_finance').today(),))
        if recent.empty:
            ui.empty_state("لا توجد دفعات مسجلة بعد.")
        else:
            ui.dataframe(recent, hide_index=True, use_container_width=True)
        if st.button("عرض الوصولات", key="home_receipts", use_container_width=True):
            ui.navigate("payments", payments_requested_tab="🧾 الوصولات")
