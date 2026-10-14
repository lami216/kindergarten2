"""
sections/reports.py — التقارير والتصدير

Filtered report views with robust filtering (by class, year, date ranges), 
customizable column selection, summary metrics, landscape PDF printouts, 
and a comprehensive executive management analysis report.
"""

import io
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
from datetime import datetime

import ui
import helpers as H


def _to_excel(df: pd.DataFrame) -> bytes:
    """Helper to convert DataFrame to Excel binary stream."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='التقرير')
    return output.getvalue()


def _render_printable_report_pdf(
    report_title: str,
    meta_info: dict,
    df: pd.DataFrame,
    summary_metrics: dict,
):
    """Renders a print-ready iframe with a landscape PDF layout, letterhead, and summary footer."""
    
    headers_html = "".join([f"<th>{col}</th>" for col in df.columns])
    
    rows_html = ""
    for _, row in df.iterrows():
        cells = "".join([f"<td>{str(val) if pd.notna(val) else ''}</td>" for val in row])
        rows_html += f"<tr>{cells}</tr>"

    logo_img_tag = ui.logo_html()

    meta_html = "".join([f"<div><strong>{k}:</strong> {v}</div>" for k, v in meta_info.items()])

    summary_html = ""
    if summary_metrics:
        summary_items = "".join([f'<div class="summary-card"><span>{k}</span><strong>{v}</strong></div>' for k, v in summary_metrics.items()])
        summary_html = f"""
        <div class="summary-section">
            <div class="summary-title">📊 الملخص الإحصائي المالي والإداري</div>
            <div class="summary-grid">{summary_items}</div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
    <meta charset="utf-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        * {{
            box-sizing: border-box;
            font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
        }}
        body {{
            direction: rtl;
            text-align: right;
            margin: 0;
            padding: 15px;
            background: #fff;
            color: #1F2A22;
        }}
        .print-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 2px solid #163D22;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        .header-brand {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header-brand img {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
        }}
        .brand-titles .ar {{ font-size: 15px; font-weight: 800; color: #163D22; }}
        .brand-titles .en {{ font-size: 10px; color: #7C8A7E; }}
        .report-meta {{
            text-align: left;
            font-size: 12px;
            color: #475569;
        }}
        .report-title {{
            text-align: center;
            font-size: 18px;
            font-weight: 800;
            color: #163D22;
            margin: 10px 0 15px 0;
            background: #FAF9F5;
            padding: 6px;
            border-radius: 6px;
            border: 1px dashed #D7A431;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 5px;
            margin-bottom: 15px;
        }}
        th, td {{
            border: 1px solid #CBD5E1;
            padding: 6px 8px;
            text-align: center;
        }}
        th {{
            background-color: #163D22;
            color: white;
            font-weight: 700;
            font-size: 12px;
        }}
        tr:nth-child(even) {{
            background-color: #F8FAFC;
        }}
        .summary-section {{
            margin-top: 20px;
            border: 1px solid #163D22;
            border-radius: 8px;
            padding: 10px;
            background: #FAF9F5;
        }}
        .summary-title {{
            font-size: 13px;
            font-weight: 800;
            color: #163D22;
            margin-bottom: 8px;
            text-align: center;
        }}
        .summary-grid {{
            display: flex;
            justify-content: space-around;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .summary-card {{
            background: #fff;
            border: 1px solid #D7A431;
            border-radius: 6px;
            padding: 6px 14px;
            text-align: center;
            min-width: 140px;
        }}
        .summary-card span {{
            display: block;
            font-size: 11px;
            color: #7C8A7E;
        }}
        .summary-card strong {{
            display: block;
            font-size: 14px;
            color: #163D22;
            margin-top: 2px;
        }}
        .print-btn {{
            display: block;
            width: 100%;
            background: #163D22;
            color: white;
            border: none;
            padding: 10px 0;
            font-size: 14px;
            font-weight: 700;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 15px;
        }}
        .print-btn:hover {{
            opacity: 0.9;
        }}

        @media print {{
            .print-btn {{ display: none; }}
            body {{ padding: 0; }}
            @page {{
                size: A4 landscape;
                margin: 10mm;
            }}
        }}
    </style>
    </head>
    <body>
        <button class="print-btn" onclick="window.print()">🖨️ اضغط هنا للطباعة أو الحفظ كـ PDF</button>

        <div class="print-header">
            <div class="header-brand">
                {logo_img_tag}
                <div class="brand-titles">
                    <div class="ar">روضة أطفال فودي حبيب ساكرا</div>
                    <div class="en">Jardin d’enfant FODIYE HABIB SAKERA</div>
                </div>
            </div>
            <div class="report-meta">
                {meta_html}
                <div><strong>تاريخ الاستخراج:</strong> {H.today_str()}</div>
            </div>
        </div>

        <div class="report-title">
            {report_title} ({len(df)} سجل)
        </div>

        <table>
            <thead>
                <tr>{headers_html}</tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        {summary_html}
    </body>
    </html>
    """
    
    height = 720 if len(df) > 10 else 520
    components.html(html_content, height=height, scrolling=True)


def _get_scalar(conn, query, params=()):
    """Executes a scalar SQL query safely."""
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
    ui.section_header("📈", "التقارير والتصدير", "استخراج بيانات مفلترة وتصديرها وإدارتها")

    report_type = st.radio(
        "اختر نوع التقرير",
        [
            "📑 تقرير الإدارة العليا الشامل (التحليلي والمالي)",
            "📅 تقرير الحسابات الشهرية (أوقية قديمة)",
            "🏫 كشف الطلاب حسب الصف (للحضور والغياب)",
            "💵 سجل المقبوضات المالية",
            "👨‍👩‍👧‍👦 قائمة الطلاب وأولياء الأمور",
            "📋 قائمة التسجيلات",
            "⚠️ كشف الديون والذمم المتبقية",
            "💼 سجل الرواتب والمستحقات",
            "💸 تقرير المصروفات التشغيلية",
            "🏛️ تقرير الأصول والموجودات الثابتة",
        ],
        horizontal=True,
    )

    st.markdown("---")

    result = pd.DataFrame()
    meta_info = {}
    report_title_str = ""
    summary_metrics = {}

    years_df = ui.df(conn, "SELECT year_id FROM academic_years ORDER BY year_id DESC")
    # Financial reports are independent of academic setup. Never invent a
    # year or access a nonexistent fallback when the year table is empty.
    year_list = years_df['year_id'].tolist() if not years_df.empty else []

    classes_df = ui.df(conn, """
        SELECT c.class_id, (c.class_type || ' ' || c.section) AS class_name
        FROM classes c
        ORDER BY c.class_type, c.section
    """)

    if report_type == "📅 تقرير الحسابات الشهرية (أوقية قديمة)":
        from sections.monthly_payments import render_report
        render_report(conn)
        return

    # --------------------------------------------------------------------------
    # 0. EXECUTIVE MANAGEMENT COMPREHENSIVE REPORT
    # --------------------------------------------------------------------------
    if report_type == "📑 تقرير الإدارة العليا الشامل (التحليلي والمالي)":
        import monthly_finance as F
        current=F.today()
        c1,c2=st.columns(2)
        start=c1.date_input("من تاريخ",value=current.replace(day=1),key="exec_finance_start")
        end=c2.date_input("إلى تاريخ",value=current,key="exec_finance_end")
        if start>end:
            st.error("تاريخ البداية بعد تاريخ النهاية.")
            return
        summary=F.financial_report(conn,start,end)
        money=lambda n: f"{H.format_money(n)} {F.CURRENCY}"
        students_count=int(_get_scalar(conn,"SELECT COUNT(*) FROM students"))
        teachers_count=int(_get_scalar(conn,"SELECT COUNT(*) FROM teachers"))
        classes_count=int(_get_scalar(conn,"SELECT COUNT(*) FROM classes"))
        assets=_get_scalar(conn,"SELECT COALESCE(SUM(total_cost),0) FROM assets")
        st.markdown("### 📑 تقرير إدارة الروضة")
        a,b,c=st.columns(3)
        a.metric("الطلاب",students_count)
        b.metric("المعلمات",teachers_count)
        c.metric("الصفوف",classes_count)
        a,b,c=st.columns(3)
        a.metric("إجمالي المقبوضات",money(summary["total_cash"]))
        b.metric("إجمالي المصروفات",money(summary["expenses"]))
        c.metric("الباقي من المداخيل",money(summary["remaining_cash"]))
        a,b,c=st.columns(3)
        a.metric("أطفال سددوا التسجيل",summary["registration_children"])
        b.metric("جيليه مدفوعة",summary["gilet_count"])
        c.metric("الباقي على الطلاب",money(summary["due_now"]))
        details=pd.DataFrame([
            {"البند":"التسجيل المقبوض","المبلغ":money(summary["registration_cash"])},
            {"البند":"الجيليه المقبوض","المبلغ":money(summary["gilet_cash"])},
            {"البند":"الشهور المقبوضة","المبلغ":money(summary["monthly_cash"])},
            {"البند":"منها دفعات مقدمة، ضمن الشهور","المبلغ":money(summary["prepaid_cash"])},
            {"البند":"المصروفات التشغيلية النقدية","المبلغ":money(summary["operational_cash"])},
            {"البند":"الرواتب المصروفة","المبلغ":money(summary["salary_cash"])},
            {"البند":"السلف المصروفة","المبلغ":money(summary["advance_cash"])},
            {"البند":"قيمة الأصول الثابتة","المبلغ":money(assets)},
        ])
        ui.dataframe(details,use_container_width=True,hide_index=True)
        st.caption("الدفعات المقدمة ضمن المقبوضات مرة واحدة. "
                   "الذمم على الطلاب لا تُطرح من النقدية، والرواتب المستحقة غير المصروفة ليست مصروفاً.")
        if st.button("🖨️ معاينة وطباعة تقرير الإدارة (PDF)"):
            _render_printable_report_pdf("تقرير الإدارة",{
                "الفترة":f"{start} إلى {end}","العملة":F.CURRENCY},details,{
                "إجمالي المقبوضات":money(summary["total_cash"]),
                "إجمالي المصروفات":money(summary["expenses"]),
                "الباقي من المداخيل":money(summary["remaining_cash"])})
        return

    # --------------------------------------------------------------------------
    # 1. CLASS ROSTER & ATTENDANCE SHEET REPORT
    # --------------------------------------------------------------------------
    elif report_type == "🏫 كشف الطلاب حسب الصف (للحضور والغياب)":
        if classes_df.empty:
            ui.empty_state("لا توجد صفوف معرفة في النظام.")
            return

        c1, c2, c3 = st.columns(3)
        class_options = dict(zip(classes_df['class_name'], classes_df['class_id']))
        selected_class_name = c1.selectbox("اختر الصف *", list(class_options.keys()))
        selected_class_id = class_options[selected_class_name]

        selected_year = c2.selectbox("السنة الدراسية", year_list)
        include_attendance_cols = c3.checkbox("إضافة أعمدة لتسجيل الحضور والغياب", value=True)

        query = """
            SELECT 
                s.student_id AS "رقم الهوية",
                s.full_name AS "اسم الطالب",
                s.gender AS "الجنس",
                s.birth_date AS "تاريخ الميلاد",
                p.father_name AS "اسم الأب",
                p.father_mobile AS "جوال الأب",
                p.mother_name AS "اسم الأم",
                r.status AS "حالة التسجيل"
            FROM registrations r
            JOIN students s ON r.student_id = s.student_id
            JOIN parents p ON s.father_id = p.father_id
            WHERE r.class_id = %s AND r.year_id = %s
            ORDER BY s.full_name ASC
        """
        result = ui.df(conn, query, (selected_class_id, selected_year))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            if include_attendance_cols:
                for day in ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "ملاحظات"]:
                    result[day] = ""

            meta_info = {"الصف": selected_class_name, "السنة الدراسية": selected_year}
            report_title_str = f"كشف أسماء الطلاب {'والحضور' if include_attendance_cols else ''} — {selected_class_name}"
            
            male_count = len(result[result['الجنس'] == 'ذكر']) if 'الجنس' in result.columns else 0
            female_count = len(result[result['الجنس'] == 'أنثى']) if 'الجنس' in result.columns else 0
            summary_metrics = {
                "إجمالي عدد الطلاب": f"{len(result)} طالب/ة",
                "عدد الذكور": f"{male_count}",
                "عدد الإناث": f"{female_count}"
            }

    # --------------------------------------------------------------------------
    # 2. FINANCIAL CASH RECEIPTS REPORT
    # --------------------------------------------------------------------------
    elif report_type == "💵 سجل المقبوضات المالية":
        import monthly_finance as F
        c1,c2=st.columns(2)
        start=c1.date_input("من تاريخ",value=F.today().replace(day=1),key="receipt_report_start")
        end=c2.date_input("إلى تاريخ",value=F.today(),key="receipt_report_end")
        if start>end:
            st.error("تاريخ البداية بعد تاريخ النهاية.")
            return
        result=ui.df(conn,"""
            SELECT r.receipt_id AS "رقم الوصل",s.full_name AS "اسم الطالب",
                r.received_on AS "تاريخ القبض",r.amount AS "المبلغ",
                r.payer AS "الدافع",CASE WHEN r.state='active' THEN 'ساري'
                    ELSE 'ملغى' END AS "حالة الوصل"
            FROM monthly_receipts r JOIN students s ON s.student_id=r.student_id
            WHERE r.received_on BETWEEN %s AND %s ORDER BY r.receipt_id DESC
        """,(start,end))
        report=F.financial_report(conn,start,end)
        report_title_str="سجل المقبوضات المالية بالأوقية القديمة"
        meta_info={"الفترة":f"{start} إلى {end}","العملة":F.CURRENCY}
        summary_metrics={
            "إجمالي المقبوضات":f"{report['total_cash']:,} {F.CURRENCY}",
            "الوصولات السارية":str((result["حالة الوصل"]=="ساري").sum()) if not result.empty else "0"
        }

    # --------------------------------------------------------------------------
    # 3. STUDENTS & GUARDIANS REGISTRY
    # --------------------------------------------------------------------------
    elif report_type == "👨‍👩‍👧‍👦 قائمة الطلاب وأولياء الأمور":
        c1, c2 = st.columns(2)
        gender_filter = c1.selectbox("الجنس", ["الكل", "ذكر", "أنثى"])
        class_filter_options = ["الكل"] + list(classes_df['class_name']) if not classes_df.empty else ["الكل"]
        selected_class_filter = c2.selectbox("تصفية حسب الصف الحالي", class_filter_options)

        query = """
            SELECT DISTINCT s.student_id AS "رقم هوية الطالب", s.full_name AS "اسم الطالب",
                   s.birth_date AS "تاريخ الميلاد", s.gender AS "الجنس",
                   p.father_name AS "اسم الأب", p.father_mobile AS "جوال الأب",
                   p.mother_name AS "اسم الأم", p.address AS "العنوان",
                   (c.class_type || ' ' || c.section) AS "الصف الحالي"
            FROM students s 
            JOIN parents p ON s.father_id = p.father_id
            LEFT JOIN registrations r ON s.student_id = r.student_id
            LEFT JOIN classes c ON r.class_id = c.class_id
            WHERE 1=1
        """
        params = []
        if gender_filter != "الكل":
            query += " AND s.gender = %s"
            params.append(gender_filter)
        if selected_class_filter != "الكل":
            query += " AND (c.class_type || ' ' || c.section) = %s"
            params.append(selected_class_filter)

        query += " ORDER BY s.full_name ASC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            meta_info = {"الجنس": gender_filter, "الصف": selected_class_filter}
            report_title_str = "قائمة الطلاب وأولياء الأمور"
            summary_metrics = {
                "إجمالي الطلاب": f"{len(result)} طالب/ة"
            }

    # --------------------------------------------------------------------------
    # 4. REGISTRATION LIST
    # --------------------------------------------------------------------------
    elif report_type == "📋 قائمة التسجيلات":
        c1, c2, c3 = st.columns(3)
        year_filter = c1.selectbox("السنة الدراسية", ["الكل"] + year_list)
        class_filter_options = ["الكل"] + list(classes_df['class_name']) if not classes_df.empty else ["الكل"]
        selected_class_filter = c2.selectbox("الصف", class_filter_options)
        status_filter = c3.selectbox("حالة التسجيل", ["الكل", "مسجل", "انسحب", "مؤجل"])

        query = """
            SELECT s.full_name AS "اسم الطالب", (c.class_type || ' ' || c.section) AS "الصف",
                   r.year_id AS "السنة الدراسية", r.status AS "الحالة", r.registration_date AS "تاريخ التسجيل"
            FROM registrations r
            JOIN students s ON r.student_id = s.student_id
            JOIN classes c ON c.class_id = r.class_id
            WHERE 1=1
        """
        params = []
        if year_filter != "الكل":
            query += " AND r.year_id = %s"
            params.append(year_filter)
        if selected_class_filter != "الكل":
            query += " AND (c.class_type || ' ' || c.section) = %s"
            params.append(selected_class_filter)
        if status_filter != "الكل":
            query += " AND r.status = %s"
            params.append(status_filter)

        query += " ORDER BY r.registration_id DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            meta_info = {"السنة": year_filter, "الصف": selected_class_filter, "الحالة": status_filter}
            report_title_str = "قائمة التسجيلات"
            active_count = len(result[result['الحالة'] == 'مسجل']) if 'الحالة' in result.columns else len(result)
            summary_metrics = {
                "إجمالي التسجيلات": f"{len(result)} تسجيل",
                "الطلاب المنتظمين": f"{active_count}"
            }

    # --------------------------------------------------------------------------
    # 5. OUTSTANDING BALANCES / DEBTORS REPORT
    # --------------------------------------------------------------------------
    elif report_type == "⚠️ كشف الديون والذمم المتبقية":
        import monthly_finance as F
        children=ui.df(conn,"""
            SELECT a.student_id,s.full_name,p.father_name,p.father_mobile
            FROM monthly_accounts a JOIN students s ON s.student_id=a.student_id
            JOIN parents p ON p.father_id=s.father_id
            WHERE a.status='regular' ORDER BY s.full_name
        """)
        debt_rows=[]
        for _,child in children.iterrows():
            account=F.projection(conn,child["student_id"])
            if account and account["due_now"]>0:
                debt_rows.append({
                    "اسم الطالب":child["full_name"],
                    "ولي الأمر":child["father_name"] or "",
                    "الهاتف":child["father_mobile"] or "",
                    "المدفوع فعلياً":sum(int(r["amount"]) for r in account["receipts"]
                                         if r["state"]=="active"),
                    "الباقي على الطالب":account["due_now"],
                    "موعد أول قسط غير مكتمل":account["next_unpaid"],
                })
        result=pd.DataFrame(debt_rows)
        report_title_str="كشف ديون الأطفال بالأوقية القديمة"
        meta_info={"التاريخ":str(F.today()),"العملة":F.CURRENCY}
        summary_metrics={
            "الباقي على الطلاب":f"{sum(row['الباقي على الطالب'] for row in debt_rows):,} {F.CURRENCY}",
            "الأطفال أصحاب المستحقات":str(len(debt_rows)),
        }

    # --------------------------------------------------------------------------
    # 6. TEACHER PAYMENTS REPORT
    # --------------------------------------------------------------------------
    elif report_type == "💼 سجل الرواتب والمستحقات":
        c1, c2 = st.columns(2)
        month_filter = c1.text_input("تصفية حسب شهر الراتب (مثال: 2026-10)", value="")
        
        teachers_df = ui.df(conn, "SELECT national_id, full_name FROM teachers ORDER BY full_name")
        teacher_options = {"الكل": "الكل"}
        if not teachers_df.empty:
            teacher_options.update(dict(zip(teachers_df['full_name'], teachers_df['national_id'])))
        selected_teacher_name = c2.selectbox("اختر المعلم/ة", list(teacher_options.keys()))

        query = """
            SELECT tp.payment_id AS "رقم القسيمة", t.full_name AS "اسم المعلم/ة",
                   tp.salary_month AS "شهر الراتب", tp.base_salary AS "الراتب الأساسي",
                   tp.bonus AS "المكافآت", tp.deductions AS "الخصومات", tp.amount AS "صافي الصرف",
                   tp.payment_date AS "تاريخ الصرف"
            FROM teacher_payments tp
            JOIN teachers t ON tp.national_id = t.national_id
            WHERE 1=1
        """
        params = []
        if month_filter.strip():
            query += " AND tp.salary_month = %s"
            params.append(month_filter.strip())
        if selected_teacher_name != "الكل":
            query += " AND tp.national_id = %s"
            params.append(teacher_options[selected_teacher_name])

        query += " ORDER BY tp.payment_date DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            total_salaries = result['صافي الصرف'].sum()
            meta_info = {"الشهر": month_filter or "الكل", "المعلم/ة": selected_teacher_name}
            report_title_str = "سجل رواتب المعلمين والمعلمات"
            summary_metrics = {
                "إجمالي الرواتب المصروفة": H.format_money(total_salaries),
                "عدد الحركات": f"{len(result)} حركة"
            }

    # --------------------------------------------------------------------------
    # 7. OPERATIONAL EXPENSES REPORT
    # --------------------------------------------------------------------------
    elif report_type == "💸 تقرير المصروفات التشغيلية":
        c1, c2, c3 = st.columns(3)
        date_from = c1.date_input("من تاريخ", value=None)
        date_to = c2.date_input("إلى تاريخ", value=None)
        status_filter = c3.selectbox("حالة الدفع", ["الكل", "مدفوع بالكامل", "متبقي جزء", "غير مدفوع"])

        query = """
            SELECT expense_id AS "رقم المصروف", expense_date AS "التاريخ",
                   category AS "التصنيف", amount AS "المبلغ الكلي",
                   amount_paid AS "المبلغ المدفوع", payment_status AS "حالة الدفع",
                   payee AS "الجهة المستفيدة", notes AS "ملاحظات"
            FROM expenses
            WHERE 1=1
        """
        params = []
        if date_from:
            query += " AND expense_date >= %s"
            params.append(str(date_from))
        if date_to:
            query += " AND expense_date <= %s"
            params.append(str(date_to))
        if status_filter != "الكل":
            query += " AND payment_status = %s"
            params.append(status_filter)

        query += " ORDER BY expense_date DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            total_exp = result['المبلغ الكلي'].sum()
            total_paid_exp = result['المبلغ المدفوع'].sum()
            meta_info = {"الفترة": f"{date_from or 'البداية'} إلى {date_to or 'النهاية'}", "الحالة": status_filter}
            report_title_str = "تقرير المصروفات التشغيلية"
            summary_metrics = {
                "إجمالي المصروفات": H.format_money(total_exp),
                "إجمالي المدفوع فعلياً": H.format_money(total_paid_exp)
            }

    # --------------------------------------------------------------------------
    # 8. ASSETS & EQUIPMENT REPORT
    # --------------------------------------------------------------------------
    else:  # "🏛️ تقرير الأصول والموجودات الثابتة"
        c1, c2 = st.columns(2)
        condition_filter = c1.selectbox("حالة الأصل", ["الكل", "ممتازة", "جيدة", "تحتاج صيانة", "تالفة"])
        category_input = c2.text_input("تصفية حسب التصنيف", value="")

        query = """
            SELECT asset_id AS "رقم الأصل", item_name AS "اسم الصنف",
                   category AS "التصنيف", quantity AS "الكمية",
                   unit_cost AS "سعر الوحدة", total_cost AS "التكلفة الكلية",
                   condition_status AS "الحالة", purchase_date AS "تاريخ الشراء"
            FROM assets
            WHERE 1=1
        """
        params = []
        if condition_filter != "الكل":
            query += " AND condition_status = %s"
            params.append(condition_filter)
        if category_input.strip():
            query += " AND category ILIKE %s"
            params.append(f"%{category_input.strip()}%")

        query += " ORDER BY purchase_date DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            total_assets_cost = result['التكلفة الكلية'].sum()
            total_items_count = result['الكمية'].sum()
            meta_info = {"الحالة": condition_filter, "التصنيف": category_input or "الكل"}
            report_title_str = "تقرير الأصول والموجودات الثابتة"
            summary_metrics = {
                "إجمالي قيمة الأصول": H.format_money(total_assets_cost),
                "إجمالي عدد القطع": f"{total_items_count} قطعة"
            }

    # --------------------------------------------------------------------------
    # ATTRIBUTE SELECTION & EXPORT CONTROLS (For tabular reports)
    # --------------------------------------------------------------------------
    if not result.empty:
        st.markdown("---")
        st.subheader("⚙️ تخصيص الأعمدة المعروضة")
        
        all_columns = list(result.columns)
        selected_columns = st.multiselect(
            "اختر الحقول/العمود المراد إظهارها في التقرير والطباعة:",
            options=all_columns,
            default=all_columns
        )

        if selected_columns:
            display_df = result[selected_columns]
        else:
            display_df = result

        st.markdown("---")
        st.subheader("👀 معاينة التقرير والملخصات")
        
        if summary_metrics:
            cols = st.columns(len(summary_metrics))
            for i, (k, v) in enumerate(summary_metrics.items()):
                cols[i].metric(label=k, value=v)
            st.markdown("")

        ui.dataframe(display_df, use_container_width=True, hide_index=True)

        st.markdown("##### 📥 خيارات الطباعة والتصدير")
        c1, c2 = st.columns(2)
        
        with c1:
            st.download_button(
                "📊 تحميل التقرير كملف Excel",
                data=_to_excel(display_df),
                file_name=f"report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        with c2:
            if st.button("🖨️ معاينة و طباعة التقرير ( PDF)", use_container_width=True):
                st.session_state['show_report_print_preview'] = True

        if st.session_state.get('show_report_print_preview', False):
            st.markdown("---")
            st.markdown("#### معاينة الطباعة الرسمية :")
            _render_printable_report_pdf(report_title_str, meta_info, display_df, summary_metrics)
    elif report_type != "📑 تقرير الأداء العام  ":
        ui.empty_state("لا توجد بيانات مطابقة للفلاتر المحددة.")
