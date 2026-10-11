"""Child records: one child+family form, separate academic-year registration."""
from datetime import date
import uuid

import pandas as pd
import streamlit as st

import db
import helpers as H
import ui


ADD_KEYS = ("kid_name", "kid_birth", "kid_gender", "kid_place", "kid_address",
            "kid_father_name", "kid_father_phone", "kid_mother_name",
            "kid_mother_phone", "kid_email", "kid_health", "kid_allergy",
            "kid_notes", "kid_pickups")


def _parse_pickups(raw):
    """One authorised contact per line: name | phone (both required)."""
    people = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("اكتب كل مخوّل بالاستلام في سطر: الاسم | رقم الهاتف.")
        if len(parts[0]) > 100 or len(parts[1]) > 20:
            raise ValueError("اسم المخوّل أو رقم هاتفه أطول من المسموح.")
        people.append({"name": parts[0], "phone": parts[1]})
    return people


def _format_pickups(value):
    if not isinstance(value, list):
        return ""
    return "\n".join(f"{person.get('name','')} | {person.get('phone','')}"
                     for person in value if isinstance(person, dict))


def _reset_after_success():
    if st.session_state.pop("kid_saved_reset", False):
        for key in ADD_KEYS:
            st.session_state.pop(key, None)
        st.session_state["kid_request_token"] = str(uuid.uuid4())


