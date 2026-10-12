"""
sections/payments.py — الدفعات المالية

Records a cash payment against a registration, updates the registration's
status automatically, shows the remaining yearly balance, and offers a
one-click printable receipt. Also supports editing, deleting, or re-printing
any historical payment receipt.
"""

import streamlit as st

import ui
import helpers as H
import receipt
import historical_finance as legacy
from sections import monthly_payments


def _get_registration_tuition(conn, registration_id):
    """Fetches tuition directly from registrations database record."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(annual_tuition, 3500.0) AS annual_tuition FROM registrations WHERE registration_id = %s", (registration_id,))
        res = cur.fetchone()
        cur.close()
        if res is None:
            return 3500.0
        return float(res['annual_tuition'] if isinstance(res, dict) else res[0])
    except Exception:
        return 3500.0


def render(conn):
    ui.section_header("💵", "الدفعات المالية", "حسابات الأوقية القديمة، والإيصالات التاريخية")
    tab_accounts, tab_receipts, tab_prices, tab_old = st.tabs([
        "📅 حسابات الأطفال الشهرية", "🧾 وصولات شهرية", "⚙️ إعدادات الرسوم",
        "📂 الدفعات السنوية القديمة"])
    with tab_accounts:
        monthly_payments.render_accounts(conn)
    with tab_receipts:
        monthly_payments.render_receipts(conn)
    with tab_prices:
        monthly_payments.render_settings(conn)
    with tab_old:
        _render_historical(conn)


def _render_historical(conn):
    st.caption("السجلات السنوية القديمة محفوظة بعملتها وقيمها الأصلية.")
    ui.section_header("💵", "الدفعات المالية", "تسجيل دفعة نقدية وطباعة وصل استلام")

    active_regs = ui.df(conn, """
        SELECT r.registration_id, s.full_name AS student_name, p.father_name,
               (c.class_type || ' ' || c.section) AS class_label, r.year_id, r.status
        FROM registrations r
        JOIN students s ON s.student_id = r.student_id
        JOIN classes c ON c.class_id = r.class_id
        JOIN parents p ON p.father_id = s.father_id
        WHERE NOT EXISTS (SELECT 1 FROM monthly_accounts ma WHERE ma.student_id=s.student_id)
        ORDER BY r.registration_id DESC
    """)

    if active_regs.empty:
        ui.empty_state("لا يوجد طلاب مسجلون بعد. قم بتسجيل طالب أولاً من صفحة «التسجيل».")
        return

    tab_add, tab_view = st.tabs(["➕ تسجيل دفعة كاش", "📋 سجل الدفعات والإعادة"])

    # -------------------------------------------------- TAB 1: ADD PAYMENT --
    with tab_add:
        active_regs['label'] = (active_regs['student_name'] + "  |  " + active_regs['class_label'] +
                                 "  |  " + active_regs['year_id'] + "  (" + active_regs['status'] + ")")
        reg_dict = dict(zip(active_regs['label'], active_regs['registration_id']))
        selected_label = st.selectbox("اختر الطالب والتسجيل", list(reg_dict.keys()))
        selected_row = active_regs[active_regs['label'] == selected_label].iloc[0]
        reg_id_preview = int(selected_row['registration_id'])

        reg_tuition = _get_registration_tuition(conn, reg_id_preview)
        paid_so_far = H.compute_paid_toward_tuition(conn, reg_id_preview)
        remaining_before = H.compute_remaining_balance(conn, reg_id_preview)

        i1, i2, i3 = st.columns(3)
        i1.metric("الرسوم السنوية", f"{H.format_money(reg_tuition)}")
        i2.metric("المدفوع حتى الآن", f"{H.format_money(paid_so_far)}")
        i3.metric("المتبقي", f"{H.format_money(remaining_before)}")

        with st.form("add_payment_form"):
            c1, c2 = st.columns(2)
            amount = c1.number_input("المبلغ المدفوع (كاش) *", min_value=1.0, value=100.0, step=10.0)
            payer = c2.text_input("اسم الدافع (ولي الأمر) *", value=selected_row['father_name'])

            c3, c4 = st.columns(2)
            reason = c3.selectbox("مقابل *", H.PAYMENT_FOR)
            reason_other = c4.text_input("تفاصيل أخرى") if reason == "آخر" else ""

            submitted = st.form_submit_button("🧾 حفظ الدفعة وطباعة الوصل", type="primary", use_container_width=True)

        if submitted:
            reg_id = int(selected_row['registration_id'])
            today = H.today_str()
            try:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO payments (registration_id, amount, payment_date, payment_method,
                        payer_name, payment_for, payment_for_other)
                    VALUES (%s, %s, %s, 'كاش', %s, %s, %s)
                    RETURNING receipt_number
                ''', (reg_id, amount, today, payer, reason, reason_other))
                receipt_id = cur.fetchone()['receipt_number']
                conn.commit()
                cur.close()
            except Exception as e:
                conn.rollback()
                st.error("تعذّر تسجيل الدفعة التاريخية؛ لم تُحفظ العملية.")
            else:
                new_status = H.refresh_registration_status(conn, reg_id)
                remaining_after = H.compute_remaining_balance(conn, reg_id)

                st.success(f"✅ تم حفظ الدفعة بنجاح! رقم الوصل: #{receipt_id} — حالة التسجيل الآن: {new_status}")

                receipt.render_receipt(
                    receipt_id=receipt_id,
                    date=today,
                    student_name=selected_row['student_name'],
                    payer=payer,
                    amount=H.format_money(amount),
                    reason=reason,
                    remaining=H.format_money(remaining_after),
                    reason_other=reason_other,
                )

    # ---------------------------------- TAB 2: VIEW / REPRINT / EDIT / DELETE --
    with tab_view:
        notice = st.session_state.pop("legacy_receipt_notice", None)
        if notice:
            st.success(notice)
        payments = ui.df(conn, """
            SELECT p.receipt_number AS "رقم الوصل", s.full_name AS "اسم الطالب",
                   p.amount AS "المبلغ", p.payment_date AS "التاريخ",
                   p.payer_name AS "الدافع", p.payment_for AS "مقابل",
                   p.payment_for_other AS "تفاصيل أخرى", p.registration_id,
                   p.receipt_state AS "حالة الوصل", p.cancel_reason AS "سبب الإلغاء"
            FROM payments p
            JOIN registrations r ON p.registration_id = r.registration_id
            JOIN students s ON r.student_id = s.student_id
            ORDER BY p.receipt_number DESC
        """)
        if payments.empty:
            ui.empty_state("لا توجد دفعات مسجلة بعد.")
        else:
            search = st.text_input("🔍 ابحث باسم الطالب أو الدافع")
            shown = payments.copy()
            if search:
                shown = shown[shown["اسم الطالب"].str.contains(search, na=False) |
                               shown["الدافع"].str.contains(search, na=False)]
            
            display = shown.drop(columns=["registration_id", "تفاصيل أخرى", "سبب الإلغاء"]).copy()
            display["حالة الوصل"] = display["حالة الوصل"].replace(
                {"active": "ساري", "cancelled": "ملغى"})
            ui.dataframe(display, use_container_width=True, hide_index=True)
            active_sum = shown.loc[shown["حالة الوصل"] == "active", "المبلغ"].sum()
            st.metric("💰 مجموع الدفعات السارية المعروضة", H.format_money(active_sum))

            st.markdown("---")
            st.markdown("##### ⚙️ إدارة الوصل المحدد (إعادة طباعة / تصحيح / إلغاء)")

            # Select by immutable receipt number: the displayed label changes
            # after a correction, but the selection must remain stable on rerun.
            pay_labels = {
                int(row["رقم الوصل"]):
                f"وصل #{int(row['رقم الوصل'])} — {row['اسم الطالب']} — {H.format_money(row['المبلغ'])} شيكل"
                for _, row in payments.iterrows()
            }
            # After a write, explicitly restore the receipt selection before
            # constructing this widget. Streamlit may otherwise invalidate the
            # display-formatted selection on the following rerun.
            restored = st.session_state.pop("legacy_restore_receipt", None)
            if restored in pay_labels:
                st.session_state["payment_select_edit"] = restored
            selected = st.selectbox(
                "اختر الوصل للطباعة أو التعديل", options=list(pay_labels),
                format_func=lambda rid: pay_labels[rid],
                index=None, placeholder="اختر وصل استلام...", key="payment_select_edit",
            )

            if selected is not None:
                receipt_no = int(selected)
                row = payments[payments['رقم الوصل'] == receipt_no].iloc[0]
                reg_id_sel = int(row['registration_id'])

                # 🖨️ Reprint Option
                if st.button("🖨️ إعادة عرض / طباعة الوصل المحدد", use_container_width=True):
                    rem_bal = H.compute_remaining_balance(conn, reg_id_sel)
                    receipt.render_receipt(
                        receipt_id=receipt_no,
                        date=str(row['التاريخ']),
                        student_name=row['اسم الطالب'],
                        payer=row['الدافع'],
                        amount=H.format_money(row['المبلغ']),
                        reason=("وصل ملغى — " + str(row["مقابل"])
                                if row["حالة الوصل"] == "cancelled" else row["مقابل"]),
                        remaining=H.format_money(rem_bal),
                        reason_other=((row["تفاصيل أخرى"] or "") +
                            (" — سبب الإلغاء: " + str(row["سبب الإلغاء"] or ""))
                            if row["حالة الوصل"] == "cancelled" else
                            (row["تفاصيل أخرى"] or "")),
                    )

                if row["حالة الوصل"] == "cancelled":
                    st.warning("هذا الوصل ملغى ومحفوظ للمراجعة؛ لا يمكن تعديله.")
                    return

                with st.expander(f"✏️ تصحيح أو إلغاء الوصل #{receipt_no}", expanded=False):
                    with st.form("edit_payment_form"):
                        c1, c2 = st.columns(2)
                        e_amount = c1.number_input("المبلغ", min_value=0.01,
                                                   value=float(row["المبلغ"]), step=10.0)
                        e_payer = c2.text_input("اسم الدافع", value=row["الدافع"] or "")
                        c3, c4 = st.columns(2)
                        e_reason = c3.selectbox(
                            "مقابل", H.PAYMENT_FOR,
                            index=H.PAYMENT_FOR.index(row["مقابل"]) if row["مقابل"] in H.PAYMENT_FOR else 0
                        )
                        e_other = c4.text_input("تفاصيل أخرى", value=row["تفاصيل أخرى"] or "")
                        audit_reason = st.text_input("سبب التصحيح أو الإلغاء *")
                        b1, b2 = st.columns(2)
                        save = b1.form_submit_button("💾 حفظ التصحيح", type="primary",
                                                     use_container_width=True)
                        delete = b2.form_submit_button("إلغاء الوصل مع الاحتفاظ بالسجل",
                                                       use_container_width=True)
                        if save or delete:
                            try:
                                registration = legacy.change_receipt(
                                    receipt_no,
                                    actor=st.session_state.get("auth_user", ""),
                                    reason=audit_reason, cancel=bool(delete),
                                    new_amount=e_amount, payer=e_payer,
                                    payment_for=e_reason, details=e_other)
                                H.refresh_registration_status(conn, registration)
                                if delete:
                                    st.session_state["legacy_receipt_notice"] = "أُلغي الوصل؛ حُفظت بياناته الأصلية وسبب الإلغاء."
                                else:
                                    st.session_state["legacy_receipt_notice"] = "حُفظ التصحيح ونسخته السابقة في سجل المراجعة."
                                st.session_state["legacy_restore_receipt"] = receipt_no
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                            except Exception:
                                st.error("تعذّر حفظ العملية. لم تُحذف بيانات الوصل.")
