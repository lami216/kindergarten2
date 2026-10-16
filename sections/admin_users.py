"""Manager-only accounts, grants and measured saved activity."""
import secrets
import streamlit as st
import access_control as A
import records as R
import ui


def permission_fields(prefix,selected=()):
    values=[]
    for resource,(label,actions) in A.RESOURCES.items():
        with st.container(key=f'{prefix}_{resource}_group'):
            with st.expander(label,expanded=any(resource+'.'+a in selected for a in actions)):
                columns=st.columns(2)
                for index,action in enumerate(actions):
                    with columns[index%2]:
                        if st.checkbox(A.ACTIONS[action],value=resource+'.'+action in selected,
                            key=f'{prefix}_{resource}_{action}'):
                            values.append(resource+'.'+action)
    st.caption('التعديل والإلغاء يضيفان حق العرض تلقائيًا. تسجيل الدفعات أو الرواتب يتطلب عرض حساباتها. التقارير إذن مستقل يكشف المجاميع المالية.')
    return values


def render(conn):
    with conn.cursor() as c: A.require(c,'admin.manage')
    ui.section_header('🔐','لوحة المدير','الحسابات والصلاحيات ونشاط العاملين')
    if notice:=st.session_state.pop('admin_notice',None): st.success(notice)
    users=A.list_users(conn)
    accounts,usage,audit=st.tabs(['👥 الحسابات والصلاحيات','📊 نشاط العاملين','🕘 سجل إدارة الحسابات'],
        key='admin_tabs',on_change='rerun')
    labels={str(u['user_id']):f"{u['employee_name']} · {u['username']}" for u in users}
    with accounts:
        with st.expander('➕ إنشاء حساب عامل',expanded=not any(not u['is_admin'] for u in users)):
            if st.button('توليد كلمة مرور للحساب الجديد',key='admin_generate'):
                st.session_state['admin_new_password']=secrets.token_urlsafe(15)
            with st.form('admin_create'):
                name=st.text_input('اسم العامل *',max_chars=100,key='admin_new_name')
                login=st.text_input('اسم المستخدم *',max_chars=64,key='admin_new_username')
                password=st.text_input('كلمة المرور *',type='password',key='admin_new_password',help='12 حرفًا على الأقل؛ زر العين يعرض الكلمة لتسليمها للعامل.')
                manager=st.checkbox('هذا الحساب مدير ويملك جميع الصلاحيات',key='admin_new_manager')
                perms=permission_fields('admin_new_grants')
                save=st.form_submit_button('إنشاء الحساب',type='primary')
            if save:
                try:
                    A.save_user(employee_name=name,name=login,password=password,is_admin=manager,permissions=perms)
                    for key in list(st.session_state):
                        if key.startswith(('admin_new_','admin_new_grants')): del st.session_state[key]
                    st.session_state['admin_notice']='تم إنشاء الحساب. يدخل العامل باسم المستخدم وكلمة المرور اللذين حددتهما.'
                    st.rerun()
                except ValueError as error: st.error(str(error))
        st.markdown('##### الحسابات المسجلة')
        ui.dataframe([{'اسم العامل':u['employee_name'],'اسم المستخدم':u['username'],
            'الدور':'مدير' if u['is_admin'] else 'عامل','الحالة':'مفعل' if u['active'] else 'معطل',
            'آخر دخول':str(u['last_login_at'] or 'لم يدخل بعد')} for u in users],hide_index=True,use_container_width=True)
        chosen=st.selectbox('اختر حسابًا لإدارة صلاحياته',list(labels),format_func=labels.get,index=None,key='admin_selected_user')
        if chosen:
            fresh=next(u for u in users if str(u['user_id'])==chosen)
            if st.session_state.get('admin_snapshot_id')!=chosen:
                for key in list(st.session_state):
                    if key.startswith('admin_edit_'): del st.session_state[key]
                st.session_state['admin_snapshot_id']=chosen
                st.session_state['admin_snapshot']=dict(fresh)
            original=st.session_state['admin_snapshot']
            if fresh['auth_version']!=original['auth_version']: st.warning('تغير هذا الحساب. حدّث بياناته قبل الحفظ.')
            if st.button('تحديث بيانات الحساب',key='admin_refresh'):
                st.session_state.pop('admin_snapshot_id',None); st.rerun()
            with st.form('admin_edit_user'):
                employee=st.text_input('اسم العامل',value=original['employee_name'],key='admin_edit_name')
                st.caption('اسم المستخدم ثابت: '+original['username'])
                active=st.checkbox('الحساب مفعل',value=original['active'],key='admin_edit_active')
                manager=st.checkbox('مدير بجميع الصلاحيات',value=original['is_admin'],key='admin_edit_manager')
                password=st.text_input('كلمة مرور جديدة (اتركها فارغة للإبقاء على الحالية)',type='password',key='admin_edit_password')
                perms=permission_fields('admin_edit_grants',original['permissions'])
                st.caption('حفظ أي تغيير ينهي جلسات هذا الحساب؛ يدخل مجددًا بصلاحياته الجديدة. تعطيل الحساب يحفظ أعماله وهويته السابقة.')
                confirm=st.checkbox('أؤكد تغيير صلاحيات هذا الحساب',key='admin_edit_confirm')
                save=st.form_submit_button('حفظ الحساب والصلاحيات',type='primary')
            if save:
                try:
                    if not confirm: raise ValueError('أكد تغيير صلاحيات الحساب.')
                    A.save_user(user_id=chosen,employee_name=employee,password=password or None,is_admin=manager,
                        permissions=perms,active=active,expected_version=original['auth_version'])
                    st.session_state.pop('admin_snapshot_id',None)
                    st.session_state['admin_notice']='حُفظ الحساب وأُبطلت جلساته القديمة.'
                    st.rerun()
                except ValueError as error: st.error(str(error))
    with usage:
        who=st.selectbox('العامل',list(labels),format_func=labels.get,key='admin_activity_user')
        user=next(u for u in users if str(u['user_id'])==who)
        st.write('**الصلاحيات الحالية:** '+('مدير — جميع الصلاحيات' if user['is_admin'] else
            '، '.join(A.RESOURCES[p.split('.')[0]][0]+': '+A.ACTIONS[p.split('.')[1]] for p in user['permissions']) or 'لم تُمنح صلاحيات'))
        with st.container(key='admin_usage_'+str(who)):
            st.caption('نشاط حساب: '+user['employee_name']+' · '+user['username'])
            metrics=A.employee_metrics(conn,who)
            a,b,c=st.columns(3)
            a.metric('طلاب سجلهم العامل',metrics['students'])
            b.metric('مصروفات تشغيلية سجلها',metrics['expenses']['count'])
            c.metric('وصولات قبض أصلية سجلها',metrics['payments']['count'])
            a,b=st.columns(2)
            a.metric('مصروف مسجل أصلاً',f"{metrics['expenses']['original_cash']:,.2f} أوقية")
            b.metric('صافي تلك المصروفات حاليًا',f"{metrics['expenses']['current_cash']:,.2f} أوقية")
            a,b=st.columns(2)
            a.metric('قبض مسجل أصلاً',f"{metrics['payments']['original_cash']:,.0f} أوقية")
            b.metric('صافي تلك الوصولات حاليًا',f"{metrics['payments']['current_cash']:,.0f} أوقية")
            st.caption('النشاط منذ تفعيل الحسابات، لجميع التواريخ. الصافي يتبع السجل الأصلي بعد تصحيحه أو إلغائه، حتى لو صححه عامل آخر. التصحيح ليس قبضًا جديدًا، والرواتب ليست مصروفات تشغيلية ثانية. لا يُقاس الإذن بنسبة استهلاك.')
            if metrics['activity']:
                ui.dataframe([{'المجال':R.LABELS.get(r['table_name'],r['table_name']),
                    'العملية':{'created':'إضافة','updated':'تعديل','cancelled':'إلغاء','deleted':'حذف'}.get(r['action'],r['action']),
                    'العمليات المحفوظة':r['events'],'السجلات المختلفة':r['records']} for r in metrics['activity']],hide_index=True,use_container_width=True)
    with audit:
        for event in A.access_history(conn):
            title={'account_created':'إنشاء حساب','account_updated':'تحديث حساب وصلاحيات','owner_bootstrap':'تهيئة المدير الأول'}.get(event['action'],event['action'])
            with st.expander(f"{title} · {event['target_name']} · {event['happened_at']}"):
                st.caption('المسؤول: '+str(event['responsible'] or 'مسؤول التشغيل'))
                before=event['before_state'] or {}; after=event['after_state'] or {}
                def display(state,key):
                    if key not in state: return '—'
                    if key=='active': return 'مفعل' if state[key] else 'معطل'
                    if key=='is_admin': return 'مدير' if state[key] else 'عامل'
                    if key=='permissions':
                        if state.get('is_admin'): return 'جميع الصلاحيات'
                        return '، '.join(A.RESOURCES[p.split('.')[0]][0]+': '+A.ACTIONS[p.split('.')[1]]
                            for p in state[key]) or 'بلا صلاحيات'
                    return state[key]
                fields={'employee_name':'اسم العامل','username':'اسم المستخدم','active':'الحالة','is_admin':'الدور','permissions':'الصلاحيات'}
                ui.dataframe([{'البيان':label,'قبل':display(before,key),'بعد':display(after,key)}
                    for key,label in fields.items() if before.get(key)!=after.get(key)],hide_index=True,use_container_width=True)
                if after.get('password_changed'): st.caption('تم تحديد كلمة مرور جديدة؛ لا تُعرض كلمة المرور في السجل.')
