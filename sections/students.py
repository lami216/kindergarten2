"""Child + parent intake and student editing; academic enrollment remains separate."""
from datetime import date
import json
import uuid

import pandas as pd
import streamlit as st

import db
import monthly_finance as F
import student_debt as D
from sections.monthly_payments import financial_panel, actor
import helpers as H
import ui


ADD_KEYS = ("kid_name", "kid_birth", "kid_gender", "kid_place", "kid_address",
            "kid_father_name", "kid_father_phone", "kid_mother_name",
            "kid_mother_phone", "kid_email", "kid_health", "kid_allergy",
            "kid_notes", "kid_use_existing", "kid_existing_family",
            "kid_finance_mode", "kid_initial_registration", "kid_initial_gilet",
            "kid_initial_amount", "kid_finance_start")
ADD_KEYS += ('kid_photo',)


def _text(value):
    """No pandas NA/NaN/None representation may enter a text widget."""
    if value is None:
        return ""
    if isinstance(value, str):
        return "" if value.strip().lower() in ("nan", "none", "<na>") else value
    if not isinstance(value, (list, tuple, dict)):
        try:
            if bool(pd.isna(value)):
                return ""
        except (TypeError, ValueError):
            pass
    return str(value)


def _pickups_from_db(value):
    if isinstance(value, list):
        return [{"name": _text(v.get("name")), "phone": _text(v.get("phone"))}
                for v in value if isinstance(v, dict)]
    return []


def _validate_pickups(rows):
    """Optional structured inputs; reject half-filled rows without discarding them."""
    clean = []
    for item in rows:
        name, phone = _text(item["name"]).strip(), _text(item["phone"]).strip()
        if not name and not phone:
            continue
        if not name or not phone:
            raise ValueError("يرجى إدخال اسم ورقم هاتف لكل شخص مخوّل بالاستلام.")
        if len(name) > 100 or len(phone) > 20:
            raise ValueError("اسم المخوّل أو رقم هاتفه أطول من المسموح.")
        clean.append({"name": name, "phone": phone})
    return clean


def _form_key(base):
    version = st.session_state.get("kid_form_version", 0)
    return base if not version else f"{base}_v{version}"


def _reset_after_success():
    """Clear and rotate widgets only while building the next visible form.

    Rotating form/widget identities ensures the browser cannot carry old values
    across a successful save, even if it queues a second click while rerunning.
    Validation or database errors never trigger this path.
    """
    if st.session_state.pop("kid_saved_reset", False):
        previous = st.session_state.get("kid_form_version", 0)
        suffix = "" if previous == 0 else f"_v{previous}"
        for base in ADD_KEYS:
            st.session_state.pop(base + suffix, None)
        prefix = f"kid_add_{previous}"
        for row_id in st.session_state.pop(prefix + "_pickup_ids", []):
            for part in ("name", "phone"):
                st.session_state.pop(f"{prefix}_pickup_{row_id}_{part}", None)
        st.session_state["kid_form_version"] = previous + 1
        st.session_state["kid_request_token"] = str(uuid.uuid4())


def _pickup_editor(owner, initial=None, *, in_form=True):
    """Render ordinary paired widgets and add/remove submit buttons in a form."""
    list_key = owner + "_pickup_ids"
    if list_key not in st.session_state:
        row_ids = []
        for item in initial or []:
            row_id = uuid.uuid4().hex[:12]
            row_ids.append(row_id)
            st.session_state[f"{owner}_pickup_{row_id}_name"] = _text(item.get("name"))
            st.session_state[f"{owner}_pickup_{row_id}_phone"] = _text(item.get("phone"))
        st.session_state[list_key] = row_ids

    people = []
    with st.expander("المخولون باستلام الطفل (اختياري)"):
        st.markdown(
            '<span class="pickup-style-anchor" aria-hidden="true" style="display:none"></span>',
            unsafe_allow_html=True,
        )
        for row_id in list(st.session_state[list_key]):
            a, b, c = st.columns([4, 4, 2])
            name = a.text_input("الاسم", key=f"{owner}_pickup_{row_id}_name")
            phone = b.text_input("رقم الهاتف", key=f"{owner}_pickup_{row_id}_phone")
            remove = (c.form_submit_button if in_form else c.button)("إزالة",
                        key=f"{owner}_pickup_{row_id}_remove",
                        use_container_width=True)
            if remove:
                st.session_state[list_key].remove(row_id)
                st.rerun()
            people.append({"name": name, "phone": phone})
        add = (st.form_submit_button if in_form else st.button)("＋ إضافة شخص مخوّل",
                  key=owner + "_pickup_add")
        if add:
            st.session_state[list_key].append(uuid.uuid4().hex[:12])
            st.rerun()
    return people


