"""Typed operator forms with optimistic locking, reasons and deletion confirmation."""
import json
from datetime import date
import streamlit as st
from psycopg2 import sql
import ui
import records as R
import record_history as H
from sections.change_history import FIELD_NAMES

FINANCE={'expenses':('expense_date','category','amount','amount_paid','payment_method','payee','notes'),
         'teacher_payments':('national_id','payment_date','salary_month','base_salary','bonus','deductions','notes'),
         'teacher_advances':('national_id','advance_date','salary_month','amount','notes'),
         'payments':('amount','payer_name','payment_for','payment_for_other','payment_date'),
         'monthly_accounts':('start_date','status'),
         'monthly_waivers':('amount','effective_on')}
CHOICES=list(R.FIELDS)+list(FINANCE)+['monthly_receipts','monthly_tariffs']
REFERENCES={'father_id':('parents','father_id','COALESCE(father_name,mother_name)'),
            'department_id':('school_departments','department_id','name'),
            'teacher_id':('teachers','national_id','full_name'),'student_id':('students','student_id','full_name'),
            'class_id':('classes','class_id',"class_type||' '||section"),'year_id':('academic_years','year_id','year_id')}


def render(conn):
    ui.section_header('✏️','إدارة السجلات','اختر السجل لتعديل بياناته أو إلغاء إدخال خاطئ')
    if notice:=st.session_state.pop('records_notice',None): st.success(notice)
    default=st.session_state.pop('records_target',None)
    if default in CHOICES: st.session_state['records_type']=default
    table=st.selectbox('نوع السجل',CHOICES,format_func=R.LABELS.get,key='records_type')
    if table=='monthly_tariffs': _tariffs(conn); return
    show=st.checkbox('عرض المحذوف والملغى',key='records_show_cancelled')
    with conn.cursor() as c:
        c.execute(sql.SQL('SELECT * FROM {} ORDER BY {} DESC').format(sql.Identifier(table),sql.Identifier(H.TABLES[table])))
        rows=[dict(r) for r in c.fetchall()]
        c.execute('SELECT student_id,full_name FROM students')
        students={r['student_id']:r['full_name'] for r in c.fetchall()}
        c.execute('SELECT national_id,full_name FROM teachers')
        teachers={r['national_id']:r['full_name'] for r in c.fetchall()}
    if not show: rows=[r for r in rows if not _cancelled(r,table)]
    term=st.text_input('بحث بالاسم أو الرقم',key='records_search').strip().lower()
    def title(r):
        person=students.get(r.get('student_id')) or teachers.get(r.get('national_id'))
        return (person+' · ' if person and not r.get('full_name') else '')+_title(r,table)
    if term: rows=[r for r in rows if term in (title(r)+' '+' '.join(str(v or '') for v in r.values())).lower()]
    if not rows: ui.empty_state('لا توجد سجلات مطابقة.'); return
    pk=H.TABLES[table]; mapping={r[pk]:r for r in rows}
    chosen=st.selectbox('اختر السجل',list(mapping),index=None,
        format_func=lambda key:title(mapping[key]),key='records_pick_'+table)
    if chosen is None: return
    fresh=mapping[chosen]
    scope=f'{table}:{chosen}'
    if st.session_state.get('records_open')!=scope:
        st.session_state['records_open']=scope
        st.session_state['records_snapshot']=fresh
        st.session_state['records_form_version']=st.session_state.get('records_form_version',0)+1
    if st.button('تحديث بيانات السجل',key='records_refresh'):
        st.session_state.pop('records_open',None); st.rerun()
    row=st.session_state['records_snapshot']
    if R.revision(fresh)!=R.revision(row): st.warning('تغيّر هذا السجل بعد فتحه؛ حدّث بياناته قبل الحفظ.')
    if table=='monthly_receipts':
        from sections.receipt_inspector import render_inspector
        st.caption('لتصحيح الطفل الذي سُجلت له دفعة بالخطأ: ألغِ الوصل ثم سجّل الدفعة للطفل الصحيح. تبقى العمليتان في السجل.')
        render_inspector(conn,int(chosen),scope='records'); return
    if _cancelled(fresh,table):
        st.info('هذا الإدخال ملغى أو محذوف. أصله محفوظ في سجل التغييرات.')
        ui.dataframe([{'الحقل':FIELD_NAMES[k],'القيمة':str(v if v is not None else '—')} for k,v in row.items() if k in FIELD_NAMES],hide_index=True,use_container_width=True)
        return
    fields=R.FIELDS.get(table,FINANCE.get(table,()))
    version=st.session_state['records_form_version']
    with conn.cursor() as c:
        c.execute('SELECT column_name,data_type,character_maximum_length FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s',(table,))
        types={r['column_name']:r for r in c.fetchall()}
    with st.form('records_edit_'+str(version)):
        values={}
        cols=st.columns(2)
        for i,field in enumerate(fields):
            with cols[i%2]: values[field]=_input(conn,table,field,row.get(field),types[field],version)
        reason=st.text_input('سبب التعديل *',max_chars=2000)
        confirmed=True
        if table in FINANCE:
            confirmed=st.checkbox('أؤكد تعديل الاشتراك / الإعفاء دون تسجيل قبض' if table in ('monthly_accounts','monthly_waivers')
                else 'أؤكد أن هذا تصحيح لبيانات أدخلت خطأ، وأن المبلغ المصحح هو المبلغ الفعلي')
        save=st.form_submit_button('حفظ التعديل',type='primary')
    if save:
        try:
            if not confirmed: raise ValueError('أكد صحة المبلغ المصحح.')
            _edit(table,chosen,values,row,reason)
            _done('تم حفظ التعديل وتحديث الحسابات المرتبطة.')
        except (ValueError,PermissionError) as error: st.error(str(error))
        except Exception: st.error('تعذر الحفظ؛ لم يُطبّق التعديل جزئيًا.')
    with st.expander('حذف / إلغاء السجل'):
        st.caption('يزول من القوائم الحالية. بياناته السابقة وقرار الحذف يبقيان في سجل التغييرات.')
        destination=None
        waiver=False
        if table=='school_departments':
            with conn.cursor() as c:
                c.execute('SELECT department_id,name FROM school_departments WHERE archived_at IS NULL AND department_id<>%s ORDER BY name',(chosen,))
                destinations={r['department_id']:r['name'] for r in c.fetchall()}
            destination=st.selectbox('الأطفال الموجودون في القسم',[None]+list(destinations),
                format_func=lambda x:'تركهم بدون قسم' if x is None else 'نقلهم إلى '+destinations[x])
        if table=='students':
            waiver=st.checkbox('إسقاط أي مبلغ متبقٍ على الطالب عند إلغاء الملف (لا يُسجل كقبض)')
            st.caption('الدفعات المقبوضة تبقى؛ لإلغاء دفعة خاطئة افتح الوصل نفسه.')
        if table=='parents': st.caption('يبقى ارتباط الأطفال بهذا السجل محفوظًا؛ يمكن اختيار ولي أمر آخر من تعديل الطالب.')
        if table=='registrations': st.caption('يلغى أثر الوصولات السنوية التابعة لهذا التسجيل كذلك.')
        why=st.text_input('سبب الحذف أو الإلغاء *',max_chars=2000,key='records_delete_reason_'+str(version))
        agree=st.checkbox('أؤكد إلغاء هذا الإدخال',key='records_delete_agree_'+str(version))
        if st.button('تأكيد الحذف / الإلغاء',disabled=not agree,key='records_delete_'+str(version)):
            try:
                _cancel(table,chosen,row,why,destination,waiver)
                _done('تم الإلغاء؛ العملية محفوظة في سجل التغييرات.')
            except (ValueError,PermissionError) as error: st.error(str(error))
            except Exception: st.error('تعذر الإلغاء؛ لم يتغير السجل جزئيًا.')
    if st.button('عرض سجل تغييرات هذا السجل'):
        st.session_state['history_target']=(table,str(chosen))
        st.session_state['current_page']='history'; st.rerun()


