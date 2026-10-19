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
from datetime import datetime
from html import escape

import ui
import helpers as H


def _to_excel(df: pd.DataFrame, *, sheet_name='التقرير') -> bytes:
    """Helper to convert DataFrame to Excel binary stream."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        # Reports contain values, never executable workbook formulas. Protect
        # headers and every text cell while retaining numbers/dates as typed.
        for row in writer.sheets[sheet_name].iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    return output.getvalue()


def _render_printable_report_pdf(
    report_title: str,
    meta_info: dict,
    df: pd.DataFrame,
    summary_metrics: dict,
):
    """Renders a print-ready iframe with a landscape PDF layout, letterhead, and summary footer."""
    
    headers_html = "".join([f"<th>{escape(str(col))}</th>" for col in df.columns])
    
    rows_html = ""
    for _, row in df.iterrows():
        cells = "".join([f"<td>{escape(str(val)) if pd.notna(val) else ''}</td>" for val in row])
        rows_html += f"<tr>{cells}</tr>"

    logo_img_tag = ui.logo_html()

    meta_html = "".join([f"<div><strong>{escape(str(k))}:</strong> {escape(str(v))}</div>" for k, v in meta_info.items()])

    summary_html = ""
    if summary_metrics:
        summary_items = "".join([f'<div class="summary-card"><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></div>' for k, v in summary_metrics.items()])
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
            {escape(str(report_title))} ({len(df)} سجل)
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


def _teacher_labels(teachers):
    labels = {}
    for row in teachers.to_dict('records'):
        label = f"{row['full_name']} — {row['display_national_id']}"
        if pd.notna(row['archived_at']):
            label += " (مؤرشفة)"
        labels[row['national_id']] = label
    # Displayed identities may be reused after archival. Disambiguate those
    # historical rows too, while the SQL filter always uses the stable key.
    from collections import Counter
    repeated = Counter(labels.values())
    return {ident: label if repeated[label]==1 else f"{label} · مرجع {ident}"
            for ident,label in labels.items()}


def _current_students(conn, department=-1, gender="الكل"):
    query = """SELECT s.student_id AS "رقم الطالب",s.full_name AS "اسم الطالب",
        COALESCE(d.name,'بدون قسم') AS "القسم",s.gender AS "الجنس",s.birth_date AS "تاريخ الميلاد",
        p.father_name AS "اسم الأب",p.father_mobile AS "جوال الأب",
        p.mother_name AS "اسم الأم",p.mother_mobile AS "جوال الأم",s.address AS "العنوان"
        FROM students s LEFT JOIN parents p ON p.father_id=s.father_id
        LEFT JOIN student_departments m ON m.student_id=s.student_id
        LEFT JOIN school_departments d ON d.department_id=m.department_id AND d.archived_at IS NULL
        WHERE s.archived_at IS NULL"""
    params = []
    if department == 0:
        query += " AND d.department_id IS NULL"
    elif department != -1:
        query += " AND d.department_id=%s"
        params.append(department)
    if gender != "الكل":
        query += " AND s.gender=%s"
        params.append(gender)
    result = ui.df(conn, query+" ORDER BY s.full_name,s.student_id", tuple(params))
    if result.empty:
        return pd.DataFrame(columns=["رقم الطالب","اسم الطالب","القسم","الجنس","تاريخ الميلاد",
            "اسم الأب","جوال الأب","اسم الأم","جوال الأم","العنوان"])
    return result


def _current_debts(conn):
    import monthly_finance as F
    day = F.today()
    # Materialize once for the entire report; then read without per-child connections.
    F._ensure_all_started(day)
    children = ui.df(conn,"""SELECT a.student_id,s.full_name,s.archived_at,a.status,
        p.father_name,p.mother_name,p.father_mobile,p.mother_mobile
        FROM monthly_accounts a JOIN students s ON s.student_id=a.student_id
        LEFT JOIN parents p ON p.father_id=s.father_id ORDER BY s.full_name,s.student_id""")
    rows = []
    contacts=['father_name','father_mobile','mother_name','mother_mobile']
    children=children.fillna({name:'' for name in contacts})
    for child in children.to_dict('records'):
        account = F.projection(conn,child['student_id'],day,materialize=False)
        if not account or account['due_now'] <= 0:
            continue
        rows.append({"اسم الطالب":child['full_name'],
            "حالة الملف":"مؤرشف" if pd.notna(child['archived_at']) else "نشط",
            "الرسوم":"معفي" if child['status']=='exempt' else "دفع",
            "اسم الأب":child['father_name'] or "", "جوال الأب":child['father_mobile'] or "",
            "اسم الأم":child['mother_name'] or "", "جوال الأم":child['mother_mobile'] or "",
            "المدفوع فعلياً":account['cash_paid'],"الباقي على الطالب":account['due_now'],
            "موعد القسط التالي":account['next_due'] if child['status']=='regular' and pd.isna(child['archived_at']) else None})
    return rows


def render(conn):
    ui.section_header("📈", "التقارير والتصدير", "استخراج بيانات مفلترة وتصديرها وإدارتها")

    names = {
        "📑 تقرير الإدارة العليا الشامل (التحليلي والمالي)": "الحركة المالية خلال فترة",
        "💵 سجل المقبوضات المالية": "الوصولات والدفعات",
        "👨‍👩‍👧‍👦 قائمة الطلاب وأولياء الأمور": "الطلاب وأولياء الأمور",
        "🏷️ كشف الحضور حسب القسم": "كشف الحضور حسب القسم",
        "⚠️ كشف الديون والذمم المتبقية": "المتبقي على الطلاب",
        "💼 سجل الرواتب والمستحقات": "الرواتب المصروفة",
        "💸 تقرير المصروفات التشغيلية": "فواتير المصروفات والمتبقي منها",
        "🏛️ تقرير الأصول والموجودات الثابتة": "جرد التجهيزات",
    }
    if st.checkbox("عرض تقارير الصفوف والسنوات السابقة", key="reports_legacy"):
        names.update({"🏫 كشف الطلاب حسب الصف (للحضور والغياب)": "كشف الصفوف السابق",
                      "📋 قائمة التسجيلات": "التسجيلات في النظام السابق"})
    report_type = st.selectbox("اختر التقرير", list(names), format_func=names.get, key="report_type")
    st.markdown("##### " + names[report_type])
    st.markdown("---")

    result = pd.DataFrame()
    meta_info = {}
    report_title_str = ""
    summary_metrics = {}

    # Academic setup is read only for explicitly requested historical reports.
    if report_type in ("🏫 كشف الطلاب حسب الصف (للحضور والغياب)", "📋 قائمة التسجيلات"):
        years_df = ui.df(conn, "SELECT year_id,COALESCE(display_year_id,year_id) AS display_year_id FROM academic_years ORDER BY year_id DESC")
        year_list = years_df.year_id.tolist() if not years_df.empty else []
        year_labels = dict(zip(years_df.year_id,years_df.display_year_id)) if not years_df.empty else {}
        classes_df = ui.df(conn, "SELECT class_id,(class_type || ' ' || section) AS class_name FROM classes ORDER BY class_type,section")
        st.caption("هذا تقرير لسجلات النظام السابق. لتوزيع الأطفال الحالي استخدم الأقسام.")

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
            {"البند":"المصروفات المسجلة والمدفوعة","المبلغ":money(summary["operational_cash"])},
            {"البند":"الرواتب المصروفة","المبلغ":money(summary["salary_cash"])},
            {"البند":"السلف المصروفة","المبلغ":money(summary["advance_cash"])},
        ])
        ui.dataframe(details,use_container_width=True,hide_index=True)
        st.caption("المتبقي على الطلاب محسوب حتى نهاية الفترة، ومنفصل عن النقد المتبقي. الدفعات المقدمة ضمن المقبوضات مرة واحدة.")
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
        if not year_list:
            ui.empty_state("لا توجد سنوات دراسية في السجلات السابقة.")
            return
        if classes_df.empty:
            ui.empty_state("لا توجد صفوف معرفة في النظام.")
            return

        c1, c2, c3 = st.columns(3)
        class_options = dict(zip(classes_df['class_name'], classes_df['class_id']))
        selected_class_name = c1.selectbox("اختر الصف *", list(class_options.keys()))
        selected_class_id = class_options[selected_class_name]

        selected_year = c2.selectbox("السنة الدراسية", year_list,format_func=lambda x:year_labels.get(x,x))
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
            WHERE r.class_id = %s AND r.year_id = %s AND r.archived_at IS NULL AND s.archived_at IS NULL
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
    elif report_type in ("👨‍👩‍👧‍👦 قائمة الطلاب وأولياء الأمور", "🏷️ كشف الحضور حسب القسم"):
        departments = ui.df(conn, "SELECT department_id,name FROM school_departments WHERE archived_at IS NULL ORDER BY name")
        labels = dict(zip(departments.department_id,departments.name)) if not departments.empty else {}
        selected = st.selectbox("القسم الحالي", [-1,0]+list(labels),
            format_func=lambda x: "كل الأطفال" if x==-1 else "بدون قسم" if x==0 else labels[x], key="report_department")
        gender = st.selectbox("الجنس", ["الكل", "ذكر", "أنثى"], key="report_gender")
        result = _current_students(conn, selected, gender)
        attendance = report_type == "🏷️ كشف الحضور حسب القسم"
        if attendance:
            result = result[["اسم الطالب", "القسم", "جوال الأب", "جوال الأم"]].copy()
            for day in ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "ملاحظات"]:
                result[day] = ""
        if not result.empty:
            result.insert(0,"م",range(1,len(result)+1))
        report_title_str = "كشف الحضور حسب القسم" if attendance else "الطلاب وأولياء الأمور"
        meta_info = {"القسم": "كل الأطفال" if selected==-1 else "بدون قسم" if selected==0 else labels[selected], "الجنس":gender}
        summary_metrics = {"عدد الطلاب": str(len(result))}

    # --------------------------------------------------------------------------
    # 4. REGISTRATION LIST
    # --------------------------------------------------------------------------
    elif report_type == "📋 قائمة التسجيلات":
        c1, c2, c3 = st.columns(3)
        year_filter = c1.selectbox("السنة الدراسية", ["الكل"] + year_list,format_func=lambda x:year_labels.get(x,x))
        class_filter_options = ["الكل"] + list(classes_df['class_name']) if not classes_df.empty else ["الكل"]
        selected_class_filter = c2.selectbox("الصف", class_filter_options)
        status_filter = c3.selectbox("حالة التسجيل", ["الكل", "مسجل", "انسحب", "مؤجل"])

        query = """
            SELECT s.full_name AS "اسم الطالب", (c.class_type || ' ' || c.section) AS "الصف",
                   COALESCE(y.display_year_id,r.year_id) AS "السنة الدراسية", r.status AS "الحالة", r.registration_date AS "تاريخ التسجيل"
            FROM registrations r
            JOIN students s ON r.student_id = s.student_id
            JOIN classes c ON c.class_id = r.class_id
            LEFT JOIN academic_years y ON y.year_id=r.year_id
            WHERE r.archived_at IS NULL AND s.archived_at IS NULL
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
        debt_rows = _current_debts(conn)
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
        st.caption("حالة المستند مستقلة عن النقد: إلغاء مستند الراتب وحده لا يعني استرداد المبلغ المصروف.")
        c1, c2 = st.columns(2)
        month_filter = c1.text_input("تصفية حسب شهر الراتب (مثال: 2026-10)", value="")
        
        teachers_df = ui.df(conn, """SELECT national_id,COALESCE(display_national_id,national_id) AS display_national_id,
            full_name,archived_at FROM teachers ORDER BY full_name,national_id""")
        teacher_labels = _teacher_labels(teachers_df)
        selected_teacher = c2.selectbox("اختر المعلم/ة", [None]+list(teacher_labels),
            format_func=lambda ident: "الكل" if ident is None else teacher_labels[ident],
            key="salary_report_teacher")

        query = """
            SELECT tp.payment_id AS "رقم القسيمة", t.full_name AS "اسم المعلم/ة",
                   COALESCE(t.display_national_id,t.national_id) AS "هوية المعلم/ة",
                   tp.salary_month AS "شهر الراتب", tp.base_salary AS "الراتب الأساسي",
                   tp.bonus AS "المكافآت", tp.deductions AS "الخصومات", tp.amount AS "قيمة المستند",
                   COALESCE(tp.cash_amount,tp.amount) AS "النقد المصروف",
                   CASE tp.record_state WHEN 'active' THEN 'ساري' ELSE 'ملغى' END AS "حالة المستند",
                   tp.payment_date AS "تاريخ الصرف"
            FROM teacher_payments tp
            JOIN teachers t ON tp.national_id = t.national_id
            WHERE 1=1
        """
        params = []
        if month_filter.strip():
            query += " AND tp.salary_month = %s"
            params.append(month_filter.strip())
        if selected_teacher is not None:
            query += " AND tp.national_id = %s"
            params.append(selected_teacher)

        query += " ORDER BY tp.payment_date DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            total_salaries = result['النقد المصروف'].sum()
            meta_info = {"الشهر": month_filter or "الكل", "المعلم/ة": teacher_labels.get(selected_teacher,"الكل")}
            report_title_str = "سجل رواتب المعلمين والمعلمات"
            summary_metrics = {
                "إجمالي الرواتب المصروفة": H.format_money(total_salaries),
                "عدد الحركات": f"{len(result)} حركة"
            }

    # --------------------------------------------------------------------------
    # 7. OPERATIONAL EXPENSES REPORT
    # --------------------------------------------------------------------------
    elif report_type == "💸 تقرير المصروفات التشغيلية":
        st.caption("هذه فواتير حسب تاريخ تسجيل المصروف، والمدفوع هو مجموع تسديد كل فاتورة. لمعرفة النقد المصروف خلال فترة استخدم تقرير الحركة المالية.")
        c1, c2, c3 = st.columns(3)
        date_from = c1.date_input("من تاريخ", value=None)
        date_to = c2.date_input("إلى تاريخ", value=None)
        status_filter = c3.selectbox("حالة الدفع", ["الكل", "مدفوع بالكامل", "مدفوع جزئياً", "غير مدفوع"])

        query = """
            SELECT expense_id AS "رقم المصروف", expense_date AS "التاريخ",
                   category AS "اسم المصروف", amount AS "المبلغ الكلي",
                   amount_paid AS "المبلغ المدفوع", payment_status AS "حالة الدفع",
                   payee AS "الجهة المستفيدة", notes AS "ملاحظات"
            FROM expenses
            WHERE cancelled_at IS NULL AND teacher_payment_id IS NULL AND teacher_advance_id IS NULL
        """
        params = []
        if date_from:
            query += " AND expense_date >= %s"
            params.append(str(date_from))
        if date_to:
            query += " AND expense_date <= %s"
            params.append(str(date_to))
        if status_filter != "الكل":
            query += {"مدفوع بالكامل":" AND amount_paid=amount",
                      "مدفوع جزئياً":" AND amount_paid>0 AND amount_paid<amount",
                      "غير مدفوع":" AND amount_paid=0"}[status_filter]

        query += " ORDER BY expense_date DESC"
        result = ui.df(conn, query, tuple(params))

        if not result.empty:
            result.insert(0, "م", range(1, len(result) + 1))
            total_exp = result['المبلغ الكلي'].sum()
            total_paid_exp = result['المبلغ المدفوع'].sum()
            meta_info = {"الفترة": f"{date_from or 'البداية'} إلى {date_to or 'النهاية'}", "الحالة": status_filter}
            report_title_str = "تقرير المصروفات التشغيلية"
            summary_metrics = {
                "قيمة الفواتير": H.format_money(total_exp),
                "إجمالي المدفوع فعلياً": H.format_money(total_paid_exp)
            }

    # --------------------------------------------------------------------------
    # 8. ASSETS & EQUIPMENT REPORT
    # --------------------------------------------------------------------------
    else:  # "🏛️ تقرير الأصول والموجودات الثابتة"
        c1, c2 = st.columns(2)
        st.caption("قيمة الجرد ليست مصروفًا نقديًا؛ يظهر الصرف الفعلي في سجل المصروفات.")
        condition_filter = c1.selectbox("حالة الأصل", ["الكل", "ممتازة", "جيدة", "تحتاج صيانة", "تالفة/مستهلكة"])
        category_input = c2.text_input("تصفية حسب التصنيف", value="")

        query = """
            SELECT asset_id AS "رقم الأصل", item_name AS "اسم الصنف",
                   category AS "التصنيف", quantity AS "الكمية",
                   unit_cost AS "سعر الوحدة", total_cost AS "التكلفة الكلية",
                   condition_status AS "الحالة", purchase_date AS "تاريخ الشراء"
            FROM assets
            WHERE archived_at IS NULL
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
                st.session_state['show_report_print_preview'] = report_type

        if st.session_state.get('show_report_print_preview') == report_type:
            st.markdown("---")
            st.markdown("#### معاينة الطباعة الرسمية :")
            _render_printable_report_pdf(report_title_str, meta_info, display_df, summary_metrics)
    else:
        ui.empty_state("لا توجد بيانات مطابقة للفلاتر المحددة.")
