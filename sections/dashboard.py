"""
sections/dashboard.py — لوحة التحكم (الرئيسية)
Organized into clear visual sections with subheadings for improved UI/UX.
"""

import streamlit as st
import ui
import helpers as H
import plotly.express as px
from datetime import datetime


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
    ui.section_header("📊", "الرئيسية", "نظرة سريعة وشاملة على أداء الروضة والمالية والسيولة")

    current_month = datetime.now().strftime("%Y-%m")

    # ------------------------------------------------------------------
    # Data Queries
    # ------------------------------------------------------------------
    # 1. Operational Counts
    total_students = int(_get_scalar(conn, "SELECT COUNT(*) FROM students"))
    total_teachers = int(_get_scalar(conn, "SELECT COUNT(*) FROM teachers"))
    total_classes = int(_get_scalar(conn, "SELECT COUNT(*) FROM classes"))
    pending = int(_get_scalar(conn, "SELECT COUNT(*) FROM registrations WHERE status = %s", (H.STATUS_NEW,)))

    from monthly_finance import financial_report, today as business_today, CURRENCY
    from datetime import date as business_date

    current=business_today()
    start_col,end_col=st.columns(2)
    start=start_col.date_input("بداية الفترة المالية",
        value=business_date(current.year,current.month,1),key="dashboard_finance_start")
    end=end_col.date_input("نهاية الفترة المالية",
        value=current,key="dashboard_finance_end")
    if start>end:
        st.error("تاريخ البداية بعد تاريخ النهاية.")
        return
    financial=financial_report(conn,start,end)
    money=lambda value: f"{H.format_money(value)} {CURRENCY}"
    total_assets = float(_get_scalar(conn,
        "SELECT COALESCE(SUM(total_cost),0) FROM assets"))
    monthly_salaries_due = float(_get_scalar(conn,
        "SELECT COALESCE(SUM(salary),0) FROM teachers"))
    total_supplier_debts = float(_get_scalar(conn,
        "SELECT COALESCE(SUM(amount-amount_paid),0) FROM expenses"))

    # ==================================================================
    # SECTION 1: ENTITIES & OPERATIONAL COUNTS
    # ==================================================================
    st.markdown("##### 👥 الأعداد  ")
    c1, c2, c3, c4, c5 = st.columns(5)
    ui.kpi(c1, "🎒", "إجمالي الطلاب", total_students, bg="#E9F5EC", fg="#219044")
    ui.kpi(c2, "👩‍🏫", "المعلمات", total_teachers, bg="#F0F9FF", fg="#0284C7")
    ui.kpi(c3, "🏷️", "الصفوف", total_classes, bg="#F5F3FF", fg="#7C3AED")
    ui.kpi(c4, "⏳", "طلبات بانتظار التحديد", pending, bg="#FEF3C7", fg="#D97706")
    ui.kpi(c5, "🧩", "استثمار الأصول والألعاب", money(total_assets), bg="#F0FDF4", fg="#15803D")

    st.markdown("---")

    # ==================================================================
    # SECTION 2: Single-currency receipt and actual cash-outflow projection
    # ==================================================================
    st.markdown("##### 💰 المقبوضات والسيولة بالأوقية القديمة")
    r1,r2,r3=st.columns(3)
    ui.kpi(r1,"💵","إجمالي المقبوضات",money(financial["total_cash"]),bg="#ECFDF5",fg="#059669")
    ui.kpi(r2,"💸","إجمالي المصروفات",money(financial["expenses"]),bg="#FFF1F2",fg="#BE123C")
    ui.kpi(r3,"📊","الباقي من المداخيل",money(financial["remaining_cash"]),bg="#E0F2FE",fg="#0369A1")
    r4,r5,r6=st.columns(3)
    # Unit is stated in the section title and adjacent cash cards.  A long
    # currency suffix would clip this native metric at tablet widths.
    r4.metric("الباقي على الطلاب",H.format_money(financial["due_now"]))
    r5.metric("أطفال سددوا التسجيل",financial["registration_children"])
    r6.metric("جيليه مدفوعة",financial["gilet_count"])
    st.caption(f"تسجيل {money(financial['registration_cash'])} · "
               f"جيليه {money(financial['gilet_cash'])} · "
               f"أشهر {money(financial['monthly_cash'])} "
               f"(منها مقدم {money(financial['prepaid_cash'])}، وليس إيراداً إضافياً)")
    st.caption("الديون المستحقة على الأطفال لا تُخصم من المقبوضات كأنها مصروف.")

    st.markdown("---")
    st.markdown("##### 💸 التزامات منفصلة عن النقدية المصروفة")
    e1,e2,e3=st.columns(3)
    ui.kpi(e1,"📋","استحقاق الرواتب الشهري",money(monthly_salaries_due),bg="#FFFBEB",fg="#B45309")
    ui.kpi(e2,"📦","تشغيلية مدفوعة",money(financial["operational_cash"]),bg="#FFF1F2",fg="#BE123C")
    ui.kpi(e3,"💳","ديون الموردين (غير مدفوعة)",money(total_supplier_debts),bg="#FFFBEB",fg="#B45309")
    st.caption(f"رواتب مصروفة {money(financial['salary_cash'])} · "
               f"سلف مدفوعة {money(financial['advance_cash'])} (كل صرف مرة واحدة).")
    st.markdown("---")

    # ==================================================================
        # SECTION 5: CHARTS AND VISUAL ANALYTICS
    # ==================================================================
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