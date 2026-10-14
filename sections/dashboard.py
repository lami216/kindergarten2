"""
sections/dashboard.py — لوحة التحكم (الرئيسية)
Organized into clear visual sections with subheadings for improved UI/UX.
"""

import streamlit as st
import ui
import helpers as H
import plotly.express as px
from monthly_finance import today as business_today
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
    if actions[0].button("➕ إضافة طالب", key="home_add_student", use_container_width=True):
        ui.navigate("students")
    if actions[1].button("💵 تسجيل دفعة", key="home_payment", type="primary", use_container_width=True):
        ui.navigate("payments", payments_requested_tab="📅 حسابات الأطفال")
    if actions[2].button("📦 إضافة مصروف", key="home_expense", use_container_width=True):
        ui.navigate("expenses")

    from monthly_finance import financial_report, CURRENCY
    from datetime import date
    current = business_today()
    with st.expander("📅 تغيير الفترة المالية", expanded=False):
        a, b = st.columns(2)
        start = a.date_input("بداية الفترة المالية", value=date(current.year, current.month, 1),
                             key="dashboard_finance_start")
        end = b.date_input("نهاية الفترة المالية", value=current, key="dashboard_finance_end")
    if start > end:
        st.error("تاريخ البداية بعد تاريخ النهاية.")
        return
    try:
        financial = financial_report(conn, start, end)
    except Exception:
        st.error("تعذّر تحميل الملخص المالي. أعد المحاولة.")
        return
    money = money_number
    st.markdown("##### ملخص الروضة")
    st.caption(f"الحركة المالية من {start} إلى {end} · جميع المبالغ بـ{CURRENCY}")
    total_students = int(_get_scalar(conn, "SELECT COUNT(*) FROM students WHERE archived_at IS NULL"))
    c1, c2, c3, c4 = st.columns(4)
    ui.kpi(c1, "🎒", "الطلاب الحاليون", total_students, hint="الملفات غير المؤرشفة")
    ui.kpi(c2, "💵", "إجمالي المقبوضات", money(financial["total_cash"]), hint=CURRENCY)
    ui.kpi(c3, "📦", "إجمالي المصروفات", money(financial["expenses"]),
           bg="#FFF1F2", fg="#BE123C", hint=CURRENCY)
    ui.kpi(c4, "💰", "الباقي من المداخيل", money(financial["remaining_cash"]),
           bg="#E0F2FE", fg="#0369A1", hint=CURRENCY)
    a, b, c = st.columns(3)
    ui.kpi(a, "⏳", "الباقي على الطلاب", money(financial["due_now"]),
           bg="#FFFBEB", fg="#B45309", hint=f"المستحق حتى {end} · " + CURRENCY)
    ui.kpi(b, "📝", "أطفال سددوا التسجيل", financial["registration_children"], hint="خلال الفترة المختارة")
    ui.kpi(c, "🧥", "جيليه مدفوعة", financial["gilet_count"],
           bg="#F5F3FF", fg="#7C3AED", hint="خلال الفترة المختارة")

    with st.expander("تفاصيل المقبوضات والالتزامات", expanded=False):
        st.caption("المستحق على الطلاب منفصل عن النقد المتبقي؛ لا يُحسب كمصروف.")
        a, b, c = st.columns(3)
        ui.kpi(a, "📝", "قبض التسجيل", money(financial["registration_cash"]), hint=CURRENCY)
        ui.kpi(b, "🧥", "قبض الجيليه", money(financial["gilet_cash"]), hint=CURRENCY)
        ui.kpi(c, "📅", "قبض الشهرية", money(financial["monthly_cash"]), hint=CURRENCY)
        st.caption(f"من الشهرية {money(financial['prepaid_cash'])} {CURRENCY} مدفوعة مقدمًا.")
        a, b, c = st.columns(3)
        ui.kpi(a, "👩‍🏫", "رواتب مصروفة", money(financial["salary_cash"]), hint=CURRENCY)
        ui.kpi(b, "💳", "سلف مصروفة", money(financial["advance_cash"]), hint=CURRENCY)
        ui.kpi(c, "📦", "تشغيلية مدفوعة", money(financial["operational_cash"]), hint=CURRENCY)
        a, b, c = st.columns(3)
        ui.kpi(a, "📋", "استحقاق الرواتب الشهري", money(_get_scalar(conn,
            "SELECT COALESCE(SUM(salary),0) FROM teachers")), hint=CURRENCY)
        ui.kpi(b, "⏳", "ديون الموردين", money(_get_scalar(conn,
            "SELECT COALESCE(SUM(amount-amount_paid),0) FROM expenses")), hint="غير مدفوعة · " + CURRENCY)
        ui.kpi(c, "🧩", "الأصول والتجهيزات", money(_get_scalar(conn,
            "SELECT COALESCE(SUM(total_cost),0) FROM assets")), hint=CURRENCY)

    with st.expander("📈 الرسوم البيانية وآخر التسجيلات", expanded=False):
        left, right = st.columns([1.3, 1])

        with left:
            with st.container(border=True):
                st.markdown("##### 📈 المقبوضات آخر 6 أشهر")
                rev = ui.df(conn, """
                    SELECT TO_CHAR(received_on, 'YYYY-MM') AS "الشهر", SUM(amount) AS "المبلغ"
                    FROM monthly_receipts
                    WHERE state='active'
                    GROUP BY TO_CHAR(received_on, 'YYYY-MM')
                    ORDER BY TO_CHAR(received_on, 'YYYY-MM') DESC
                    LIMIT 6
                """)
                if rev.empty:
                    ui.empty_state("لا توجد مقبوضات مسجلة بعد.")
                else:
                    rev_sorted = rev.sort_values("الشهر")
                    rev_sorted["الشهر"] = rev_sorted["الشهر"].astype(str)

                    fig_rev = px.bar(rev_sorted, x="الشهر", y="المبلغ", text_auto=True, height=280)
                    fig_rev.update_traces(marker_color="#10B981", marker_line_color="#059669", marker_line_width=1.5, textposition="outside")
                    fig_rev.update_layout(
                        xaxis_title="", yaxis_title="",
                        xaxis=dict(type='category'),
                        margin=dict(l=10, r=10, t=25, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Cairo", size=12)
                    )
                    ui.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})

        with right:
            with st.container(border=True):
                st.markdown("##### 🏷️ توزيع الطلاب على الصفوف")
                dist = ui.df(conn, """
                    SELECT (c.class_type || ' ' || c.section) AS "الصف", COUNT(r.registration_id) AS "العدد"
                    FROM classes c
                    LEFT JOIN registrations r ON r.class_id = c.class_id
                        AND r.year_id = (SELECT year_id FROM academic_years ORDER BY start_date DESC LIMIT 1)
                    GROUP BY c.class_id, c.class_type, c.section
                """)
                if dist.empty:
                    ui.empty_state("لا توجد صفوف بعد.")
                else:
                    dist["الصف"] = dist["الصف"].astype(str)
                    fig_dist = px.bar(dist, x="الصف", y="العدد", text_auto=True, height=280)
                    fig_dist.update_traces(marker_color="#0284C7", marker_line_color="#0369A1", marker_line_width=1.5, textposition="outside")
                    fig_dist.update_layout(
                        xaxis_title="", yaxis_title="",
                        xaxis=dict(type='category'),
                        yaxis=dict(dtick=1),
                        margin=dict(l=10, r=10, t=25, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Cairo", size=12)
                    )
                    ui.plotly_chart(fig_dist, use_container_width=True, config={"displayModeBar": False})

        # Breakdown Charts
        exp_col, ast_col = st.columns(2)

        with exp_col:
            with st.container(border=True):
                st.markdown("##### 💸 المصروفات المدفوعة حسب الفئة")
                exp_chart_df = ui.df(conn, """
                    SELECT category AS "الفئة", SUM(amount_paid) AS "الإجمالي"
                    FROM expenses
                    GROUP BY category
                    ORDER BY "الإجمالي" DESC
                """)
                if exp_chart_df.empty:
                    ui.empty_state("لا توجد مصروفات مسجلة بعد.")
                else:
                    fig_exp = px.pie(
                        exp_chart_df,
                        names="الفئة",
                        values="الإجمالي",
                        hole=0.4,
                        height=280,
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig_exp.update_traces(textinfo="percent+label")
                    fig_exp.update_layout(
                        margin=dict(l=10, r=10, t=25, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Cairo", size=12),
                        showlegend=False
                    )
                    ui.plotly_chart(fig_exp, use_container_width=True, config={"displayModeBar": False})

        with ast_col:
            with st.container(border=True):
                st.markdown("##### 🧸 توزيع الأصول والتجهيزات")
                ast_chart_df = ui.df(conn, """
                    SELECT category AS "الفئة", SUM(total_cost) AS "الإجمالي"
                    FROM assets
                    GROUP BY category
                    ORDER BY "الإجمالي" DESC
                """)
                if ast_chart_df.empty:
                    ui.empty_state("لا توجد أصول أو ألعاب مسجلة بعد.")
                else:
                    fig_ast = px.pie(
                        ast_chart_df,
                        names="الفئة",
                        values="الإجمالي",
                        hole=0.4,
                        height=280,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_ast.update_traces(textinfo="percent+label")
                    fig_ast.update_layout(
                        margin=dict(l=10, r=10, t=25, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Cairo", size=12),
                        showlegend=False
                    )
                    ui.plotly_chart(fig_ast, use_container_width=True, config={"displayModeBar": False})

        # ==================================================================
        # SECTION 6: RECENT ACTIVITY
        # ==================================================================
        with st.container(border=True):
            st.markdown("##### 🕓 آخر عمليات التسجيل")
            recent = ui.df(conn, """
                SELECT s.full_name AS "اسم الطالب", (c.class_type || ' ' || c.section) AS "الصف",
                       r.year_id AS "السنة الدراسية", r.status AS "الحالة"
                FROM registrations r
                JOIN students s ON s.student_id = r.student_id
                JOIN classes c ON c.class_id = r.class_id
                ORDER BY r.registration_id DESC LIMIT 8
            """)
            if recent.empty:
                ui.empty_state("لا توجد تسجيلات بعد.")
            else:
                ui.dataframe(
                    recent,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "الحالة": st.column_config.TextColumn(
                            "الحالة",
                            help="حالة الطالب الحالية"
                        )
                    }
                )