def render(conn):
    _reset_after_success()
    if "kid_request_token" not in st.session_state:
        st.session_state["kid_request_token"] = str(uuid.uuid4())

    ui.section_header("🎒", "إدارة الطلاب", "إضافة وتعديل ومتابعة بيانات الأطفال")
    tab_add, tab_view = st.tabs(["➕ إضافة طالب جديد", "📋 عرض / تعديل / حذف"])
    parents = ui.df(conn, """
        SELECT father_id, father_name, mother_name, father_mobile, mother_mobile
        FROM parents ORDER BY COALESCE(father_name, mother_name)
    """)
    family_choices = []
    for _, row in parents.iterrows():
        names = " / ".join(x for x in (row["father_name"], row["mother_name"])
                           if isinstance(x, str) and x.strip())
        phones = " / ".join(x for x in (row["father_mobile"], row["mother_mobile"])
                            if isinstance(x, str) and x.strip())
        family_choices.append((row["father_id"], f"{names} — {phones}"))

    with tab_add:
        use_existing = False
        if family_choices:
            use_existing = st.checkbox("اختيار ولي أمر موجود", key="kid_use_existing")
        with st.form("add_student_form", clear_on_submit=False):
            st.markdown("##### 🎒 بيانات الطفل")
            c1, c2 = st.columns(2)
            full_name = c1.text_input("اسم الطفل *", key="kid_name").strip()
            birth_date = c2.date_input("تاريخ الميلاد *", value=date(2022, 1, 1),
                                       min_value=date(1990, 1, 1), max_value=date.today(),
                                       key="kid_birth")
            c3, c4 = st.columns(2)
            gender = c3.selectbox("الجنس *", H.GENDERS, key="kid_gender")
            birth_place = c4.text_input("مكان الميلاد (اختياري)", key="kid_place").strip()
            address = st.text_input("العنوان (اختياري)", key="kid_address").strip()

            selected_parent_id = None
            family = dict(father_name="", father_mobile="", mother_name="",
                          mother_mobile="", contact_email="")
            st.markdown("##### 👨‍👩‍👧 بيانات الأهل")
            if use_existing:
                choice = st.selectbox("ولي الأمر الموجود", family_choices,
                    format_func=lambda option: option[1], key="kid_existing_family")
                selected_parent_id = choice[0]
                st.caption("بيانات الأهل المشتركة تُعدّل من صفحة أولياء الأمور.")
            else:
                a, b = st.columns(2)
                family["father_name"] = a.text_input("اسم الأب", key="kid_father_name").strip()
                family["father_mobile"] = a.text_input("هاتف الأب", key="kid_father_phone").strip()
                family["mother_name"] = b.text_input("اسم الأم", key="kid_mother_name").strip()
                family["mother_mobile"] = b.text_input("هاتف الأم", key="kid_mother_phone").strip()
                family["contact_email"] = st.text_input(
                    "بريد التواصل (اختياري)", key="kid_email").strip()

            with st.expander("تفاصيل اختيارية"):
                medical = st.text_area("ملاحظات صحية", key="kid_health")
                allergies = st.text_area("الحساسية", key="kid_allergy")
                notes = st.text_area("ملاحظات عامة", key="kid_notes")
                pickups = st.text_area("المخولون باستلام الطفل",
                    placeholder="اسم الشخص | رقم الهاتف\nاسم شخص آخر | رقم الهاتف",
                    key="kid_pickups", help="كل شخص في سطر مستقل: الاسم | رقم الهاتف")
            submitted = st.form_submit_button("💾 حفظ بيانات الطفل والأهل",
                                               type="primary", use_container_width=True)
            if submitted:
                try:
                    if not full_name:
                        raise ValueError("يرجى كتابة اسم الطفل.")
                    if any(len(v) > 100 for v in (full_name, birth_place,
                          family["father_name"], family["mother_name"])):
                        raise ValueError("أحد الأسماء أو مكان الميلاد طويل جداً.")
                    if any(len(v) > 20 for v in (family["father_mobile"], family["mother_mobile"])):
                        raise ValueError("رقم الهاتف أطول من المسموح.")
                    if len(family["contact_email"]) > 254:
                        raise ValueError("بريد التواصل أطول من المسموح.")
                    if family["contact_email"] and (
                        "@" not in family["contact_email"] or " " in family["contact_email"]):
                        raise ValueError("يرجى كتابة بريد تواصل صحيح.")
                    child = dict(full_name=full_name, birth_date=birth_date, gender=gender,
                        birth_place=birth_place, address=address, medical_details=medical,
                        allergies=allergies, general_notes=notes,
                        authorized_pickups=_parse_pickups(pickups))
                    _, created = db.save_child_with_family(
                        child, family, selected_parent_id, st.session_state["kid_request_token"])
                    if created:
                        st.success("تم حفظ الطفل والأهل وربطهما بنجاح.")
                    else:
                        st.info("تم حفظ هذا الطلب سابقاً، ولم تُنشأ نسخة مكررة.")
                    st.session_state["kid_saved_reset"] = True
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("تعذّر حفظ البيانات. لم تُحفظ الأسرة جزئياً؛ راجع البيانات وحاول مجدداً.")

    with tab_view:
        students = ui.df(conn, """
            SELECT s.student_id, s.full_name, s.birth_date, s.gender, s.birth_place,
                   s.address, s.medical_details, s.allergies, s.general_notes,
                   s.authorized_pickups, s.father_id,
                   COALESCE(p.father_name, p.mother_name) AS parent_name
            FROM students s JOIN parents p ON p.father_id=s.father_id
            ORDER BY s.created_at DESC
        """)
        if students.empty:
            ui.empty_state("لا يوجد طلاب مسجلون بعد.")
            return
        search = st.text_input("🔍 ابحث باسم الطفل").strip()
        shown = students[students["full_name"].str.contains(
            search, case=False, na=False, regex=False)] if search else students
        display = shown.copy()
        display["العمر"] = display["birth_date"].apply(H.calculate_age)
        ui.dataframe(display.rename(columns={
            "full_name": "الاسم", "birth_date": "تاريخ الميلاد",
            "gender": "الجنس", "parent_name": "ولي الأمر"})[
            ["الاسم", "العمر", "تاريخ الميلاد", "الجنس", "ولي الأمر"]],
            use_container_width=True, hide_index=True)
        st.markdown("---")
        st.markdown("##### ✏️ تعديل أو حذف طالب")
        options = [(row["student_id"], row["full_name"]) for _, row in students.iterrows()]
        chosen = st.selectbox("اختر الطفل", options,
            format_func=lambda x: x[1], index=None, placeholder="ابحث عن طفل...",
            key="student_select_edit")
        if chosen:
            sid = chosen[0]
            row = students[students["student_id"] == sid].iloc[0]
            with st.expander(f"⚙️ تعديل بيانات: {row['full_name']}", expanded=True):
                with st.form(f"edit_student_form_{sid}"):
                    c1, c2, c3 = st.columns(3)
                    e_name = c1.text_input("اسم الطفل", value=row["full_name"])
                    old_date = pd.to_datetime(row["birth_date"], errors="coerce")
                    e_birth = c2.date_input("تاريخ الميلاد",
                        value=old_date.date() if pd.notna(old_date) else date(2022, 1, 1),
                        min_value=date(1990, 1, 1), max_value=date.today())
                    e_gender = c3.selectbox("الجنس", H.GENDERS,
                        index=H.GENDERS.index(row["gender"]) if row["gender"] in H.GENDERS else 0)
                    a, b = st.columns(2)
                    e_place = a.text_input("مكان الميلاد (اختياري)", value=row["birth_place"] or "")
                    e_address = b.text_input("العنوان (اختياري)", value=row["address"] or "")
                    with st.expander("تفاصيل اختيارية"):
                        e_medical = st.text_area("ملاحظات صحية", value=row["medical_details"] or "")
                        e_allergies = st.text_area("الحساسية", value=row["allergies"] or "")
                        e_notes = st.text_area("ملاحظات عامة", value=row["general_notes"] or "")
                        e_pickups = st.text_area("المخولون باستلام الطفل",
                            value=_format_pickups(row["authorized_pickups"]),
                            help="كل شخص في سطر: الاسم | رقم الهاتف")
                    b1, b2 = st.columns(2)
                    save = b1.form_submit_button("💾 حفظ التعديلات", type="primary",
                                                 use_container_width=True)
                    delete = b2.form_submit_button("🗑️ حذف الطالب",
                                                   use_container_width=True)
                    if save:
                        try:
                            people = _parse_pickups(e_pickups)
                            if not e_name.strip() or len(e_name.strip()) > 100:
                                raise ValueError("يرجى كتابة اسم طفل صحيح.")
                            import json
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE students SET full_name=%s, birth_date=%s,
                                        gender=%s, birth_place=%s, address=%s,
                                        medical_details=%s, allergies=%s, general_notes=%s,
                                        authorized_pickups=%s::jsonb WHERE student_id=%s
                                """, (e_name.strip(), e_birth, e_gender,
                                      e_place.strip() or None, e_address.strip() or None,
                                      e_medical.strip() or None, e_allergies.strip() or None,
                                      e_notes.strip() or None,
                                      json.dumps(people, ensure_ascii=False), sid))
                            st.success("تم حفظ التعديلات.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                        except Exception:
                            conn.rollback()
                            st.error("تعذّر حفظ التعديلات؛ يرجى المحاولة مرة أخرى.")
                    if delete:
                        try:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM students WHERE student_id=%s", (sid,))
                            st.warning("تم حذف الطالب.")
                            st.rerun()
                        except Exception:
                            conn.rollback()
                            st.error("تعذّر الحذف؛ يرجى مراجعة ارتباطات الطفل.")
