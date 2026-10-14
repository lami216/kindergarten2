"""Name-only departments and repeatable individual or bulk child transfers."""
import streamlit as st
import ui
import school_departments as D
from student_search import filter_children


def render(conn):
    ui.section_header('🏷️','الأقسام','أضف أقسام الروضة وانقل الأطفال بينها')
    notice=st.session_state.pop('department_notice',None)
    if notice:
        st.success(notice)
    with st.form('add_department',clear_on_submit=True):
        name=st.text_input('اسم القسم *',max_chars=100,placeholder='مثال: قسم الورود')
        if st.form_submit_button('إضافة القسم',type='primary'):
            try:
                D.create(name)
                st.session_state['department_notice']='تمت إضافة القسم.'
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error('تعذرت إضافة القسم؛ حاول مجددًا.')
    departments=ui.df(conn,'''SELECT d.department_id,d.name,COUNT(s.student_id) AS children
        FROM school_departments d LEFT JOIN student_departments m ON m.department_id=d.department_id
        LEFT JOIN students s ON s.student_id=m.student_id AND s.archived_at IS NULL
        WHERE d.archived_at IS NULL GROUP BY d.department_id ORDER BY d.name''')
    if departments.empty:
        ui.empty_state('أضف أول قسم، ثم اختر الأطفال لإلحاقهم به.')
        return
    ui.dataframe(departments.rename(columns={'name':'القسم','children':'عدد الأطفال'})[['القسم','عدد الأطفال']],hide_index=True,use_container_width=True)
    if st.button('تعديل أو حذف قسم',key='department_edit_open'):
        st.session_state['records_target']='school_departments'
        st.session_state['current_page']='records'
        st.rerun()
    children=ui.df(conn,'''SELECT s.student_id,s.full_name,p.father_name,p.mother_name,
        p.father_mobile,p.mother_mobile,m.department_id,COALESCE(d.name,'بدون قسم') AS department_name
        FROM students s LEFT JOIN parents p ON p.father_id=s.father_id
        LEFT JOIN student_departments m ON m.student_id=s.student_id
        LEFT JOIN school_departments d ON d.department_id=m.department_id
        WHERE s.archived_at IS NULL ORDER BY s.full_name,s.student_id''')
    if children.empty:
        ui.empty_state('لا يوجد أطفال حاليون لتوزيعهم.')
        return
    st.markdown('##### توزيع الأطفال ونقلهم')
    names=dict(zip(departments.department_id,departments.name))
    source=st.selectbox('عرض الأطفال',[-1,0]+list(names),format_func=lambda x:'كل الأطفال' if x==-1 else 'بدون قسم' if x==0 else names[x],key='department_source')
    shown=children if source==-1 else children[children.department_id.isna()] if source==0 else children[children.department_id==source]
    term=st.text_input('بحث باسم الطفل أو هاتف الأب أو الأم',key='department_search')
    shown=filter_children(shown,term)
    ui.dataframe(shown.rename(columns={'full_name':'الطفل','department_name':'القسم'})[['الطفل','القسم']],hide_index=True,use_container_width=True)
    labels={r.student_id:f'{r.full_name} — {r.department_name}' for r in shown.itertuples()}
    version=st.session_state.get('department_transfer_version',0)
    key=f'department_children_{version}'
    if key in st.session_state:
        st.session_state[key]=[s for s in st.session_state[key] if s in labels]
    selected=st.multiselect('اختر الأطفال لنقلهم',list(labels),format_func=labels.get,key=key)
    destination=st.selectbox('القسم الجديد',list(names),format_func=names.get,index=None,placeholder='اختر القسم...',key='department_destination')
    if st.button('نقل الأطفال',type='primary',disabled=not selected or destination is None,key='department_transfer'):
        try:
            changed=D.transfer(selected,int(destination),actor=st.session_state.get('auth_user'))
            st.session_state['department_notice']=f'تم نقل {changed} طفل.' if changed else 'الأطفال المحددون موجودون في هذا القسم بالفعل.'
            st.session_state['department_transfer_version']=version+1
            st.rerun()
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error('تعذر حفظ النقل؛ لم تُنقل المجموعة جزئيًا.')