def _actor():
    actor=st.session_state.get('auth_user')
    if not actor: raise PermissionError('أعد تسجيل الدخول قبل حفظ التغييرات.')
    return actor


def _cancelled(row,table):
    # Retiring a payroll document leaves its actual cash. It can still be corrected.
    if table in ('teacher_payments','teacher_advances'): return bool(row.get('entry_cancelled_at'))
    return bool(row.get('archived_at') or row.get('cancelled_at') or row.get('receipt_state')=='cancelled' or row.get('state')=='cancelled')


def _title(row,table):
    key=row[H.TABLES[table]]
    name=row.get('full_name') or row.get('name') or row.get('item_name') or row.get('category') or row.get('father_name') or row.get('mother_name') or row.get('salary_month') or row.get('cohort_name') or ''
    public=row.get('display_national_id') or row.get('display_year_id') or key
    return f'{name} · #{public}'+(' · ملغى' if _cancelled(row,table) else '')


def _input(conn,table,field,value,meta,version):
    label=FIELD_NAMES.get(field,{'payer_name':'الدافع','payment_for':'نوع الدفعة','payment_for_other':'تفاصيل الدفعة'}.get(field,field))
    key=f'record_field_{version}_{field}'
    display={'teachers':('national_id','display_national_id'),'academic_years':('year_id','display_year_id')}.get(table)
    if display and field==display[0]:
        value=st.session_state['records_snapshot'].get(display[1]) or value
    reference=REFERENCES.get(field)
    if field=='national_id' and table in FINANCE: reference=('teachers','national_id','full_name')
    if reference and reference[0]!=table:
        target,pk,description=reference
        if target=='teachers': description="full_name||' · '||COALESCE(display_national_id,national_id)"
        if target=='academic_years': description='COALESCE(display_year_id,year_id)'
        with conn.cursor() as c:
            c.execute(sql.SQL('SELECT {} AS key,{} AS name FROM {} WHERE archived_at IS NULL OR {}=%s').format(sql.Identifier(pk),sql.SQL(description),sql.Identifier(target),sql.Identifier(pk)),(value,))
            options={r['key']:r['name'] for r in c.fetchall()}
        items=[None]+list(options)
        return st.selectbox(label,items,index=items.index(value) if value in items else 0,
                            format_func=lambda x:'بدون' if x is None else str(options[x]) if target in ('teachers','academic_years') else f'{options[x]} · {x}',key=key)
    kind=meta['data_type']
    if table=='monthly_accounts' and field=='status':
        return st.selectbox(label,['regular','exempt'],index=0 if value=='regular' else 1,
                            format_func=lambda x:'عادي' if x=='regular' else 'معفي',key=key)
    if kind=='date':
        return st.date_input(label,value=value or None,min_value=date(1900,1,1),max_value=date(2100,12,31),key=key)
    if kind in ('integer','bigint','numeric'):
        if kind=='numeric': return st.number_input(label,value=float(value or 0),step=1.0,format='%.2f',key=key)
        return st.number_input(label,value=int(value or 0),step=1,key=key)
    if field=='authorized_pickups':
        import pandas as pd
        data=pd.DataFrame(value or [],columns=['name','phone'])
        edited=st.data_editor(data,num_rows='dynamic',hide_index=True,
            column_config={'name':st.column_config.TextColumn('الاسم'),'phone':st.column_config.TextColumn('الهاتف')},key=key)
        return edited.fillna('').to_dict('records')
    return st.text_input(label,value=str(value or ''),max_chars=meta['character_maximum_length'] or 4000,key=key)


