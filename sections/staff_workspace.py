"""Scoped worker workspace; legacy manager pages never execute for a worker."""
import uuid
from datetime import date
import streamlit as st
import access_control as A
import ui
import auth
import monthly_finance as F
import expense_finance as E
import payroll_finance as P

TABLES={'students':['students'],'parents':['parents'],'departments':['school_departments'],
    'expenses':['expenses'],'assets':['assets'],'teachers':['teachers'],
    'salaries':['teacher_payments','teacher_advances'],'classes':['classes'],
    'years':['academic_years'],'accounts':['monthly_accounts','monthly_waivers','registrations'],
    'fees':['monthly_tariffs']}


def render(conn):
    profile=A.current()
    permitted={resource:label for resource,(label,actions) in A.RESOURCES.items()
        if any(A.can(resource+'.'+action) for action in actions)}
    with st.sidebar:
        ui.render_logo(width=80)
        st.write('**'+profile['employee_name']+'**')
        st.caption(profile['username'])
        for key,label in [('home','الرئيسية')]+list(permitted.items()):
            if st.button(label,key='staff_nav_'+key,use_container_width=True):
                st.session_state['current_page']=key; st.rerun()
        if st.button('تسجيل الخروج',key='staff_logout'): auth.logout()
    page=st.session_state.get('current_page','home')
    if page!='home' and page not in permitted:
        st.session_state['current_page']='home'; page='home'
    if page=='home':
        ui.section_header('🌿','أهلًا '+profile['employee_name'],'اختر العمل المطلوب من القائمة')
        if not permitted:
            st.info('حسابك مفعل، ولم يحدد المدير صلاحيات عمل له بعد.')
            return
        metrics=A.employee_metrics(conn,profile['user_id'])
        if A.can('students.create') or A.can('students.view'): st.metric('طلاب سجلتهم',metrics['students'])
        if A.can('expenses.create') or A.can('expenses.view'):
            st.metric('مصروفات سجلتها',metrics['expenses']['count'])
        return
    with conn.cursor() as c:
        # The route is checked against the live session, beyond sidebar hiding.
        available=[page+'.'+a for a in A.RESOURCES[page][1] if A.can(page+'.'+a)]
        A.require(c,available[0])
    ui.section_header('🌱',permitted[page],'الأعمال المتاحة لحسابك')
    if page=='reports':
        from sections import reports
        reports.render(conn); return
    if page=='history':
        from sections import change_history
        change_history.render(conn); return
    if page=='payments':
        from sections import monthly_payments as M
        accounts,receipts=st.tabs(['حساب الطفل','الوصولات'],key='staff_payment_tabs',on_change='rerun')
        with accounts: M.render_accounts(conn,allow_payment=A.can('payments.create'))
        with receipts: M.render_receipts(conn)
        return
    if A.can(page+'.create'):
        with st.expander('➕ إضافة جديدة',expanded=True):
            if page=='students':
                from sections.students import render_intake
                render_intake(conn)
            elif page=='expenses': _expense_intake()
            elif page=='departments': _department_intake()
            elif page=='salaries': _payroll_intake(conn)
    if page=='departments' and A.can('departments.edit'):
        _transfer(conn)
    if A.can(page+'.view') and page in TABLES:
        from sections.record_manager import render as records
        records(conn,allowed_tables=TABLES[page])


def _expense_intake():
    version=st.session_state.get('staff_expense_version',0)
    prefix=f'staff_expense_{version}'
    st.session_state.setdefault(prefix+'_token',str(uuid.uuid4()))
    with st.form(prefix):
        category=st.text_input('اسم المصروف *',max_chars=100,key=prefix+'_category')
        day=st.date_input('تاريخ المصروف',value=F.today(),max_value=F.today(),key=prefix+'_date')
        total=st.number_input('إجمالي المصروف',min_value=0.0,step=1.0,key=prefix+'_total')
        paid=st.number_input('المدفوع فعليًا',min_value=0.0,step=1.0,key=prefix+'_paid')
        payee=st.text_input('المستلم / المورد',max_chars=150,key=prefix+'_payee')
        method=st.selectbox('طريقة الدفع',['كاش','تحويل بنكي','شيك'],key=prefix+'_method')
        notes=st.text_area('ملاحظات',max_chars=10000,key=prefix+'_notes')
        save=st.form_submit_button('حفظ المصروف',type='primary')
    if save:
        try:
            E.create(category=category,amount_total=total,amount_paid=paid,expense_date=day,
                payee=payee,payment_method=method,notes=notes,token=st.session_state[prefix+'_token'])
            st.session_state['staff_expense_version']=version+1
            st.session_state['staff_notice']='حُفظ المصروف باسم حسابك.'
            st.rerun()
        except ValueError as error: st.error(str(error))
    if notice:=st.session_state.pop('staff_notice',None): st.success(notice)