def _parent_fields(family):
    """Keep these widgets mounted even while a saved family is selected."""
    a, b = st.columns(2)
    family["father_name"] = a.text_input("اسم الأب",
        key=_form_key("kid_father_name")).strip()
    family["father_mobile"] = a.text_input("هاتف الأب",
        key=_form_key("kid_father_phone")).strip()
    family["mother_name"] = b.text_input("اسم الأم",
        key=_form_key("kid_mother_name")).strip()
    family["mother_mobile"] = b.text_input("هاتف الأم",
        key=_form_key("kid_mother_phone")).strip()
    family["contact_email"] = st.text_input("بريد التواصل (اختياري)",
        key=_form_key("kid_email")).strip()


def _medical_flag(old_details, old_flag, new_details, clear_legacy=False):
    """New/removed notes update the flag; note-less legacy flags are protected."""
    if _text(new_details).strip():
        return 1
    if _text(old_details).strip():
        return 0
    return int(bool(old_flag) and not clear_legacy)


def render_intake(conn,parents=None,family_choices=None):
    import access_control as A
    _reset_after_success()
    st.session_state.setdefault('kid_form_version',0)
    st.session_state.setdefault('kid_request_token',str(uuid.uuid4()))
    if parents is None:
        parents=ui.df(conn,"SELECT father_id,father_name,mother_name,father_mobile,mother_mobile FROM parents WHERE archived_at IS NULL ORDER BY father_id") if A.can('students.view') else pd.DataFrame()
    if family_choices is None:
        family_choices=[]
        for _,row in parents.iterrows():
            names=' / '.join(filter(None,(_text(row['father_name']),_text(row['mother_name']))))
            phones=' / '.join(filter(None,(_text(row['father_mobile']),_text(row['mother_mobile']))))
            family_choices.append((row['father_id'],names+' — '+phones))
    if st.session_state.get("kid_last_saved"):
        st.success(st.session_state["kid_last_saved"])
    existing = False
    if family_choices:
        existing = st.checkbox("اختيار ولي أمر موجود", key=_form_key("kid_use_existing"))
    version = st.session_state["kid_form_version"]
    with st.container(border=True):
        ui.form_section_title("١ · بيانات الطفل")
        a, b = st.columns(2)
        name = a.text_input("اسم الطفل *", key=_form_key("kid_name")).strip()
        birth = b.date_input("تاريخ الميلاد *", value=date(2022, 1, 1),
                   min_value=date(1990, 1, 1), max_value=F.today(),
                   key=_form_key("kid_birth"))
        a, b = st.columns(2)
        gender = a.selectbox("الجنس *", H.GENDERS, key=_form_key("kid_gender"))
        place = b.text_input("مكان الميلاد (اختياري)", key=_form_key("kid_place"))
        address = st.text_input("العنوان (اختياري)", key=_form_key("kid_address"))
        with st.expander('📷 صورة الطالب (اختياري)'):
            photo = st.file_uploader('صورة الطفل',type=['jpg','jpeg','png','webp'],max_upload_size=5,
                key=_form_key('kid_photo'),help='حتى 5 ميغابايت. يمكنك إضافتها أو تغييرها لاحقًا من ملف الطالب.')
        family = dict(father_name="", father_mobile="", mother_name="",
                      mother_mobile="", contact_email="")
        parent_id = None
        ui.form_section_title("٢ · بيانات الأهل")
        if existing:
            selected = st.selectbox("ولي الأمر الموجود", family_choices,
                format_func=lambda option: option[1],
                key=_form_key("kid_existing_family"))
            parent_id = selected[0]
            st.caption("بيانات الأهل المشتركة تُعدّل من صفحة أولياء الأمور.")
            # Streamlit destroys an unrendered widget's state on rerun.
            # Keep fields mounted in a closed expander when switching modes.
            with st.expander("بيانات أهل جديدة محفوظة (اختياري)"):
                _parent_fields(family)
        else:
            _parent_fields(family)

        with st.expander("تفاصيل اختيارية"):
            medical = st.text_area("ملاحظات صحية", key=_form_key("kid_health"))
            allergy = st.text_area("الحساسية", key=_form_key("kid_allergy"))
            notes = st.text_area("ملاحظات عامة", key=_form_key("kid_notes"))

        pickups = _pickup_editor(f"kid_add_{version}", in_form=False)

        ui.form_section_title("٣ · الرسوم والدفع")
        # Unlike fields inside st.form, native segmented and amount controls
        # trigger immediate reruns and therefore a live receipt breakdown.
        modes=['بلا دفعة']+(['دفع'] if A.can('payments.create') else [])+(['معفي'] if A.can('accounts.edit') else [])
        mode = st.segmented_control("طريقة الرسوم", modes,
            selection_mode="single", default="بلا دفعة", key=_form_key("kid_finance_mode"),
            help="يمكن تسجيل الدفعة لاحقًا من صفحة الدفعات.")
        tariff = F.prices(conn)
        start_date = F.today()
        with st.expander("تاريخ بدء التسجيل"):
            start_date = st.date_input("تاريخ بدء الاشتراك", value=F.today(),
                key=_form_key("kid_finance_start"))
        reg_chosen = garment_chosen = False
        initial_amount = 0
        if mode == "معفي":
            st.caption("يشمل الإعفاء التسجيل والجيليه والشهرية، دون قبض أي مبلغ.")
        elif mode == "دفع":
            if tariff:
                reg_price, garment_price = int(tariff["registration"]), int(tariff["gilet"])
                reg_chosen = st.checkbox(f"رسوم التسجيل — {reg_price:,} أوقية قديمة",
                    key=_form_key("kid_initial_registration"))
                garment_chosen = st.checkbox(f"الجيليه — {garment_price:,} أوقية قديمة",
                    key=_form_key("kid_initial_gilet"))
            else:
                st.warning("لم تُضبط الأسعار بعد. افتح إعدادات الرسوم في صفحة الدفعات.")
            initial_amount = st.number_input("المبلغ المدفوع", min_value=0,
                max_value=F.MAX_AMOUNT, step=1, value=0,
                key=_form_key("kid_initial_amount"))
            if tariff:
                try:
                    F.preview(int(initial_amount),reg_chosen,garment_chosen,tariff)
                except ValueError as exc:
                    st.warning(str(exc))
        else:
            st.caption("يمكنك تسجيل الدفعة لاحقًا. رسوم التسجيل تبقى مستحقة.")

        submitted = st.button("💾 حفظ بيانات الطفل والأهل",
                              type="primary", use_container_width=True,
                              key=f"kid_save_final_{version}")
        if submitted:
            # Remove the preceding success notice only for a new valid attempt.
            try:
                if not name:
                    raise ValueError("يرجى كتابة اسم الطفل.")
                # Child validation applies in either family-selection mode.
                if len(name) > 100 or len(place.strip()) > 100:
                    raise ValueError("اسم الطفل أو مكان الميلاد طويل جداً.")
                # Draft details of a *new* family are preserved when switching
                # to an existing guardian, but must not block that child save.
                if parent_id is None:
                    if any(len(v) > 100 for v in (
                            family["father_name"], family["mother_name"])):
                        raise ValueError("أحد أسماء الأهل أطول من المسموح.")
                    if any(len(v) > 20 for v in (
                            family["father_mobile"], family["mother_mobile"])):
                        raise ValueError("رقم الهاتف أطول من المسموح.")
                    if len(family["contact_email"]) > 254 or (
                        family["contact_email"] and ("@" not in family["contact_email"]
                                                     or " " in family["contact_email"])):
                        raise ValueError("يرجى كتابة بريد تواصل صحيح.")
                child = dict(full_name=name, birth_date=birth, gender=gender,
                    birth_place=place, address=address, medical_details=medical,
                    allergies=allergy, general_notes=notes,
                    authorized_pickups=_validate_pickups(pickups))
                if mode == "دفع" and not initial_amount:
                    raise ValueError("أدخل المبلغ المدفوع أو اترك الخيار بلا دفع.")
                # This preview does not authorize the charge; PostgreSQL
                # re-reads current tariffs and allocates in the transaction.
                if mode == "دفع" and tariff:
                    F.preview(int(initial_amount),reg_chosen,garment_chosen,tariff)
                if parent_id:
                    stored_parent = parents.loc[parents["father_id"] == parent_id].iloc[0]
                    payer = (_text(stored_parent["father_name"]).strip() or
                             _text(stored_parent["mother_name"]).strip() or "ولي الأمر")
                else:
                    payer = family["father_name"] or family["mother_name"]
                finance = {"mode": "exempt" if mode=="معفي" else "regular",
                           "start_date": str(start_date),
                           "registration": bool(reg_chosen) if mode=="دفع" else False,
                           "gilet": bool(garment_chosen) if mode=="دفع" else False,
                           "cash": int(initial_amount) if mode=="دفع" else 0,
                           "payer": payer}
                _, created = db.save_child_with_family(
                    child, family, parent_id, st.session_state["kid_request_token"],
                    finance=finance, actor=actor(), photo=photo.getvalue() if photo else None)
                st.session_state["kid_last_saved"] = (
                    "✅ تم حفظ الطفل والأهل بنجاح. النموذج فارغ لإدخال طفل آخر."
                    if created else
                    "✅ تم حفظ هذا الطلب سابقاً دون إنشاء طفل أو أسرة مكررين.")
                st.session_state["kid_saved_reset"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("تعذّر حفظ البيانات. لم تُحفظ الأسرة جزئياً؛ راجع البيانات وحاول مجدداً.")



def render(conn):
    import access_control as A
    _reset_after_success()
    if "kid_form_version" not in st.session_state:
        st.session_state["kid_form_version"] = 0
    if "kid_request_token" not in st.session_state:
        st.session_state["kid_request_token"] = str(uuid.uuid4())

    ui.section_header("🎒", "إدارة الطلاب", "إضافة وتعديل ومتابعة بيانات الأطفال")
    tabs = st.tabs((["➕ إضافة طالب جديد"] if A.can('students.create') else [])+["📋 عرض / تعديل / حذف"],
        key='student_tabs',on_change='rerun')
    parents = ui.df(conn, """
        SELECT father_id, father_name, mother_name, father_mobile, mother_mobile
        FROM parents WHERE archived_at IS NULL ORDER BY COALESCE(father_name, mother_name)
    """)
    family_choices = []
    for _, row in parents.iterrows():
        names = " / ".join(x for x in (_text(row["father_name"]), _text(row["mother_name"])) if x)
        phones = " / ".join(x for x in (_text(row["father_mobile"]), _text(row["mother_mobile"])) if x)
        family_choices.append((row["father_id"], f"{names} — {phones}"))

    if A.can('students.create'):
        with tabs[0]:
            render_intake(conn,parents,family_choices)

    with tabs[-1]:
        students = ui.df(conn, """
            SELECT s.student_id, s.full_name, s.birth_date, s.gender, s.birth_place,
                   s.address, s.medical_details, s.has_medical_condition,
                   s.allergies, s.general_notes, s.authorized_pickups, s.father_id,
                   s.archived_at,COALESCE(d.name,'بدون قسم') AS department_name,
                   COALESCE(p.father_name, p.mother_name) AS parent_name,
                    p.father_mobile,p.mother_mobile,p.father_name,p.mother_name,p.contact_email
            FROM students s JOIN parents p ON p.father_id=s.father_id
            LEFT JOIN student_departments m ON m.student_id=s.student_id
            LEFT JOIN school_departments d ON d.department_id=m.department_id
            ORDER BY s.created_at DESC
        """)
        if students.empty:
            ui.empty_state("لا يوجد طلاب مسجلون بعد.")
            return
        show_archived = st.checkbox("إظهار ملفات الأطفال المؤرشفين (السجل المالي محفوظ)",
                                    key="show_archived_student_history")
        if not show_archived:
            students=students[students["archived_at"].isna()].copy()
        if students.empty:
            ui.empty_state("لا توجد ملفات في هذا العرض.")
            return
        search = st.text_input("🔍 ابحث باسم الطفل أو ولي الأمر أو رقم الهاتف").strip()
        matches=(
            students["full_name"].fillna("").astype(str).str.contains(
                search,case=False,regex=False) |
            students["parent_name"].fillna("").astype(str).str.contains(
                search,case=False,regex=False) |
            students["father_mobile"].fillna("").astype(str).str.contains(
                search,case=False,regex=False) |
            students["mother_mobile"].fillna("").astype(str).str.contains(
                search,case=False,regex=False)
        ) if search else None
        shown=students[matches] if search else students
        display = shown.copy()
        display["العمر"] = display["birth_date"].apply(H.calculate_age)
        ui.dataframe(display.rename(columns={
            "full_name": "الاسم", "birth_date": "تاريخ الميلاد",
            "gender": "الجنس", "parent_name": "ولي الأمر", "department_name": "القسم"})[
            ["الاسم", "العمر", "تاريخ الميلاد", "الجنس", "ولي الأمر", "القسم"]],
            use_container_width=True, hide_index=True)
        st.markdown("---")
        st.markdown("##### فتح ملف طالب")
        options = [(row["student_id"], row["full_name"]) for _, row in shown.iterrows()]
        duplicate_names=set(shown['full_name'][shown['full_name'].duplicated(keep=False)])
        chosen = st.selectbox("اختر الطفل", options,
            format_func=lambda x:f'{x[1]} · {x[0]}' if x[1] in duplicate_names else x[1], index=None, placeholder="ابحث عن طفل...",
            key="student_select_edit")
        if chosen:
            sid = chosen[0]
            row = students[students["student_id"] == sid].iloc[0]
            from sections import student_profile as profile
            photo = profile.header(conn,row)
            if A.can('payments.view'):
                with st.container(border=True):
                    st.markdown('##### 💵 الحساب المالي')
                    financial_panel(conn, sid, payment=pd.isna(row['archived_at']) and A.can('payments.create'),
                        profile=True, student_name=row['full_name'])
            profile.details(row)
            profile.photo_editor(conn,row,photo)
            if pd.notna(row["archived_at"]):
                st.warning("الطالب مؤرشف؛ سجله وحساباته باقية للمراجعة.")
                archived_finance=F.projection(conn,sid,materialize=False) if A.can('payments.view') else None
                if archived_finance and archived_finance["due_now"]:
                    st.error(f"دين أعيد فتحه بعد تصحيح أو إلغاء قبض سابق: "
                             f"{archived_finance['due_now']:,} أوقية قديمة. "
                             "لم تُستأنف رسوم شهرية جديدة.")
                return
            if not (A.can('students.edit') or A.can('students.delete')):
                return
            with st.expander(f"⚙️ تعديل بيانات: {_text(row['full_name'])}", expanded=False):
                snapshot,snapshot_key=ui.edit_snapshot(conn,'students',sid,scope='student_'+sid,widget_prefix=f'edit_{sid}_')
                row=pd.Series(snapshot)
                with st.form(f"edit_student_form_{sid}"):
                    if A.can('students.edit'):
                        a, b, c = st.columns(3)
                        e_name = a.text_input("اسم الطفل", value=_text(row["full_name"]),
                                              key=f"edit_{sid}_name")
                        old_date = pd.to_datetime(row["birth_date"], errors="coerce")
                        e_birth = b.date_input("تاريخ الميلاد",
                            value=old_date.date() if pd.notna(old_date) else date(2022, 1, 1),
                            min_value=date(1990, 1, 1), max_value=F.today(),
                            key=f"edit_{sid}_birth")
                        original_gender = _text(row["gender"])
                        e_gender = c.selectbox("الجنس", H.GENDERS,
                            index=H.GENDERS.index(original_gender) if original_gender in H.GENDERS else 0,
                            key=f"edit_{sid}_gender")
                        a, b = st.columns(2)
                        e_place = a.text_input("مكان الميلاد (اختياري)",
                                     value=_text(row["birth_place"]), key=f"edit_{sid}_place")
                        e_address = b.text_input("العنوان (اختياري)",
                                     value=_text(row["address"]), key=f"edit_{sid}_address")
                        old_medical = _text(row["medical_details"])
                        old_flag = bool(row["has_medical_condition"]) if pd.notna(row["has_medical_condition"]) else False
                        with st.expander("تفاصيل اختيارية"):
                            e_medical = st.text_area("ملاحظات صحية", value=old_medical,
                                                   key=f"edit_{sid}_health")
                            e_allergy = st.text_area("الحساسية", value=_text(row["allergies"]),
                                                   key=f"edit_{sid}_allergy")
                            e_notes = st.text_area("ملاحظات عامة", value=_text(row["general_notes"]),
                                                 key=f"edit_{sid}_notes")
                            clear_legacy = False
                            if old_flag and not old_medical.strip():
                                st.caption("هذا السجل يحمل علامة صحية تاريخية دون ملاحظات.")
                                clear_legacy = st.checkbox("إزالة علامة الحالة الصحية القديمة",
                                                           key=f"edit_{sid}_clear_health")
                        pickups = _pickup_editor(f"edit_{sid}",
                                                  initial=_pickups_from_db(row["authorized_pickups"]))
                    a, b = st.columns(2)
                    save = a.form_submit_button("💾 حفظ التعديلات", type="primary",
                                                use_container_width=True) if A.can('students.edit') else False
                    delete = b.form_submit_button("🗑️ حذف الطالب",
                                                   use_container_width=True) if A.can('students.delete') else False
                    if save:
                        try:
                            people = _validate_pickups(pickups)
                            if not e_name.strip() or len(e_name.strip()) > 100:
                                raise ValueError("يرجى كتابة اسم طفل صحيح.")
                            if len(e_place.strip()) > 100:
                                raise ValueError("مكان الميلاد أطول من المسموح.")
                            import records as R
                            R.edit('students',sid,dict(full_name=e_name,birth_date=e_birth,
                                gender=e_gender,birth_place=e_place,address=e_address,
                                medical_details=e_medical,allergies=e_allergy,general_notes=e_notes,
                                authorized_pickups=people),actor=st.session_state.get('auth_user'),
                                reason='تعديل بيانات الطفل من ملفه',expected=R.revision(snapshot),
                                clear_legacy_medical=clear_legacy)
                            st.session_state.pop(snapshot_key,None)
                            st.success("تم حفظ التعديلات.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                        except Exception:
                            conn.rollback()
                            st.error("تعذّر حفظ التعديلات؛ يرجى المحاولة مرة أخرى.")
                    if delete:
                        try:
                            D.archive_student(sid,actor=st.session_state.get("auth_user","مديرة الروضة"))
                            st.session_state.pop("student_pending_debt",None)
                            st.success("أُرشف الطالب؛ جميع الحسابات والوصولات محفوظة.")
                            st.rerun()
                        except ValueError as error:
                            st.session_state["student_pending_debt"]=sid
                            st.error(str(error))
                        except Exception:
                            st.error("تعذّر الأرشفة؛ لم تتغير البيانات.")
                if st.session_state.get("student_pending_debt")==sid:
                    remaining=D.waiver_preview(conn,sid)
                    due=int(remaining["due_now"]) if remaining else 0
                    completed_waiver=st.session_state.get(f"student_waiver_success_{sid}")
                    if completed_waiver and not due:
                        st.success(f"أُلغي دين {completed_waiver:,} دون إنشاء قبض. يمكن الآن أرشفة الطالب.")
                    if due:
                        st.error(f"لا يمكن حذف الطالب؛ عليه مبلغ {due:,} أوقية قديمة.")
                        st.caption("القرار بيد المديرة: قبض فعلي أو إلغاء دين موثّق. لا يصدر وصل عند إلغاء الدين.")
                        b1,b2=st.columns(2)
                        if b1.button("تسجيل دفعة",key=f"student_pay_choice_{sid}"):
                            st.session_state[f"student_resolve_{sid}"]="pay"
                        if b2.button("إلغاء الدين",key=f"student_waive_choice_{sid}"):
                            st.session_state[f"student_resolve_{sid}"]="waive"
                        mode=st.session_state.get(f"student_resolve_{sid}")
                        if mode=="pay":
                            st.caption("الدفعة الشهرية بالمبلغ فقط متاحة في الحساب أعلاه.")
                            unsettled=[(kind,row) for kind,row in remaining["fees"].items()
                               if row["price"]-row["paid"]-row.get("waived",0)>0]
                            if unsettled:
                                fee_map={kind:("رسوم التسجيل" if kind=="registration" else "الجيليه")
                                    +f" — {info['price']-info['paid']-info.get('waived',0):,} أوقية قديمة"
                                    for kind,info in unsettled}
                                with st.form(f"student_item_collect_{sid}"):
                                    kind=st.selectbox("رسم مستحق للتحصيل النقدي",list(fee_map),
                                        format_func=lambda k:fee_map[k])
                                    paid=st.form_submit_button("تحصيل المبلغ المحدد وإصدار وصل")
                                if paid:
                                    try:
                                        token_key=f"student_item_token_{sid}"
                                        st.session_state.setdefault(token_key,str(uuid.uuid4()))
                                        receipt_id,_=D.pay_unpaid_fee(sid,kind,
                                          actor=st.session_state.get("auth_user","مديرة الروضة"),
                                          token=st.session_state[token_key])
                                        st.session_state[token_key]=str(uuid.uuid4())
                                        st.success(f"تم قبض المبلغ فعلياً؛ الوصل #{receipt_id}.")
                                        st.rerun()
                                    except ValueError as error:
                                        st.error(str(error))
                                    except Exception:
                                        st.error("تعذّر تسجيل القبض؛ لم يصدر وصل.")
                        elif mode=="waive":
                            with st.form(f"student_waive_{sid}"):
                                st.write(f"مجموع الدين الذي سيُلغى دون قبض: **{due:,} أوقية قديمة**")
                                reason=st.text_area("سبب إلغاء الدين *")
                                confirm=st.checkbox("أؤكد إلغاء الدين دون قبض أي مبلغ")
                                apply=st.form_submit_button("تأكيد قرار إلغاء الدين")
                            if apply:
                                try:
                                    key=f"student_waiver_token_{sid}"
                                    st.session_state.setdefault(key,str(uuid.uuid4()))
                                    written,_=D.waive_debt(sid,reason,confirm,
                                        actor=st.session_state.get("auth_user","مديرة الروضة"),
                                        token=st.session_state[key])
                                    st.session_state[key]=str(uuid.uuid4())
                                    st.session_state[f"student_waiver_success_{sid}"]=written
                                    st.rerun()
                                except ValueError as error:
                                    st.error(str(error))
                                except Exception:
                                    st.error("تعذّر إلغاء الدين؛ بقي الدين محفوظاً.")