def _edit(table,ident,values,row,reason):
    actor=_actor()
    if not reason.strip(): raise ValueError('أدخل سبب التعديل.')
    expected=R.revision(row)
    if table=='monthly_accounts':
        from account_records import change_account
        return change_account(ident,**values,actor=actor,reason=reason,expected=expected)
    if table=='monthly_waivers':
        from account_records import change_waiver
        return change_waiver(ident,new_amount=values['amount'],on_date=values['effective_on'],actor=actor,reason=reason,expected=expected)
    if table in R.FIELDS:
        return R.edit(table,ident,values,actor=actor,reason=reason,expected=expected)
    if table=='expenses':
        import expense_finance as E
        return E.correct(ident,amount_total=values['amount'],amount_paid=values['amount_paid'],category=values['category'],
             expense_date=values['expense_date'],payee=values['payee'],notes=values['notes'],reason=reason,actor=actor,
             expected=expected,include_settlements=True,payment_method=values['payment_method'])
    if table in ('teacher_payments','teacher_advances'):
        import payroll_finance as P
        return P.correct_cash_entry(table,ident,actor=actor,reason=reason,expected=expected,
             amount=values.get('amount'),base=values.get('base_salary',0),bonus=values.get('bonus',0),
             deductions=values.get('deductions',0),month=values['salary_month'],on_date=values.get('payment_date',values.get('advance_date')),
             notes=values['notes'],national_id=values['national_id'])
    if table=='payments':
        import historical_finance as L
        return L.change_receipt(ident,actor=actor,reason=reason,new_amount=values['amount'],payer=values['payer_name'],
             payment_for=values['payment_for'],details=values['payment_for_other'],on_date=values['payment_date'],expected=expected)