def _department_intake():
    with st.form('staff_department_create'):
        name=st.text_input('اسم القسم *',max_chars=100)
        save=st.form_submit_button('إضافة القسم')
    if save:
        try:
            from school_departments import create
            create(name); st.success('أُضيف القسم.')
        except ValueError as error: st.error(str(error))


def _transfer(conn):
    from student_search import filter_children,child_labels
    from school_departments import transfer
    with st.expander('نقل الأطفال بين الأقسام'):
        children=ui.df(conn,'''SELECT s.student_id,s.full_name,p.father_name,p.mother_name,p.father_mobile,p.mother_mobile
            FROM students s LEFT JOIN parents p ON p.father_id=s.father_id WHERE s.archived_at IS NULL ORDER BY s.full_name''')
        term=st.text_input('بحث باسم الطفل أو هاتف أحد والديه',key='staff_transfer_search')
        children=filter_children(children,term); labels=child_labels(children)
        ids=st.multiselect('الأطفال المطلوب نقلهم',list(labels),format_func=labels.get,key='staff_transfer_children')
        departments=ui.df(conn,'SELECT department_id,name FROM school_departments WHERE archived_at IS NULL ORDER BY name')
        mapping=dict(zip(departments['department_id'],departments['name'])) if not departments.empty else {}
        dest=st.selectbox('القسم الجديد',list(mapping),index=None,format_func=mapping.get,key='staff_transfer_destination')
        if st.button('تأكيد النقل',disabled=not ids or dest is None):
            try:
                transfer(ids,dest,actor=st.session_state['auth_user']); st.success('حُفظ النقل.')
            except ValueError as error: st.error(str(error))


def _payroll_intake(conn):
    if notice:=st.session_state.pop('staff_payroll_notice',None): st.success(notice)
    teachers=ui.df(conn,'SELECT national_id,full_name,salary FROM teachers WHERE archived_at IS NULL ORDER BY full_name,national_id')
    mapping={r['national_id']:r for r in teachers.to_dict('records')}
    version=st.session_state.get('staff_payroll_version',0); prefix=f'staff_payroll_{version}'
    st.session_state.setdefault(prefix+'_token',str(uuid.uuid4()))
    previous=st.session_state.get(prefix+'_quote')
    kind=st.radio('نوع الصرف',['راتب','سلفة'],horizontal=True,key=prefix+'_kind')
    tid=st.selectbox('المعلمة',list(mapping),index=None,
        format_func=lambda k:mapping[k]['full_name']+' · '+k,key=prefix+'_teacher')
    month=st.text_input('عن شهر (YYYY-MM)',value=F.today().strftime('%Y-%m'),key=prefix+'_month')
    day=st.date_input('تاريخ الصرف',value=F.today(),max_value=F.today(),key=prefix+'_date')
    base=st.number_input('الراتب الأساسي' if kind=='راتب' else 'مبلغ السلفة',min_value=0.0,
        value=float(mapping[tid]['salary']) if tid else 0.0,key=prefix+'_base_'+str(tid))
    bonus=st.number_input('المكافأة',min_value=0.0,key=prefix+'_bonus') if kind=='راتب' else 0
    deduction=st.number_input('الخصم',min_value=0.0,key=prefix+'_deduction') if kind=='راتب' else 0
    notes=st.text_input('ملاحظات الصرف',key=prefix+'_notes')
    try:
        quote=P.salary_preview(base,bonus,deduction)
    except ValueError as error:
        st.info(str(error)); quote=None
    signature=(tid,kind,month,str(day),str(base),str(bonus),str(deduction)) if quote else None
    st.session_state[prefix+'_quote']=signature
    if quote: st.info(f"الصافي: {quote['net']:,.2f} أوقية قديمة")
    if st.button('تسجيل الصرف',disabled=not tid or not quote,key=prefix+'_save'):
        try:
            if previous!=signature: raise ValueError('راجع الصافي المحدّث ثم اضغط تسجيل الصرف مجددًا.')
            args=dict(actor=st.session_state['auth_user'],token=st.session_state[prefix+'_token'],notes=notes,on_date=day)
            if kind=='راتب': P.save_salary(tid,month,base,bonus,deduction,**args)
            else: P.save_advance(tid,month,base,**args)
            st.session_state['staff_payroll_version']=version+1
            st.session_state['staff_payroll_notice']='سُجل الصرف باسم حسابك.'
            st.rerun()
        except ValueError as error: st.error(str(error))
