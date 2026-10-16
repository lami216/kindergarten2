"""
pages_expenses.py — Operational Expenses & Capital Assets Management (PostgreSQL/Supabase).
Supports full Paid/Debt status calculations, edit/delete actions, and asset scrapping.
"""

import streamlit as st
from datetime import datetime, date
import ui
import expense_finance as E
from monthly_finance import today as business_today
import uuid

EXPENSE_CATEGORIES = [
    "قرطاسية ومطبوعات",
    "ضيافة وتنظيف",
    "صيانة وإصلاحات",
    "كهرباء ومياه واشتراكات",
    "فعاليات وأنشطة",
    "مصروفات أخرى"
]

ASSET_CATEGORIES = [
    "ألعاب وتجهيزات أطفال",
    "أثاث ومفروشات",
    "أجهزة إلكترونية وتقنية",
    "معدات تحسين الروضة"
]

ASSET_CONDITIONS = ["ممتازة", "جيدة", "تحتاج صيانة", "تالفة/مستهلكة"]
PAYMENT_STATUSES = ["مدفوع بالكامل", "آجل / دين (غير مدفوع)", "مدفوع جزئياً"]


def render(conn):
    ui.section_header("📦", "المصروفات والأصول", "إدارة المصروفات التشغيلية والديون وجرد حالة الأصول")

    with st.expander("عن الرواتب والسلف"):
        st.caption("سجّل الرواتب والسلف من صفحة الرواتب؛ تظهر تلقائيًا في الملخص المالي.")
    main_tab1, main_tab2 = st.tabs(["💰 المصروفات والديون التشغيلية", "🧸 الأصول والتجهيزات"])

    # ==================================================================
    # MAIN TAB 1: OPERATIONAL EXPENSES & DEBT MANAGEMENT
    # ==================================================================
    with main_tab1:
        sub_tab1, sub_tab2 = st.tabs(["📋 السجل والتسجيل", "⚙️ إدارة المصروفات والديون"])

        # --------------------------------------------------------------
        # SUB TAB 1: View Log & Add Expense
        # --------------------------------------------------------------
        with sub_tab1:
            col_form, col_list = st.columns([1, 1.4])

            with col_form:
                # --------------------------------------------------------------
                # داخل نموذج إضافة مصروف جديد (Add Expense Form)
                # --------------------------------------------------------------
                st.markdown("##### ➕ تسجيل مصروف جديد")
                notice=st.session_state.pop("expense_add_notice", None)
                if notice:
                    st.success(notice)
                version=st.session_state.get("expense_add_version", 0)
                with st.container(border=True, key=f"expense_intake_{version}"):
                    exp_date = st.date_input("تاريخ المصروف", key=f"expense_add_date_{version}", value=business_today())
                    category = st.text_input("اسم المصروف *", placeholder="مثال: شراء دفاتر للأطفال", max_chars=100, key=f"expense_add_category_{version}").strip()
                    amount = st.number_input("إجمالي قيمة الفاتورة/المصروف (أوقية قديمة)", key=f"expense_add_amount_{version}", min_value=0.0, step=10.0, format="%.2f")

                    pay_status = st.selectbox("حالة الدفع", PAYMENT_STATUSES, key=f"expense_add_status_{version}")

                    # تحكم ديناميكي بالمبلغ المدفوع بناءً على الحالة
                    if pay_status == "مدفوع بالكامل":
                        amount_paid = amount
                    elif pay_status == "آجل / دين (غير مدفوع)":
                        amount_paid = 0.0
                    else:  # مدفوع جزئياً
                        paid_key=f"expense_add_paid_{version}"
                        amount_paid = st.number_input(
                            "المبلغ المدفوع فعلياً (أوقية قديمة)",
                            key=f"expense_add_paid_{version}",
                            min_value=0.0,
                            value=0.0,
                            step=10.0,
                            format="%.2f"
                        )

                    payee = st.text_input("المستلم / المورد (اختياري)", key=f"expense_add_payee_{version}")
                    method = st.selectbox("طريقة الدفع", ["كاش", "تحويل بنكي", "شيك"], key=f"expense_add_method_{version}")
                    with st.expander("ملاحظات أو رقم فاتورة (اختياري)"):
                        notes = st.text_area("ملاحظات / رقم الفاتورة", key=f"expense_add_notes_{version}", height=70)

                    if st.button("حفظ المصروف", key=f"expense_add_save_{version}", type="primary", use_container_width=True):
                        if not category:
                            st.error("أدخل اسم المصروف.")
                        elif amount <= 0:
                            st.error("⚠️ يرجى إدخال مبلغ أكبر من صفر.")
                        elif pay_status == 'مدفوع جزئياً' and amount_paid>amount:
                            st.error('المدفوع أكبر من قيمة الفاتورة؛ صحّح الإجمالي أو المدفوع.')
                        else:
                            # ضمان حتمي لتطابق القيمة قبل الحفظ في قاعدة البيانات
                            final_paid = amount if pay_status == "مدفوع بالكامل" else (0.0 if pay_status == "آجل / دين (غير مدفوع)" else amount_paid)

                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO expenses (expense_date, category, amount, amount_paid, payment_status, payment_method, payee, notes)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """, (exp_date, category, amount, final_paid, pay_status, method, payee, notes))
                            st.session_state["expense_add_version"]=version+1
                            st.session_state["expense_add_notice"]="تم تسجيل المصروف بنجاح."
                            st.rerun()

            with col_list:
                st.markdown("##### 📋 سجل المصروفات والالتزامات")
                df_exp = ui.df(conn, """
                    SELECT
                        expense_id AS "الرقم",
                        expense_date AS "التاريخ",
                        category AS "اسم المصروف",
                        amount AS "الإجمالي",
                        amount_paid AS "المدفوع",
                        (amount - amount_paid) AS "المتبقي (دين)",
                        payment_status AS "حالة الدفع",
                        payee AS "المورد",
                        notes AS "ملاحظات"
                    FROM expenses WHERE cancelled_at IS NULL
                    ORDER BY expense_date DESC
                """)
                if df_exp.empty:
                    ui.empty_state("لا توجد مصروفات مسجلة حتى الآن.")
                else:
                    ui.dataframe(df_exp, use_container_width=True, hide_index=True)

        # --------------------------------------------------------------
        # SUB TAB 2: Edit & Settle Debts
        # --------------------------------------------------------------
        with sub_tab2:
            df_exp_manage = ui.df(conn, "SELECT * FROM expenses WHERE cancelled_at IS NULL ORDER BY expense_date DESC")
            if df_exp_manage.empty:
                ui.empty_state("لا توجد مصروفات للتعديل أو الحذف.")
            else:
                exp_options = {
                    row["expense_id"]: f"#{row['expense_id']} - {row['category']} (المتبقي: {float(row['amount']) - float(row['amount_paid'])} أوقية قديمة) - {row['payment_status']}"
                    for _, row in df_exp_manage.iterrows()
                }
                selected_id = st.selectbox("اختر المصروف لتعديله، تسديد الدين، أو الحذف:", options=list(exp_options.keys()), format_func=lambda x: exp_options[x],key='expense_manage_select')

                exp_data = df_exp_manage[df_exp_manage["expense_id"] == selected_id].iloc[0]
                ui.open_record_editor('expenses',int(selected_id),'تعديل كامل للمصروف وتسوياته')
                remaining_debt = float(exp_data["amount"]) - float(exp_data["amount_paid"])

                col_edit, col_del = st.columns([2, 1])
                with col_edit:
                    st.markdown("##### ✏️ تعديل البيانات وحالة السداد")
                    with st.form(f"edit_exp_{selected_id}"):
                        try:
                            curr_date = datetime.strptime(str(exp_data["expense_date"]), "%Y-%m-%d").date()
                        except Exception:
                            curr_date = business_today()

                        e_date = st.date_input("التاريخ", value=curr_date)
                        e_cat = st.text_input("اسم المصروف *", value=exp_data["category"] or "", max_chars=100).strip()
                        e_amt = st.number_input("إجمالي الفاتورة", value=float(exp_data["amount"]), step=10.0, format="%.2f")

                        curr_status_idx = PAYMENT_STATUSES.index(exp_data["payment_status"]) if exp_data["payment_status"] in PAYMENT_STATUSES else 0
                        e_status = st.selectbox("حالة الدفع", PAYMENT_STATUSES, index=curr_status_idx)

                        # Keep recorded cash editable even when the total is
                        # temporarily lower; validate the relation on submission.
                        e_paid = st.number_input("المبلغ المدفوع فعلياً", value=float(exp_data["amount_paid"]), min_value=0.0, step=10.0, format="%.2f")

                        e_payee = st.text_input("المورد", value=exp_data["payee"] or "")
                        e_notes = st.text_area("ملاحظات", value=exp_data["notes"] or "", height=70)

                        st.caption("هذا تصحيح لقيد محفوظ، وليس تسوية أو استرداد نقد جديد.")
                        correction_reason=st.text_input("سبب تصحيح القيد *")
                        if st.form_submit_button("حفظ تصحيح القيد", type="primary", use_container_width=True):
                            try:
                                key=f"expense_correct_token_{selected_id}"
                                st.session_state.setdefault(key,str(uuid.uuid4()))
                                E.correct(selected_id,amount_total=e_amt,amount_paid=e_paid,
                                    category=e_cat,expense_date=e_date,payee=e_payee,
                                    notes=e_notes,reason=correction_reason,
                                    actor=st.session_state.get("auth_user","مديرة الروضة"),
                                    token=st.session_state[key])
                                st.session_state[key]=str(uuid.uuid4())
                                st.success("حُفظ التصحيح وسجل التدقيق دون اختلاق حركة نقدية اليوم.")
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))
                            except Exception:
                                st.error("تعذّر تصحيح المصروف؛ لم تتغير الأدلة.")

                with col_del:
                    st.markdown("##### 🚨 إجراءات الديون والحذف")
                    with st.container(border=True):
                        if remaining_debt > 0:
                            st.info(f"💡 المتبقي كدين لهذا المصروف: **{remaining_debt:,.2f} أوقية قديمة**")
                            with st.form(f"settle_expense_{selected_id}"):
                                pay=st.number_input("مبلغ نقد صُرف فعلياً الآن",
                                    min_value=0.0,max_value=float(remaining_debt),
                                    value=0.0,step=10.0,format="%.2f")
                                payment_date=st.date_input("تاريخ صرف النقد",value=business_today())
                                settle_reason=st.text_input("سبب تسوية الدفع *")
                                settle=st.form_submit_button("تسجيل تسوية نقدية فعلية")
                            if settle:
                                try:
                                    key=f"expense_settle_token_{selected_id}"
                                    st.session_state.setdefault(key,str(uuid.uuid4()))
                                    E.settle(selected_id,pay,on_date=payment_date,
                                        actor=st.session_state.get("auth_user","مديرة الروضة"),
                                        reason=settle_reason,token=st.session_state[key])
                                    st.session_state[key]=str(uuid.uuid4())
                                    st.success("سُجل صرف النقد بتاريخ الدفع الفعلي، لا بتاريخ الفاتورة.")
                                    st.rerun()
                                except ValueError as error:
                                    st.error(str(error))
                                except Exception:
                                    st.error("تعذّر حفظ التسوية؛ بقي الحساب كما هو.")
                            st.write("---")

                        reason=st.text_input("سبب إلغاء المصروف *",key=f"expense_cancel_reason_{selected_id}")
                        agree=st.checkbox("أؤكد إلغاء إدخال المصروف الخاطئ وإزالة أثره من الحسابات",key=f"expense_cancel_agree_{selected_id}")
                        if st.button("إلغاء المصروف",disabled=not agree,key=f"del_exp_{selected_id}"):
                            try:
                                E.cancel(selected_id,actor=st.session_state.get("auth_user"),reason=reason)
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))
                            except Exception:
                                st.error("تعذر الإلغاء؛ بقي الحساب كما هو.")

    # ==================================================================
    # MAIN TAB 2: CAPITAL ASSETS & TOYS
    # ==================================================================
    with main_tab2:
        sub_ast1, sub_ast2 = st.tabs(["🧸 جرد الأصول والإضافة", "⚙️ إدارة وتعديل الأصول والفرق"])

        # --------------------------------------------------------------
        # SUB TAB 1: View Assets & Add New
        # --------------------------------------------------------------
        with sub_ast1:
            col_ast_list, col_ast_form = st.columns([1.8, 1])

            with col_ast_form:
                st.markdown("##### ➕ إضافة أصل / ألعاب جديدة")
                with st.form("add_asset_form", clear_on_submit=True):
                    p_date = st.date_input("تاريخ الشراء", value=business_today())
                    item_name = st.text_input("اسم الأصل / اللعبة", placeholder="مثال: مجمع ألعاب بلاستيكي")
                    category = st.selectbox("فئة الأصل", ASSET_CATEGORIES)
                    qty = st.number_input("الكمية", min_value=1, value=1, step=1)
                    unit_cost = st.number_input("سعر القطعة (أوقية قديمة)", min_value=0.0, step=10.0, format="%.2f")
                    status = st.selectbox("الحالة", ASSET_CONDITIONS)
                    notes = st.text_area("ملاحظات / المورد", height=70)

                    if st.form_submit_button("تسجيل الأصل", type="primary", use_container_width=True):
                        if not item_name.strip() or unit_cost <= 0:
                            st.error("⚠️ يرجى التأكد من إدخال اسم الأصل والتكلفة.")
                        else:
                            total_cost = qty * unit_cost
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO assets (purchase_date, item_name, category, quantity, unit_cost, total_cost, condition_status, notes)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """, (p_date, item_name, category, qty, unit_cost, total_cost, status, notes))
                            st.success("✅ تم تسجيل الأصل بنجاح!")
                            st.rerun()

            with col_ast_list:
                st.markdown("##### 🧸 جدول جرد الأصول والألعاب")
                df_ast = ui.df(conn, """
                    SELECT
                        asset_id AS "الرقم",
                        purchase_date AS "تاريخ الشراء",
                        item_name AS "الاسم",
                        category AS "الفئة",
                        quantity AS "الكمية",
                        unit_cost AS "سعر القطعة",
                        total_cost AS "الإجمالي",
                        condition_status AS "الحالة"
                    FROM assets WHERE archived_at IS NULL
                    ORDER BY purchase_date DESC
                """)
                if df_ast.empty:
                    ui.empty_state("لا توجد أصول أو ألعاب مسجلة حتى الآن.")
                else:
                    ui.dataframe(df_ast, use_container_width=True, hide_index=True)

        # --------------------------------------------------------------
        # SUB TAB 2: Edit & Scrap Asset
        # --------------------------------------------------------------
        with sub_ast2:
            df_ast_manage = ui.df(conn, "SELECT * FROM assets WHERE archived_at IS NULL ORDER BY purchase_date DESC")
            if df_ast_manage.empty:
                ui.empty_state("لا توجد أصول لإدارتها.")
            else:
                ast_options = {row["asset_id"]: f"#{row['asset_id']} - {row['item_name']} ({row['condition_status']})" for _, row in df_ast_manage.iterrows()}
                selected_ast_id = st.selectbox("اختر الأصل/اللعبة لإدارة الحالة أو التعديل:", options=list(ast_options.keys()), format_func=lambda x: ast_options[x])

                ast_data = df_ast_manage[df_ast_manage["asset_id"] == selected_ast_id].iloc[0]

                ui.open_record_editor('assets',int(selected_ast_id),'تعديل بيانات الأصل / تغيير حالته / حذفه')