def _cancel(table,ident,row,reason,destination,waiver):
    actor=_actor(); expected=R.revision(row)
    if table=='monthly_accounts':
        from account_records import change_account
        return change_account(ident,actor=actor,reason=reason,cancel=True,expected=expected)
    if table=='monthly_waivers':
        from account_records import change_waiver
        return change_waiver(ident,actor=actor,reason=reason,cancel=True,expected=expected)
    if table in R.FIELDS: return R.cancel(table,ident,actor=actor,reason=reason,expected=expected,destination=destination,waive_student_debt=waiver)
    if table=='expenses':
        import expense_finance as E
        return E.cancel(ident,actor=actor,reason=reason,expected=expected)
    if table in ('teacher_payments','teacher_advances'):
        import payroll_finance as P
        return P.correct_cash_entry(table,ident,actor=actor,reason=reason,cancel=True,expected=expected)
    if table=='payments':
        import historical_finance as L
        return L.change_receipt(ident,actor=actor,reason=reason,cancel=True,expected=expected)


def _done(message):
    st.session_state['records_notice']=message
    st.session_state.pop('records_open',None)
    st.rerun()


def _tariffs(conn):
    import monthly_finance as F
    fresh=F.prices(conn) or {}
    if st.session_state.get('records_open')!='monthly_tariffs':
        st.session_state['records_open']='monthly_tariffs'
        st.session_state['records_tariff_snapshot']=dict(fresh)
        st.session_state['records_form_version']=st.session_state.get('records_form_version',0)+1
    settings=st.session_state['records_tariff_snapshot']
    version=st.session_state['records_form_version']
    if dict(fresh)!=settings: st.warning('تغيّرت الرسوم بعد فتح النموذج؛ حدّث البيانات قبل الحفظ.')
    if st.button('تحديث بيانات الرسوم'):
        st.session_state.pop('records_open',None); st.rerun()
    with st.form('record_tariffs_'+str(version)):
        vals={key:st.number_input(FIELD_NAMES[key],min_value=0 if key!='tuition' else 1,value=int(settings.get(key,1 if key=='tuition' else 0)),step=1,key=f'record_tariff_{version}_{key}') for key in ('registration','gilet','tuition')}
        reason=st.text_input('سبب تعديل الرسوم *')
        if st.form_submit_button('حفظ الرسوم',type='primary'):
            try:
                if not reason.strip(): raise ValueError('أدخل سبب التعديل.')
                F.update_tariffs(**vals,actor=_actor(),reason=reason,expected=R.revision(settings))
                _done('تم حفظ الرسوم الجديدة؛ أسعار الفواتير السابقة محفوظة.')
            except ValueError as error: st.error(str(error))
    st.caption('الرسوم إعداد دائم. يمكنك استعادة الأسعار السابقة من سجل التغييرات وإدخالها هنا، أو جعل رسوم التسجيل والجيليه صفرًا.')
