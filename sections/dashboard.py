"""
sections/dashboard.py — لوحة التحكم (الرئيسية)
Organized into clear visual sections with subheadings and a comprehensive executive summary report.
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
    ui.section_header("📊", "الرئيسية", "نظرة سريعة وشاملة على أداء الروضة والمالية والسيولة")[cite: 5]

    current_month = datetime.now().strftime("%Y-%m")

    # ------------------------------------------------------------------
    # Data Queries
    # ------------------------------------------------------------------
    # 1. Operational Counts
    total_students = int(_get_scalar(conn, "SELECT COUNT(*) FROM students"))[cite: 5]
    total_teachers = int(_get_scalar(conn, "SELECT COUNT(*) FROM teachers"))[cite: 5]
    total_classes = int(_get_scalar(conn, "SELECT COUNT(*) FROM classes"))[cite: 5]
    pending = int(_get_scalar(conn, "SELECT COUNT(*) FROM registrations WHERE status = %s", (H.STATUS_NEW,)))[cite: 5]

    # 2. Revenue & Student Receivables
    total_revenue = float(_get_scalar(conn, "SELECT COALESCE(SUM(amount), 0) FROM payments"))[cite: 5]
    
    total_student_outstanding = float(_get_scalar(conn, """
        SELECT COALESCE(SUM(GREATEST(0, COALESCE(r.annual_tuition, 3500.0) - COALESCE(p.paid, 0))), 0)
        FROM registrations r
        LEFT JOIN (
            SELECT registration_id, SUM(amount) AS paid
            FROM payments
            WHERE payment_for IN ('رسوم تسجيل', 'أقساط تعليمية')
            GROUP BY registration_id
        ) p ON p.registration_id = r.registration_id
        WHERE r.year_id = (SELECT year_id FROM academic_years ORDER BY start_date DESC LIMIT 1)
    """))[cite: 5]

    # 3. Expenses Breakdown & Capital Assets
    total_expenses_paid = float(_get_scalar(conn, "SELECT COALESCE(SUM(amount_paid), 0) FROM expenses"))[cite: 5]
    total_supplier_debts = float(_get_scalar(conn, "SELECT COALESCE(SUM(amount - amount_paid), 0) FROM expenses"))[cite: 5]
    total_assets = float(_get_scalar(conn, "SELECT COALESCE(SUM(total_cost), 0) FROM assets"))[cite: 5]

    # 4. Monthly Cash Flow Health Indicators
    monthly_salaries_due = float(_get_scalar(conn, "SELECT COALESCE(SUM(salary), 0) FROM teachers"))[cite: 5]
    
    monthly_student_income = float(_get_scalar(conn, """
        SELECT COALESCE(SUM(amount), 0) 
        FROM payments 
        WHERE TO_CHAR(payment_date::date, 'YYYY-MM') = %s
    """, (current_month,)))[cite: 5]

    monthly_salaries_paid = float(_get_scalar(conn, """
        SELECT COALESCE(SUM(amount), 0) 
        FROM teacher_payments 
        WHERE salary_month = %s
    """, (current_month,)))[cite: 5]

    monthly_expenses_paid = float(_get_scalar(conn, """
        SELECT COALESCE(SUM(amount_paid), 0) 
        FROM expenses 
        WHERE TO_CHAR(expense_date::date, 'YYYY-MM') = %s
    """, (current_month,)))[cite: 5]

    total_monthly_cash_outflow = monthly_salaries_paid + monthly_expenses_paid[cite: 5]

    # ==================================================================
    # SECTION 1: ENTITIES & OPERATIONAL COUNTS
    # ==================================================================
    st.markdown("##### 👥 الأعداد  ")[cite: 5]
    c1, c2, c3, c4, c5 = st.columns(5)[cite: 5]
    ui.kpi(c1, "🎒", "إجمالي الطلاب", total_students, bg="#E9F5EC", fg="#219044")[cite: 5]
    ui.kpi(c2, "👩‍🏫", "المعلمات", total_teachers, bg="#F0F9FF", fg="#0284C7")[cite: 5]
    ui.kpi(c3, "🏷️", "الصفوف", total_classes, bg="#F5F3FF", fg="#7C3AED")[cite: 5]
    ui.kpi(c4, "⏳", "طلبات بانتظار التحديد", pending, bg="#FEF3C7", fg="#D97706")[cite: 5]
    ui.kpi(c5, "🧩", "استثمار الأصول والألعاب", H.format_money(total_assets), bg="#F0FDF4", fg="#15803D")[cite: 5]

    st.markdown("---")[cite: 5]

    # ==================================================================
    # SECTION 2: REVENUE & STUDENT RECEIVABLES
    # ==================================================================
    st.markdown("##### 💰 المقبوضات والديون المتبقية (الطلاب)")[cite: 5]
    r1, r2 = st.columns(2)[cite: 5]
    ui.kpi(r1, "💵", "إجمالي مقبوضات الطلاب", H.format_money(total_revenue), bg="#ECFDF5", fg="#059669")[cite: 5]
    ui.kpi(r2, "🧾", "ديون الطلاب المتبقية (أقساط)", H.format_money(total_student_outstanding), bg="#FFE4E6", fg="#E11D48")[cite: 5]

    st.markdown("---")[cite: 5]

    # ==================================================================
    # SECTION 3: EXPENDITURES, LIABILITIES & ASSETS
    # ==================================================================
    st.markdown("##### 💸 الاتزامات")[cite: 5]
    e1, e2, e3 = st.columns(3)[cite: 5]
    ui.kpi(e1, "📋", "استحقاق الرواتب الشهري", H.format_money(monthly_salaries_due), bg="#FFFBEB", fg="#B45309")[cite: 5]
    ui.kpi(e2, "💸", "المصروفات المدفوعة فعلياً", H.format_money(total_expenses_paid), bg="#FFF1F2", fg="#BE123C")[cite: 5]
    ui.kpi(e3, "💳", "ديون الموردين والالتزامات (آجل)", H.format_money(total_supplier_debts), bg="#FFFBEB", fg="#B45309")[cite: 5]

    st.markdown("---")[cite: 5]

    # ==================================================================
    # SECTION 4: MONTHLY CASH FLOW HEALTH CHECK
    # ==================================================================
    st.markdown(f"##### 🗓️ الميزانية والسيولة التشغيلية لشهر ({current_month})")[cite: 5]
    p1, p2 = st.columns(2)[cite: 5]
    ui.kpi(p1, "💵", "مقبوضات الطلاب (هذا الشهر)", H.format_money(monthly_student_income), bg="#E0F2FE", fg="#0369A1")[cite: 5]
    ui.kpi(p2, "📦", "السيولة الخارجة (رواتب + مصروفات)", H.format_money(total_monthly_cash_outflow), bg="#FEF2F2", fg="#991B1B")[cite: 5]

    net_monthly_margin = monthly_student_income - total_monthly_cash_outflow[cite: 5]
    st.write("")[cite: 5]
    if net_monthly_margin < 0:
        st.error(
            f"⚠️ **تنبيه سيولة مالية:** تحصيلات الطلاب لهذا الشهر ({H.format_money(monthly_student_income)} شيكل) "
            f"**أقل من** السيولة الخارجة للرواتب والمصروفات ({H.format_money(total_monthly_cash_outflow)} شيكل) "
            f"بعجز قدره: **{H.format_money(abs(net_monthly_margin))} شيكل**."
        )[cite: 5]
    else:
        st.success(
            f"✅ **السيولة المالية ممتازة:** دخل الطلاب لهذا الشهر يُغطي الرواتب والمصروفات المدفوعة "
            f"بفائض تشغيلي قدره **{H.format_money(net_monthly_margin)} شيكل**."
        )[cite: 5]

    st.markdown("---")[cite: 5]

    # ==================================================================
    # SECTION 5: CHARTS AND VISUAL ANALYTICS
    # ==================================================================
    left, right = st.columns([1.3, 1])[cite: 5]

    with left:
        with st.container(border=True):
            st.markdown("##### 📈 المقبوضات آخر 6 أشهر")[cite: 5]
            rev = ui.df(conn, """
                SELECT TO_CHAR(payment_date::date, 'YYYY-MM') AS "الشهر", SUM(amount) AS "المبلغ"
                FROM payments
                GROUP BY TO_CHAR(payment_date::date, 'YYYY-MM')
                ORDER BY TO_CHAR(payment_date::date, 'YYYY-MM') DESC
                LIMIT 6
            """)[cite: 5]
            if rev.empty:
                ui.empty_state("لا توجد مقبوضات مسجلة بعد.")[cite: 5]
            else:
                rev_sorted = rev.sort_values("الشهر")[cite: 5]
                rev_sorted["الشهر"] = rev_sorted["الشهر"].astype(str)[cite: 5]
                
                fig_rev = px.bar(rev_sorted, x="الشهر", y="المبلغ", text_auto=True, height=280)[cite: 5]
                fig_rev.update_traces(marker_color="#10B981", marker_line_color="#059669", marker_line_width=1.5, textposition="outside")[cite: 5]
                fig_rev.update_layout(
                    xaxis_title="", yaxis_title="", 
                    xaxis=dict(type='category'), 
                    margin=dict(l=10, r=10, t=25, b=10), 
                    paper_bgcolor="rgba(0,0,0,0)", 
                    plot_bgcolor="rgba(0,0,0,0)", 
                    font=dict(family="Cairo", size=12)
                )[cite: 5]
                st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})[cite: 5]

    with right:
        with st.container(border=True):
            st.markdown("##### 🏷️ توزيع الطلاب على الصفوف")[cite: 5]
            dist = ui.df(conn, """
                SELECT (c.class_type || ' ' || c.section) AS "الصف", COUNT(r.registration_id) AS "العدد"
                FROM classes c
                LEFT JOIN registrations r ON r.class_id = c.class_id
                    AND r.year_id = (SELECT year_id FROM academic_years ORDER BY start_date DESC LIMIT 1)
                GROUP BY c.class_id, c.class_type, c.section
            """)[cite: 5]
            if dist.empty:
                ui.empty_state("لا توجد صفوف بعد.")[cite: 5]
            else:
                dist["الصف"] = dist["الصف"].astype(str)[cite: 5]
                fig_dist = px.bar(dist, x="الصف", y="العدد", text_auto=True, height=280)[cite: 5]
                fig_dist.update_traces(marker_color="#0284C7", marker_line_color="#0369A1", marker_line_width=1.5, textposition="outside")[cite: 5]
                fig_dist.update_layout(
                    xaxis_title="", yaxis_title="", 
                    xaxis=dict(type='category'), 
                    yaxis=dict(dtick=1), 
                    margin=dict(l=10, r=10, t=25, b=10), 
                    paper_bgcolor="rgba(0,0,0,0)", 
                    plot_bgcolor="rgba(0,0,0,0)", 
                    font=dict(family="Cairo", size=12)
                )[cite: 5]
                st.plotly_chart(fig_dist, use_container_width=True, config={"displayModeBar": False})[cite: 5]

    # Breakdown Charts
    exp_col, ast_col = st.columns(2)[cite: 5]

    with exp_col:
        with st.container(border=True):
            st.markdown("##### 💸 المصروفات المدفوعة حسب الفئة")[cite: 5]
            exp_chart_df = ui.df(conn, """
                SELECT category AS "الفئة", SUM(amount_paid) AS "الإجمالي"
                FROM expenses
                GROUP BY category
                ORDER BY "الإجمالي" DESC
            """)[cite: 5]
            if exp_chart_df.empty:
                ui.empty_state("لا توجد مصروفات مسجلة بعد.")[cite: 5]
            else:
                fig_exp = px.pie(
                    exp_chart_df, 
                    names="الفئة", 
                    values="الإجمالي", 
                    hole=0.4,
                    height=280,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )[cite: 5]
                fig_exp.update_traces(textinfo="percent+label")[cite: 5]
                fig_exp.update_layout(
                    margin=dict(l=10, r=10, t=25, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Cairo", size=12),
                    showlegend=False
                )[cite: 5]
                st.plotly_chart(fig_exp, use_container_width=True, config={"displayModeBar": False})[cite: 5]

    with ast_col:
        with st.container(border=True):
            st.markdown("##### 🧸 توزيع الأصول والتجهيزات")[cite: 5]
            ast_chart_df = ui.df(conn, """
                SELECT category AS "الفئة", SUM(total_cost) AS "الإجمالي"
                FROM assets
                GROUP BY category
                ORDER BY "الإجمالي" DESC
            """)[cite: 5]
            if ast_chart_df.empty:
                ui.empty_state("لا توجد أصول أو ألعاب مسجلة بعد.")[cite: 5]
            else:
                fig_ast = px.pie(
                    ast_chart_df, 
                    names="الفئة", 
                    values="الإجمالي", 
                    hole=0.4,
                    height=280,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )[cite: 5]
                fig_ast.update_traces(textinfo="percent+label")[cite: 5]
                fig_ast.update_layout(
                    margin=dict(l=10, r=10, t=25, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Cairo", size=12),
                    showlegend=False
                )[cite: 5]
                st.plotly_chart(fig_ast, use_container_width=True, config={"displayModeBar": False})[cite: 5]

    # ==================================================================
    # SECTION 6: RECENT ACTIVITY
    # ==================================================================
    with st.container(border=True):
        st.markdown("##### 🕓 آخر عمليات التسجيل")[cite: 5]
        recent = ui.df(conn, """
            SELECT s.full_name AS "اسم الطالب", (c.class_type || ' ' || c.section) AS "الصف",
                   r.year_id AS "السنة الدراسية", r.status AS "الحالة"
            FROM registrations r
            JOIN students s ON s.student_id = r.student_id
            JOIN classes c ON c.class_id = r.class_id
            ORDER BY r.registration_id DESC LIMIT 8
        """)[cite: 5]
        if recent.empty:
            ui.empty_state("لا توجد تسجيلات بعد.")[cite: 5]
        else:
            st.dataframe(
                recent,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "الحالة": st.column_config.TextColumn(
                        "الحالة",
                        help="حالة الطالب الحالية"
                    )
                }
            )[cite: 5]

    st.markdown("---")

    # ==================================================================
    # SECTION 7: EXECUTIVE SUMMARY REPORT & MANAGEMENT OVERVIEW
    # ==================================================================
    with st.container(border=True):
        st.markdown("### 📋 التقرير التنفيذي الشامل للإدارة العليا")
        st.markdown("ملخص تحليل الأداء المؤسسي، المالي، والتشغيلي للروضة جاهز للعرض والمراجعة.")

        col_exec1, col_exec2, col_exec3 = st.columns(3)
        col_exec1.metric("إجمالي الإيرادات المحصلة", H.format_money(total_revenue))
        col_exec2.metric("إجمالي المصروفات المدفوعة", H.format_money(total_expenses_paid))
        col_exec3.metric("إجمالي الأصول والموجودات", H.format_money(total_assets))

        st.markdown("")
        st.markdown("#### 📌 المؤشرات الرئيسية:")
        st.markdown(f"""
        - **إجمالي الكادر والطلاب:** {total_students} طالب/ة موزعين على {total_classes} صفوف، بإشراف {total_teachers} معلمات.
        - **الذمم والديون المتبقية:** إجمالي الأقساط غير المسددة للطلاب بلغت **{H.format_money(total_student_outstanding)} شيكل**، بينما بلغت التزامات الموردين الآجلة **{H.format_money(total_supplier_debts)} شيكل**.
        - **السيولة الشهرية الحالية ({current_month}):** تحصيلات الطلاب بلغت **{H.format_money(monthly_student_income)} شيكل** مقابل منصرفات تشغيلية ورواتب بقيمة **{H.format_money(total_monthly_cash_outflow)} شيكل**.
        """)

        if st.button("🖨️ طباعة وتصدير التقرير التنفيذي الشامل", use_container_width=True):
            st.success("✨ تم اعتماد التقرير التنفيذي بنجاح. يمكنك استخدام قسم (التقارير والتصدير) لتوليد ملفات PDF أفقية أو Excel مخصصة لأي بند حسب الحاجة.")