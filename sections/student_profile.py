"""Readable private student file, shared by manager and permitted workers."""
import base64
from html import escape
import pandas as pd
import streamlit as st
import access_control as A
import helpers as H
import student_photos as P
import ui


def text(value):
    if value is None: return ''
    if isinstance(value, str): return value.strip()
    return '' if pd.isna(value) else str(value)


def styles():
    st.markdown('''<style>
    .student-file-hero{display:flex;align-items:center;gap:22px;padding:24px;
        border:1px solid var(--card-border);border-radius:22px;background:var(--card-bg);margin:12px 0 20px}
    .student-file-photo{width:112px;height:112px;flex:0 0 112px;object-fit:cover;border-radius:24px;
        border:3px solid var(--card-bg);box-shadow:0 0 0 1px var(--card-border)}
    .student-file-initial{display:grid;place-items:center;background:var(--primary-light);color:var(--primary-dark);
        font-size:42px;font-weight:700}
    .student-file-hero h2{margin:0 0 8px!important;font-size:27px!important;color:var(--text-main)!important;overflow-wrap:anywhere}
    .student-file-hero p{margin:4px 0;color:var(--text-muted);font-size:14px}
    .student-file-badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
    .student-file-badges span{background:var(--bg);border:1px solid var(--card-border);border-radius:9px;
        padding:5px 10px;color:var(--text-main);font-size:13px}
    .student-file-details{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:4px 0}
    .student-file-details small{display:block;color:var(--text-muted);margin-bottom:4px}
    .student-file-details p{margin:0;color:var(--text-main);white-space:pre-wrap;overflow-wrap:anywhere}
    @media(max-width:600px){.student-file-hero{gap:14px;padding:18px}.student-file-photo{width:82px;height:82px;flex-basis:82px;border-radius:18px}
        .student-file-hero h2{font-size:21px!important}.student-file-details{gap:14px}}
    </style>''', unsafe_allow_html=True)


def header(conn, row):
    styles()
    photo = P.get(conn, row['student_id'])
    name = text(row['full_name'])
    if photo['image_data'] is not None:
        src = base64.b64encode(bytes(photo['image_data'])).decode('ascii')
        portrait = f'<img class="student-file-photo" src="data:image/jpeg;base64,{src}" alt="صورة {escape(name,quote=True)}">'
    else:
        portrait = f'<span class="student-file-photo student-file-initial" role="img" aria-label="لم تضف صورة للطالب">{escape(name[:1] or "؟")}</span>'
    archived = bool(text(row.get('archived_at')))
    badges = [text(row.get('department_name')) or 'بدون قسم', 'مؤرشف' if archived else 'ملف نشط']
    age = H.calculate_age(row.get('birth_date')) if text(row.get('birth_date')) else 'غير مسجل'
    st.markdown(f'''<div class="student-file-hero">{portrait}<div><p>ملف الطالب</p>
        <h2>{escape(name)}</h2><p>{escape(text(row.get('gender')) or 'الجنس غير مسجل')} · العمر: {escape(str(age))}</p>
        <div class="student-file-badges">{''.join('<span>'+escape(b)+'</span>' for b in badges)}</div></div></div>''',unsafe_allow_html=True)
    # Keep the keyed editor at one delta path when feedback appears/disappears.
    # Moving it between slots can leave an old tracked expander in the browser.
    with st.container(key='student_file_feedback_'+row['student_id']):
        if notice := st.session_state.pop('student_photo_notice_'+row['student_id'], None): st.success(notice)
    return photo


def fields(values):
    st.markdown('<div class="student-file-details">'+''.join(
        f'<div><small>{escape(label)}</small><p>{escape(text(value) or "غير مسجل")}</p></div>'
        for label,value in values)+'</div>',unsafe_allow_html=True)


