"""Parents: lookup and edit only. New families are created with a child."""
import streamlit as st

import db
import student_debt as D
import ui


def render(conn):
    ui.section_header("👨‍👩‍👧", "أولياء الأمور", "بيانات الأهل والأطفال المرتبطين")

    search = st.text_input("🔍 ابحث بالاسم أو رقم الهاتف",
        placeholder="اسم الأب أو الأم، أو هاتف أحدهما").strip()

    sql = """
        SELECT p.father_id, p.father_name, p.mother_name,
               p.father_mobile, p.mother_mobile, p.contact_email,
               COALESCE((
                   SELECT string_agg(s.full_name, '، ' ORDER BY s.full_name, s.student_id)
                   FROM students s WHERE s.father_id=p.father_id
               ), '') AS linked_children
        FROM parents p WHERE p.archived_at IS NULL
    """
    params = ()
    if search:
        sql += """ AND (p.father_name ILIKE %s OR p.mother_name ILIKE %s
                    OR p.father_mobile ILIKE %s OR p.mother_mobile ILIKE %s) """
        params = tuple([f"%{search}%"] * 4)
    sql += " ORDER BY COALESCE(p.father_name, p.mother_name), p.father_id"
    parents = ui.df(conn, sql, params)
    if parents.empty:
        ui.empty_state("لا توجد سجلات مطابقة.")
    else:
        table = parents.rename(columns={
            "father_name": "اسم الأب", "mother_name": "اسم الأم",
            "father_mobile": "هاتف الأب", "mother_mobile": "هاتف الأم",
            "contact_email": "بريد التواصل",
            "linked_children": "الأطفال المرتبطون"
        })
        # Display empty SQL values as blank cells, never literal None/nan.
        ui.dataframe(table[["اسم الأب", "هاتف الأب", "اسم الأم", "هاتف الأم",
                             "بريد التواصل", "الأطفال المرتبطون"]].fillna(""),
                     use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### ✏️ تعديل أو حذف ولي أمر")
    all_parents = ui.df(conn, """
        SELECT father_id, father_name, mother_name FROM parents WHERE archived_at IS NULL
        ORDER BY COALESCE(father_name, mother_name), father_id
    """)
    if all_parents.empty:
        return
    options = [(row["father_id"],
                " / ".join(name for name in (row["father_name"], row["mother_name"])
                           if isinstance(name, str) and name.strip()))
               for _, row in all_parents.iterrows()]
    chosen = st.selectbox("اختر ولي الأمر", options,
        format_func=lambda value: value[1], index=None,
        placeholder="ابحث عن ولي أمر...", key="parent_select_edit")
    if not chosen:
        return

    fid = chosen[0]
    ui.open_record_editor('parents',fid,'تعديل كامل / حذف ملف ولي الأمر مع حفظ ارتباط الأطفال')
    with conn.cursor() as cur:
        cur.execute("""SELECT father_id, father_name, mother_name,
                              father_mobile, mother_mobile, contact_email
                       FROM parents WHERE father_id=%s""", (fid,))
        parent = cur.fetchone()
    if not parent:
        st.warning("ولي الأمر غير موجود.")
        return

    children = ui.df(conn, """
        SELECT s.student_id, s.full_name,
               COALESCE(string_agg(DISTINCT
                   (c.class_type || ' ' || c.section || ' — ' || r.year_id),
                   '، '), '') AS registrations
        FROM students s
        LEFT JOIN registrations r ON r.student_id=s.student_id
        LEFT JOIN classes c ON c.class_id=r.class_id
        WHERE s.father_id=%s
        GROUP BY s.student_id, s.full_name
        ORDER BY s.full_name, s.student_id
    """, (fid,))
    st.markdown("##### 👧 الأطفال المرتبطون")
    if children.empty:
        st.caption("لا يوجد أطفال مرتبطون بهذا السجل.")
    else:
        for _, child in children.iterrows():
            registration = f" — {child['registrations']}" if child["registrations"] else ""
            st.write(f"• {child['full_name']}{registration}")

    with st.expander(f"⚙️ تعديل بيانات: {chosen[1]}", expanded=True):
        with st.form(f"edit_parent_form_{fid}", clear_on_submit=False):
            a, b = st.columns(2)
            father_name = a.text_input("اسم الأب", value=parent["father_name"] or "").strip()
            father_phone = a.text_input("هاتف الأب", value=parent["father_mobile"] or "").strip()
            mother_name = b.text_input("اسم الأم", value=parent["mother_name"] or "").strip()
            mother_phone = b.text_input("هاتف الأم", value=parent["mother_mobile"] or "").strip()
            email = st.text_input("بريد التواصل (اختياري)",
                                  value=parent["contact_email"] or "").strip()
            b1, b2 = st.columns(2)
            save = b1.form_submit_button("💾 حفظ التعديلات", type="primary",
                                         use_container_width=True)
            delete = b2.form_submit_button("🗑️ حذف ولي الأمر",
                                           use_container_width=True)
            if save:
                error = db.contact_validation_error(
                    father_name, father_phone, mother_name, mother_phone)
                if error:
                    st.error(error)
                elif any(len(v) > 100 for v in (father_name, mother_name)) or any(
                        len(v) > 20 for v in (father_phone, mother_phone)):
                    st.error("أحد الأسماء أو أرقام الهواتف أطول من المسموح.")
                elif len(email) > 254 or (email and ("@" not in email or " " in email)):
                    st.error("يرجى التحقق من بريد التواصل.")
                else:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE parents SET father_name=%s, father_mobile=%s,
                                   mother_name=%s, mother_mobile=%s, contact_email=%s
                                WHERE father_id=%s
                            """, (father_name or None, father_phone or None,
                                  mother_name or None, mother_phone or None,
                                  email or None, fid))
                        st.success("تم تحديث بيانات ولي الأمر.")
                        st.rerun()
                    except Exception:
                        conn.rollback()
                        st.error("تعذّر حفظ التعديلات؛ يرجى المحاولة مجدداً.")

            if delete:
                try:
                    D.remove_guardian_if_unlinked(fid)
                    st.success("حُذف ملف ولي الأمر غير المرتبط بأي طفل.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    st.error("تعذّر حذف ولي الأمر دون المساس بملفات الأطفال.")
