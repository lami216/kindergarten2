"""
sections/salaries.py — قسم رواتب المعلمات
"""

import streamlit as st
import ui
import helpers as H
import teacher_receipt
import payroll_finance as P
from monthly_finance import today as business_today
import uuid
from datetime import datetime


def render(conn):
    ui.section_header("💸", "رواتب المعلمات", "إدارة صرف وتعديل وإعادة طباعة قسائم الرواتب الشهرية")

    teachers_df = ui.df(conn, "SELECT national_id,COALESCE(display_national_id,national_id) AS display_national_id, full_name, salary FROM teachers WHERE archived_at IS NULL ORDER BY full_name")
    
    if teachers_df.empty:
        st.info("لا توجد معلمات نشطات للصرف؛ السجلات السابقة ما زالت متاحة.")

    tab_pay, tab_log, tab_advance = st.tabs([
        "➕ صرف راتب شهري", "📋 سجل الرواتب والإعادة", "💰 سلف المعلمات"])

    teacher_map = {f"{r.full_name} ({r.display_national_id})": (r.national_id, float(r.salary), r.full_name) for r in teachers_df.itertuples()}

    # -------------------------------------------------- TAB 1: DISBURSE SALARY --
    with tab_pay:
        st.markdown("##### 📝 تسجيل دفعة راتب جديدة")
        
        selected_teacher_label = st.selectbox("اختر المعلمة *", list(teacher_map.keys()), index=None, key="salary_teacher")
        t_id, default_salary, t_name = teacher_map.get(selected_teacher_label, (None, 0.0, ""))

        current_month = business_today().strftime("%Y-%m")

        st.session_state.setdefault("salary_request_token", str(uuid.uuid4()))
        salary_version = st.session_state.get("salary_form_version", 0)
        success = st.session_state.pop("salary_saved_notice", None)
        if success:
            st.success(success)
        quote_key=f'salary_displayed_quote_v{salary_version}'
        previous_quote=st.session_state.get(quote_key)
        quote=None
        # Live widgets rerun when amounts change; st.form batches them until save.
        with st.container(border=True,key=f"disburse_salary_form_v{salary_version}"):
            col1, col2, col3 = st.columns(3)
            salary_month = col1.text_input("عن شهر (YYYY-MM) *", value=current_month, key=f"salary_month_v{salary_version}")
            base_salary = col2.number_input("الراتب الأساسي (أوقية قديمة)", min_value=0.0, value=default_salary, step=50.0, key=f"salary_base_v{salary_version}_{t_id or 'none'}")
            bonus = col3.number_input("مكافأة / إضافي (أوقية قديمة)", min_value=0.0, value=0.0, step=50.0, key=f"salary_bonus_v{salary_version}")

            col4, col5 = st.columns(2)
            deductions = col4.number_input("خصومات (أوقية قديمة)", min_value=0.0, value=0.0, step=50.0, key=f"salary_deductions_v{salary_version}")
            notes = col5.text_input("ملاحظات إضافية (اختياري)", key=f"salary_notes_v{salary_version}")

            if t_id:
                try:
                    preview=P.salary_preview(base_salary,bonus,deductions)
                    quote={'teacher':t_id,'month':salary_month,**preview}
                    st.info(f"💵 **صافي الراتب المستحق للصرف:** {H.format_money(preview['net'])} أوقية قديمة")
                except ValueError as error:
                    st.error(str(error))
            else:
                st.info('اختر المعلمة لعرض صافي الراتب قبل الصرف.')

            pay_submitted = st.button("🧾 تسجيل الصرف وطباعة قسيمة الراتب",
                key=f'salary_save_v{salary_version}',type="primary",use_container_width=True,
                disabled=quote is None)

        st.session_state[quote_key]=quote
        if pay_submitted:
            try:
                if not t_id:
                    raise ValueError("اختر المعلمة أولاً.")
                if quote is None or previous_quote!=quote:
                    raise ValueError('تغيّرت البيانات؛ راجع صافي الراتب المحدّث ثم اضغط تسجيل الصرف مرة أخرى.')
                payment_id, created = P.save_salary(t_id, salary_month, base_salary,
                    bonus, deductions, notes, actor=st.session_state.get("auth_user", "مديرة الروضة"),
                    token=st.session_state["salary_request_token"])
                st.session_state["salary_saved_notice"] = (
                    f"تم صرف الراتب وحفظ القسيمة #{payment_id}" if created
                    else f"هذه القسيمة محفوظة سابقاً #{payment_id}")
                st.session_state["salary_request_token"] = str(uuid.uuid4())
                st.session_state["salary_form_version"] = salary_version+1
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("تعذّر تسجيل الصرف. لم يتم إنشاء قسيمة جديدة.")

    # ---------------------------------- TAB 2: LOG, REPRINT, EDIT & DELETE --
    with tab_log:
        salary_logs = ui.df(conn, """
            SELECT tp.payment_id, tp.national_id, COALESCE(t.display_national_id,t.national_id) AS display_national_id,t.full_name AS "المعلمة",
                   tp.salary_month AS "عن شهر", tp.base_salary AS "الأساسي",
                   tp.bonus AS "المكافأة", tp.deductions AS "الخصم",
                   tp.cash_amount AS "الصافي المدفوع", CASE tp.record_state
                       WHEN 'active' THEN 'نشطة' WHEN 'cancelled' THEN 'ملغاة'
                       ELSE tp.record_state END AS "الحالة", tp.payment_date AS "تاريخ الصرف",
                   tp.notes AS "ملاحظات"
            FROM teacher_payments tp
            JOIN teachers t ON t.national_id = tp.national_id
            ORDER BY tp.payment_id DESC
        """)

        if salary_logs.empty:
            ui.empty_state("لا توجد رواتب مدفوعة مسجلة بعد.")
        else:
            search = st.text_input("🔍 ابحث باسم المعلمة أو الشهر",key='salary_log_search')
            shown = salary_logs.copy()
            if search:
                shown = shown[shown["المعلمة"].str.contains(search, na=False, regex=False) |
                              shown["عن شهر"].str.contains(search, na=False, regex=False)]

            display_df = shown.drop(columns=['payment_id', 'national_id','display_national_id'])
            ui.dataframe(display_df, use_container_width=True, hide_index=True)
            st.metric("💰 مجموع النقد المصروف فعلاً", f"{H.format_money(shown['الصافي المدفوع'].sum())} أوقية قديمة")

            st.markdown("---")
            st.markdown("##### ⚙️ إدارة القسيمة المحددة (إعادة طباعة / تعديل / حذف)")

            sal_options = [
                (
                    int(row['payment_id']),
                    f"قسيمة #{int(row['payment_id'])} — {row['المعلمة']} — شهر {row['عن شهر']} — صافي: {H.format_money(row['الصافي المدفوع'])} أوقية قديمة"
                )
                for _, row in salary_logs.iterrows()
            ]

            selected_sal = st.selectbox(
                "اختر قسيمة الراتب",
                options=sal_options,
                format_func=lambda x: x[1] if x else "اختر...",
                index=None,
                placeholder="اختر قسيمة...",
                key="salary_select_edit"
            )

            if selected_sal:
                p_id = selected_sal[0]
                sal_row = salary_logs[salary_logs['payment_id'] == p_id].iloc[0]

                # 🖨️ Reprint Option
                if st.button("🖨️ إعادة عرض / طباعة القسيمة المحددة", use_container_width=True):
                    teacher_receipt.render_salary_slip(
                        payment_id=p_id,
                        teacher_name=sal_row['المعلمة'],
                        national_id=sal_row['display_national_id'],
                        payment_date=str(sal_row['تاريخ الصرف']),
                        salary_month=sal_row['عن شهر'],
                        base_salary=float(sal_row['الأساسي']),
                        bonus=float(sal_row['المكافأة']),
                        deductions=float(sal_row['الخصم']),
                        net_amount=float(sal_row['الصافي المدفوع']),
                        notes=sal_row['ملاحظات'] or ""
                    )

                ui.open_record_editor('teacher_payments',int(p_id),'تعديل مبلغ الراتب أو إلغاء الإدخال')
                salary_snapshot,salary_snapshot_key=ui.edit_snapshot(conn,'teacher_payments',int(p_id),scope='salary_'+str(p_id),widget_prefix='salary_meta_')
                # Document-only review keeps cash; monetary corrections use the full editor.
                with st.expander(f"✏️ تصحيح بيانات / إلغاء القسيمة #{p_id}", expanded=False):
                    with st.form("edit_salary_form"):
                        ec1, ec2, ec3 = st.columns(3)
                        e_month = ec1.text_input("عن شهر", value=sal_row['عن شهر'])
                        e_base = ec2.number_input("الراتب الأساسي", min_value=0.0, value=float(sal_row['الأساسي']), step=50.0, disabled=True)
                        e_bonus = ec3.number_input("المكافأة", min_value=0.0, value=float(sal_row['المكافأة']), step=50.0, disabled=True)

                        ec4, ec5 = st.columns(2)
                        e_deductions = ec4.number_input("الخصومات", min_value=0.0, value=float(sal_row['الخصم']), step=50.0, disabled=True)
                        e_notes = ec5.text_input("ملاحظات", value=sal_row['ملاحظات'] or "")

                        e_net = max(0.0, e_base + e_bonus - e_deductions)
                        st.caption(f"💡 صافي الراتب الجديد بعد التعديل: **{H.format_money(e_net)} أوقية قديمة**")

                        st.caption("التصحيح هنا للبيانات فقط؛ النقد المصروف أصلاً لا يتغير ولا تُعتبر الإزالة استردادًا.")
                        reason = st.text_input("سبب التصحيح أو الإلغاء *",key=f"payroll_reason_{p_id}")
                        confirm_document=st.checkbox('أفهم أن إلغاء القسيمة يبقي مبلغ الصرف في الحسابات',key=f'salary_meta_confirm_{p_id}')
                        btn1, btn2 = st.columns(2)
                        save_edit = btn1.form_submit_button("حفظ التصحيح", type="primary")
                        delete_sal = btn2.form_submit_button("إلغاء القسيمة مع الاحتفاظ بالصرف")
                        if save_edit or delete_sal:
                            try:
                                if delete_sal and not confirm_document: raise ValueError('أكد بقاء النقد المصروف قبل إلغاء المستند.')
                                import records as R
                                P.amend("teacher_payments", p_id, actor=st.session_state.get("auth_user","مديرة الروضة"),
                                        reason=reason, cancel=delete_sal, month=e_month, notes=e_notes,expected=R.revision(salary_snapshot))
                                st.session_state.pop(salary_snapshot_key,None)
                                st.session_state["salary_saved_notice"] = "تم حفظ قرار التدقيق دون تغيير مبلغ النقد المصروف."
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))
                            except Exception:
                                st.error("تعذّر حفظ التصحيح أو الإلغاء.")

    # An advance is a cash event when paid. Later deductions in a salary slip
    # affect its NET salary amount; no second expense is generated for the advance.
    with tab_advance:
        st.caption("السلفة المصروفة تُسجل مرة عند الدفع، ولا تُحسب ثانية عند خصمها من الراتب.")
        advance_version=st.session_state.get("advance_form_version",0)
        st.session_state.setdefault("advance_request_token",str(uuid.uuid4()))
        advance_notice=st.session_state.pop("advance_saved_notice",None)
        if advance_notice:
            st.success(advance_notice)
        with st.form(f"teacher_cash_advance_form_v{advance_version}"):
            teacher=st.selectbox("المعلمة",list(teacher_map.keys()),index=None,
                                 key=f"advance_teacher_v{advance_version}")
            advance_month=st.text_input("تُخصم عن شهر (YYYY-MM)",
                                      value=business_today().strftime("%Y-%m"),
                                      key=f"advance_month_v{advance_version}")
            advance_day=st.date_input("تاريخ صرف السلفة",value=business_today(), key=f"advance_date_v{advance_version}")
            advance_amount=st.number_input("مبلغ السلفة (أوقية قديمة)",
                min_value=0.0,step=1.0,format="%.2f",key=f"advance_amount_v{advance_version}")
            advance_note=st.text_input("ملاحظات (اختياري)",
                                      key=f"advance_note_v{advance_version}")
            submitted=st.form_submit_button("💾 تسجيل السلفة المدفوعة",type="primary")
        if submitted:
            try:
                if not teacher:
                    raise ValueError("اختر المعلمة.")
                aid,created=P.save_advance(teacher_map[teacher][0],advance_month,
                    advance_amount,advance_note,actor=st.session_state.get("auth_user","مديرة الروضة"),
                    token=st.session_state["advance_request_token"],on_date=advance_day)
                st.session_state["advance_saved_notice"] = (
                    f"تم حفظ صرف السلفة #{aid}" if created else f"السلفة محفوظة سابقاً #{aid}")
                st.session_state["advance_request_token"]=str(uuid.uuid4())
                st.session_state["advance_form_version"]=advance_version+1
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("تعذّر صرف السلفة؛ لم تُنشأ دفعة جديدة.")
        advances=ui.df(conn,"""SELECT a.advance_id AS "رقم السلفة",
               t.full_name AS "المعلمة",a.advance_date AS "تاريخ الصرف",
               a.salary_month AS "شهر الخصم",a.cash_amount AS "المبلغ",CASE a.record_state
                   WHEN 'active' THEN 'نشطة' WHEN 'cancelled' THEN 'ملغاة'
                   ELSE a.record_state END AS "الحالة",
               a.is_deducted AS "خُصمت",a.notes AS "ملاحظات"
            FROM teacher_advances a JOIN teachers t ON t.national_id=a.national_id
            ORDER BY a.advance_id DESC""")
        if not advances.empty:
            ui.dataframe(advances,hide_index=True,use_container_width=True)
            aid=st.selectbox("اختر سلفة للمراجعة",list(advances["رقم السلفة"]),index=None)
            if aid:
                entry=advances[advances["رقم السلفة"]==aid].iloc[0]
                ui.open_record_editor('teacher_advances',int(aid),'تعديل مبلغ السلفة أو إلغاء الإدخال')
                advance_snapshot,advance_snapshot_key=ui.edit_snapshot(conn,'teacher_advances',int(aid),scope='advance_'+str(aid),widget_prefix='advance_meta_')
                st.caption("إلغاء المستند يبقي مبلغ الصرف في التقرير. إلغاء إدخال مالي خاطئ من المحرر يزيل أثره من الصرف.")
                with st.form(f"advance_audit_{aid}"):
                    corrected_month=st.text_input("شهر الخصم الصحيح",value=entry["شهر الخصم"])
                    corrected_notes=st.text_input("ملاحظات",value=entry["ملاحظات"] or "")
                    audit_reason=st.text_input("السبب *")
                    a,b=st.columns(2)
                    edit=a.form_submit_button("تصحيح بيانات السلفة")
                    confirm_advance=st.checkbox('أفهم أن إلغاء مستند السلفة يبقي النقد المصروف',key=f'advance_meta_confirm_{aid}')
                    void=b.form_submit_button("إلغاء مستند السلفة")
                    if edit or void:
                        try:
                            if void and not confirm_advance: raise ValueError('أكد بقاء النقد المصروف قبل إلغاء المستند.')
                            import records as R
                            P.amend("teacher_advances",int(aid),actor=st.session_state.get("auth_user","مديرة الروضة"),
                                    reason=audit_reason,cancel=void,month=corrected_month,notes=corrected_notes,expected=R.revision(advance_snapshot))
                            st.session_state.pop(advance_snapshot_key,None)
                            st.success("حُفظ التدقيق؛ النقد المصروف محفوظ.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
                        except Exception:
                            st.error("تعذّر حفظ تدقيق السلفة.")