def details(row):
    child, family = st.columns(2)
    with child, st.container(border=True):
        st.markdown('##### 🎒 بيانات الطفل')
        fields([('تاريخ الميلاد',row.get('birth_date')),('مكان الميلاد',row.get('birth_place')),
                ('العنوان',row.get('address')),('الجنس',row.get('gender'))])
    with family, st.container(border=True):
        st.markdown('##### ☎️ التواصل مع الأسرة')
        fields([('اسم الأب',row.get('father_name')),('هاتف الأب',row.get('father_mobile')),
                ('اسم الأم',row.get('mother_name')),('هاتف الأم',row.get('mother_mobile')),
                *([('البريد الإلكتروني',row.get('contact_email'))] if text(row.get('contact_email')) else [])])
    if any(text(row.get(k)) for k in ('medical_details','allergies','general_notes')) or row.get('has_medical_condition'):
        with st.container(border=True):
            st.markdown('##### 🩺 الصحة والملاحظات')
            entries=[(label,row.get(k)) for k,label in [('medical_details','ملاحظات صحية'),('allergies','الحساسية'),('general_notes','ملاحظات عامة')]
                     if text(row.get(k))]
            if entries: fields(entries)
            if row.get('has_medical_condition') and not text(row.get('medical_details')):
                st.warning('توجد علامة صحية قديمة دون تفاصيل؛ راجع الأسرة لتوضيحها.')
    people=row.get('authorized_pickups')
    if isinstance(people,list) and people:
        with st.expander('🤝 المخولون باستلام الطفل'):
            ui.dataframe([{'الاسم':p.get('name',''),'الهاتف':p.get('phone','')} for p in people],hide_index=True,use_container_width=True)


def photo_editor(conn, row, fresh):
    if not A.can('students.edit'): return
    sid = row['student_id']
    base = 'student_photo_'+sid
    with st.expander('📷 صورة الطالب',key=base+'_editor',on_change='rerun'):
        st.caption('صورة اختيارية: JPG أو PNG أو WebP، حتى 5 ميغابايت. تُحفظ بحجم مصغّر دون بيانات الموقع أو الكاميرا.')
        st.session_state.setdefault(base+'_snapshot',fresh['revision'])
        expected = st.session_state[base+'_snapshot']
        if expected != fresh['revision']: st.warning('تغيّرت الصورة من مكان آخر. حدّث الصورة قبل الحفظ.')
        if st.button('تحديث الصورة',key=base+'_refresh'):
            st.session_state.pop(base+'_snapshot',None); st.rerun()
        upload = st.file_uploader('اختر صورة الطالب',type=['jpg','jpeg','png','webp'],
            max_upload_size=5,key=base+'_upload_'+str(expected))
        preview=st.empty()
        problem=st.empty()
        if upload:
            try:
                data=P.normalize(upload.getvalue())['image_data']
                src=base64.b64encode(data).decode('ascii')
                # Keep portraits out of Streamlit's separately served media URLs.
                preview.markdown(f'<div><img src="data:image/jpeg;base64,{src}" width="140" '
                    'style="border-radius:16px" alt="معاينة الصورة الجديدة">'
                    '<p>الصورة الجديدة قبل الحفظ</p></div>',unsafe_allow_html=True)
            except ValueError as error: problem.error(str(error))
        with st.form(base+'_form_'+str(expected)):
            reason=st.text_input('سبب تغيير الصورة *',max_chars=2000,key=base+'_reason_'+str(expected))
            a,b=st.columns(2)
            save=a.form_submit_button('حفظ الصورة',type='primary',disabled=bool(text(row.get('archived_at'))),key=base+'_save_'+str(expected))
            confirmed=False; remove=False
            if fresh['image_data'] is not None:
                confirmed=st.checkbox('أؤكد حذف صورة الطالب فقط، مع بقاء ملفه',key=base+'_confirm_'+str(expected))
                remove=b.form_submit_button('حذف الصورة',key=base+'_remove_'+str(expected))
        if save or remove:
            try:
                if remove and not confirmed: raise ValueError('أكد حذف الصورة أولًا.')
                P.save(sid,upload.getvalue() if upload else None,expected=expected,remove=remove,reason=reason)
                st.session_state.pop(base+'_snapshot',None)
                st.session_state['student_photo_notice_'+sid]='حُذفت الصورة؛ بقي ملف الطالب محفوظًا.' if remove else 'حُفظت صورة الطالب.'
                st.rerun()
            except ValueError as error: st.error(str(error))
            except Exception: st.error('تعذّر حفظ الصورة؛ لم يتغير ملف الطالب. حاول مجددًا.')
