"""One readable, searchable audit destination for all record types."""
import json
import streamlit as st
import ui
import records as R

ACTIONS={'created':'إضافة','updated':'تعديل','cancelled':'إلغاء / حذف','deleted':'حذف'}
FIELD_NAMES={
    'image_sha256':'بصمة الصورة','width':'عرض الصورة','height':'ارتفاع الصورة',
    'byte_size':'حجم الصورة بالبايت','mime_type':'نوع الصورة',
    'name':'اسم القسم','full_name':'الاسم','birth_date':'تاريخ الميلاد','gender':'الجنس',
    'father_name':'اسم الأب','father_mobile':'هاتف الأب','mother_name':'اسم الأم','mother_mobile':'هاتف الأم',
    'contact_email':'بريد التواصل','medical_details':'ملاحظات صحية','allergies':'الحساسية',
    'general_notes':'ملاحظات','authorized_pickups':'المخولون بالاستلام','father_id':'ولي الأمر',
    'address':'العنوان','birth_place':'مكان الميلاد','nationality':'الجنسية','id_type':'نوع الهوية',
    'national_id':'رقم هوية المعلمة','salary':'الراتب','mobile':'الهاتف','hire_date':'تاريخ التوظيف',
    'experience_years':'سنوات الخبرة','degree':'المؤهل','specialization':'التخصص',
    'class_type':'نوع الصف','section':'الشعبة','class_name':'اسم الصف','teacher_id':'المعلمة',
    'year_id':'السنة الدراسية','start_date':'تاريخ البداية','end_date':'تاريخ النهاية','cohort_name':'اسم الدفعة',
    'purchase_date':'تاريخ الشراء','item_name':'اسم الأصل','category':'الاسم / التصنيف','quantity':'الكمية',
    'unit_cost':'سعر الوحدة','total_cost':'إجمالي التكلفة','condition_status':'الحالة','notes':'ملاحظات',
    'expense_date':'تاريخ المصروف','amount':'المبلغ','amount_paid':'المدفوع','payee':'المستلم',
    'salary_month':'الشهر','base_salary':'الراتب الأساسي','bonus':'المكافأة','deductions':'الخصومات',
    'payment_date':'تاريخ الدفع','advance_date':'تاريخ السلفة','cash_amount':'المبلغ النقدي',
    'registration_date':'تاريخ التسجيل','annual_tuition':'الرسوم السنوية','student_id':'الطالب',
    'class_id':'الصف','status':'الحالة','registration':'رسوم التسجيل','gilet':'رسوم الجيليه','tuition':'الشهرية',
    'department_id':'القسم','archived_at':'وقت الحذف','cancelled_at':'وقت الإلغاء',
    'record_state':'حالة العملية','state':'حالة الوصل','received_on':'تاريخ القبض','payer':'الدافع',
    'emergency_contact_name':'اسم جهة الطوارئ','emergency_contact_phone':'هاتف الطوارئ',
    'mother_id':'هوية الأم','father_job':'عمل الأب','mother_job':'عمل الأم','mother_work_type':'نوع عمل الأم',
    'father_id_type':'نوع هوية الأب','mother_id_type':'نوع هوية الأم','landline':'الهاتف الثابت',
    'status_refugee':'حالة اللجوء','father_work_phone':'هاتف عمل الأب','mother_work_phone':'هاتف عمل الأم',
    'marital_status':'الحالة الاجتماعية',
    'effective_on':'تاريخ الإعفاء',
    'display_national_id':'رقم هوية المعلمة','display_year_id':'السنة الدراسية',
    'payment_method':'طريقة الدفع',
    'exempt_from':'بداية الإعفاء',
}


def render(conn):
    ui.section_header('🕘','سجل التغييرات','الإضافات والتعديلات والحذف، مع البيانات قبل العملية وبعدها')
    types=['']+list(R.LABELS)
    target=st.session_state.pop('history_target',None)
    if target:
        st.session_state['history_table']=target[0]
        st.session_state['history_record_key']=target[1]
    left,right=st.columns(2)
    table=left.selectbox('نوع السجل',types,format_func=lambda x:R.LABELS.get(x,'كل السجلات'),key='history_table')
    action=right.selectbox('العملية',['']+list(ACTIONS),format_func=lambda x:ACTIONS.get(x,'كل العمليات'))
    term=st.text_input('بحث بالاسم أو الرقم أو المسؤول أو السبب').strip()
    record_key=st.text_input('رقم سجل محدد (اختياري)',key='history_record_key').strip()
    query='SELECT * FROM record_changes WHERE true'
    params=[]
    if table: query+=' AND table_name=%s'; params.append(table)
    if action: query+=' AND action=%s'; params.append(action)
    if record_key: query+=' AND (record_key=%s OR old_key=%s)'; params.extend([record_key,record_key])
    if term:
        query+=" AND (COALESCE(before_state::text,'')||COALESCE(after_state::text,'')||actor||reason||record_key) ILIKE %s"
        params.append('%'+term+'%')
    query+=' ORDER BY change_id DESC LIMIT 200'
    with conn.cursor() as c:
        c.execute(query,params); rows=c.fetchall()
    if not rows: ui.empty_state('لا توجد تغييرات تطابق البحث.'); return
    st.caption('آخر 200 عملية مطابقة. يبدأ السجل من تفعيل هذه الميزة؛ لا تُختلق تغييرات قديمة.')
    for row in rows:
        before=row['before_state'] or {}; after=row['after_state'] or {}
        name=after.get('full_name') or after.get('name') or after.get('item_name') or after.get('category') or before.get('full_name') or before.get('name') or row['record_key']
        label=f"{ACTIONS[row['action']]} · {R.LABELS.get(row['table_name'],row['table_name'])} · {name}"
        with st.expander(label):
            st.caption(f"#{row['change_id']} · {row['happened_at'].strftime('%Y-%m-%d %H:%M')} · {row['actor']}")
            if row['reason']: st.write('السبب: '+row['reason'])
            fields=[k for k in set(before)|set(after) if before.get(k)!=after.get(k) and k in FIELD_NAMES]
            entries=[{'الحقل':FIELD_NAMES.get(k,k),'قبل':_display(before.get(k)),'بعد':_display(after.get(k))} for k in sorted(fields)]
            if entries: ui.dataframe(entries,hide_index=True,use_container_width=True)
            else: st.caption('حُفظ قرار العملية وبيانات السجل السابقة.')


def _display(value):
    if value is None: return '—'
    if isinstance(value,(list,dict)): return json.dumps(value,ensure_ascii=False)
    return str(value)
