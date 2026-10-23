"""Useful administration in the same web UI. Explicit table/field allowlists."""
from datetime import date
from decimal import Decimal
import uuid
from psycopg2 import sql
import access_control as A
import records as R
import record_history as H
import monthly_finance as F
import db

LABELS={
 'on_date':'يوم الحضور','excuse':'عذر الغياب','department_name':'القسم وقت التسجيل','person_id':'الملف','department_id':'القسم','father_name':'اسم الأب','father_mobile':'هاتف الأب','mother_name':'اسم الأم','mother_mobile':'هاتف الأم',
 'contact_email':'البريد','full_name':'الاسم','national_id':'الهوية','salary':'الراتب','mobile':'الهاتف',
 'address':'العنوان','hire_date':'تاريخ التوظيف','experience_years':'سنوات الخبرة','degree':'المؤهل','specialization':'التخصص',
 'purchase_date':'تاريخ الشراء','item_name':'اسم التجهيز','category':'التصنيف','quantity':'الكمية','unit_cost':'سعر الوحدة',
 'condition_status':'الحالة','notes':'الملاحظات','start_date':'بداية الاشتراك','status':'حالة الرسوم',
 'amount':'المبلغ','effective_on':'تاريخ إسقاط الدين','salary_month':'الشهر','base_salary':'الأساسي','bonus':'المكافأة',
 'deductions':'الخصومات','payment_date':'تاريخ الصرف','advance_date':'تاريخ السلفة','class_type':'الصف',
 'section':'الشعبة','class_name':'اسم الصف','teacher_id':'المعلم','year_id':'السنة','end_date':'النهاية','cohort_name':'الدفعة',
 'student_id':'الطالب','class_id':'الصف','registration_date':'التاريخ','annual_tuition':'الرسوم السابقة',
 'father_job':'عمل الأب','mother_job':'عمل الأم','mother_work_type':'نوع عمل الأم','father_id_type':'نوع هوية الأب',
 'mother_id_type':'نوع هوية الأم','landline':'الهاتف الثابت','status_refugee':'حالة اللجوء','father_work_phone':'هاتف عمل الأب',
 'mother_work_phone':'هاتف عمل الأم','emergency_contact_name':'جهة الطوارئ','emergency_contact_phone':'هاتف الطوارئ',
 'marital_status':'الحالة الاجتماعية','mother_id':'هوية الأم'}
TABLES={
 'parents':('أولياء الأمور',R.FIELDS['parents']),
 'teachers':('المعلمين',R.FIELDS['teachers']),
 'assets':('التجهيزات والجرد',R.FIELDS['assets']),
 'monthly_accounts':('الاشتراك والإعفاء',('start_date','status')),
 'monthly_waivers':('إسقاطات الدين',('amount','effective_on')),
 'teacher_payments':('الرواتب',('salary_month','payment_date','base_salary','bonus','deductions','notes')),
 'teacher_advances':('السلف',('salary_month','advance_date','amount','notes')),
 'classes':('الصفوف السابقة',R.FIELDS['classes']),
 'academic_years':('السنوات السابقة',R.FIELDS['academic_years']),
 'registrations':('التسجيلات السابقة',R.FIELDS['registrations']),
}
DATES={'hire_date','purchase_date','start_date','end_date','effective_on','payment_date','advance_date','registration_date'}
NUMBERS={'salary','experience_years','quantity','unit_cost','amount','base_salary','bonus','deductions','annual_tuition'}
REQUIRED={'teachers':{'full_name','national_id','department_id'},'assets':{'item_name','category','quantity','unit_cost'},
          'monthly_accounts':{'start_date','status'},'monthly_waivers':{'amount','effective_on'}}

def catalog():
    groups=[]
    for table,(title,keys) in TABLES.items():
        resource=A.TABLE_RESOURCE[table]
        if not A.can(resource+'.view'):continue
        fields=[]
        for key in keys:
            choices=['regular','exempt'] if table=='monthly_accounts' and key=='status' else []
            fields.append(dict(key=key,label=LABELS.get(key,key),type='select' if choices else
                'date' if key in DATES else 'number' if key in NUMBERS else 'month' if key=='salary_month' else 'text',
                required=key in REQUIRED.get(table,set()),choices=choices))
        groups.append(dict(key=table,title=title,fields=fields,edit=A.can(resource+'.edit'),
            delete=A.can(resource+'.delete'),create=table in ('teachers','assets') and A.can(resource+'.create')))
    return groups

def list_rows(conn,data):
    from live_pages import text,require,rows
    table=text(data,'table',40,True)
    if table not in TABLES:raise ValueError('القائمة غير متاحة.')
    require(conn,A.table_permission(table,'view'))
    page=data.get('page',1)
    if type(page) is not int or not 1<=page<=100000:raise ValueError('رقم الصفحة غير صحيح.')
    query=text(data,'query',120)
    # Search only displayed input, never request hashes, session data or binary data.
    keys=list(TABLES[table][1]);pk=H.TABLES[table]
    if table=='teachers':keys+=['display_national_id']
    clauses=[];params=[]
    state='entry_cancelled_at' if table.startswith('teacher_') else 'archived_at'
    if table not in ('monthly_waivers',) and not data.get('archived'):
        clauses.append(sql.SQL('{} IS NULL').format(sql.Identifier(state)))
    if query:
        pattern='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        clauses.append(sql.SQL('(')+sql.SQL(' OR ').join(sql.SQL('CAST({} AS text) ILIKE %s').format(sql.Identifier(k)) for k in keys)+sql.SQL(')'))
        params += [pattern]*len(keys)
    where=sql.SQL(' WHERE ')+sql.SQL(' AND ').join(clauses) if clauses else sql.SQL('')
    with conn.cursor() as c:
        c.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}{}').format(sql.Identifier(table),where),params)
        count=c.fetchone()['n']
        c.execute(sql.SQL('SELECT * FROM {}{} ORDER BY {} LIMIT 20 OFFSET %s').format(sql.Identifier(table),where,sql.Identifier(pk)),[*params,(page-1)*20])
        items=[dict(x) for x in c.fetchall()]
    names={}
    if table in ('monthly_accounts','monthly_waivers','registrations'):
        names={r['student_id']:r['full_name'] for r in rows(conn,'SELECT student_id,full_name FROM students')}
    if table.startswith('teacher_'):
        names={r['national_id']:r['full_name']+' · '+(r['display_national_id'] or r['national_id']) for r in rows(conn,'SELECT national_id,display_national_id,full_name FROM teachers')}
    output=[]
    for r in items:
        title=r.get('full_name') or r.get('item_name') or r.get('father_name') or r.get('mother_name') or names.get(r.get('student_id') or r.get('national_id')) or r.get('class_name') or r.get('display_year_id') or str(r[pk])
        values={k:r.get(k) for k in TABLES[table][1]}
        if table=='teachers':values['national_id']=r.get('display_national_id') or r['national_id']
        output.append(dict(id=r[pk],title=title,values=values,revision=R.revision(r),cancelled=bool(r.get(state)),
            cash=r.get('cash_amount'),document=r.get('record_state'),student=r.get('student_id')))
    return dict(items=output,total=count,page=page,pages=max(1,(count+19)//20))

def change(conn,data,profile):
    from live_pages import text,require,request_token
    table=text(data,'table',40,True);mode=text(data,'mode',20,True)
    if table not in TABLES:raise ValueError('السجل غير متاح.')
    if data.get('confirmed') is not True:raise ValueError('راجع البيانات وأكد الإجراء.')
    reason=text(data,'reason',2000,True);actor=profile['username'];ident=data.get('id')
    expected=text(data,'revision',64,required=mode!='create')
    values=data.get('values',{})
    if not isinstance(values,dict) or set(values)-set(TABLES[table][1]):raise ValueError('حقول غير متاحة.')
    if mode not in ('edit','cancel','create','void_document'):raise ValueError('الإجراء غير متاح.')
    if mode=='void_document' and table not in ('teacher_payments','teacher_advances'):raise ValueError('إلغاء المستند متاح للرواتب والسلف فقط.')
    if mode=='create' and table not in ('teachers','assets'):raise ValueError('الإضافة غير متاحة هنا.')
    values={k:date.fromisoformat(v) if k in DATES and v else None if k in DATES else v for k,v in values.items()}
    if table in R.FIELDS:
        if mode=='create':
            if table not in ('teachers','assets'):raise ValueError('الإضافة غير متاحة هنا.')
            require(conn,A.table_permission(table,'create'))
            with conn.cursor() as c:
                A.require(c,A.table_permission(table,'create'));H.context(c,actor,reason)
                token=request_token(data)
                fingerprint=F._hash(dict(table=table,values=values,actor=actor,reason=reason,new_department=data.get('new_department','')))
                c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(token,))
                c.execute('SELECT * FROM app_tool_requests WHERE request_token=%s',(token,))
                previous=c.fetchone()
                if previous:
                    if previous['request_hash']!=fingerprint:raise ValueError('تغيّرت بيانات الطلب؛ أعد فتح النموذج.')
                    conn.commit();return {'id':previous['record_id'],'created':False}
                if table=='teachers':
                    from school_people import department
                    values['department_id']=department(c,values.get('department_id'),data.get('new_department',''))
                    A.require(c,'teachers.create')
                R._validate(c,table,{},values)
                if table=='teachers':
                    public=str(values.pop('national_id','')).strip()
                    if not public or len(public)>20:raise ValueError('أدخل هوية حتى 20 حرفًا.')
                    values.update(national_id='T'+uuid.uuid4().hex[:19],display_national_id=public)
                c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING {}').format(sql.Identifier(table),
                    sql.SQL(',').join(map(sql.Identifier,values)),sql.SQL(',').join(sql.Placeholder() for _ in values),sql.Identifier(H.TABLES[table])),list(values.values()))
                ident=c.fetchone()[H.TABLES[table]]
                c.execute('INSERT INTO app_tool_requests(request_token,request_hash,record_id) VALUES(%s,%s,%s)',(token,fingerprint,str(ident)))
            conn.commit()
        elif mode=='cancel':R.cancel(table,ident,actor=actor,reason=reason,expected=expected)
        elif mode=='edit':R.edit(table,ident,values,actor=actor,reason=reason,expected=expected)
        else:raise ValueError('هذا ليس مستند راتب.')
    elif table=='monthly_accounts':
        import account_records as AR
        AR.change_account(ident,actor=actor,reason=reason,start_date=values.get('start_date'),status=values.get('status'),cancel=mode=='cancel',expected=expected)
    elif table=='monthly_waivers':
        import account_records as AR
        AR.change_waiver(ident,actor=actor,reason=reason,new_amount=int(values['amount']) if mode=='edit' else None,
            on_date=values.get('effective_on'),cancel=mode=='cancel',expected=expected)
    else:
        import payroll_finance as P
        if mode=='void_document':P.amend(table,ident,actor=actor,reason=reason,cancel=True,expected=expected)
        else:P.correct_cash_entry(table,ident,actor=actor,reason=reason,expected=expected,cancel=mode=='cancel',
            month=values.get('salary_month'),on_date=values.get('payment_date') or values.get('advance_date'),
            base=values.get('base_salary',0),bonus=values.get('bonus',0),deductions=values.get('deductions',0),
            amount=values.get('amount'),notes=values.get('notes',''))
    return {'id':ident}

def reports(conn,data):
    from live_pages import text,require,rows
    require(conn,'reports.view')
    kind=text(data,'kind',30,True)
    if kind=='students':
        require(conn,'students.view')
        return dict(summary={},items=rows(conn,'''SELECT s.full_name AS "الطالب",d.name AS "القسم",
            p.father_name AS "الأب",p.father_mobile AS "هاتف الأب",p.mother_name AS "الأم",p.mother_mobile AS "هاتف الأم"
            FROM students s LEFT JOIN parents p USING(father_id) LEFT JOIN student_departments sd USING(student_id)
            LEFT JOIN school_departments d USING(department_id) WHERE s.archived_at IS NULL ORDER BY s.full_name'''))
    end=date.fromisoformat(text(data,'end',10,True))
    start=end if kind=='debt' else date.fromisoformat(text(data,'start',10,True))
    if start>end or end>F.today():raise ValueError('راجع تاريخ البداية والنهاية.')
    if kind=='finance':return dict(summary=F.financial_report(conn,start,end),items=[])
    if kind=='debt':
        require(conn,'payments.view')
        F._ensure_all_started(end);accounts=F.projections(conn,end,materialize=False)
        names={s['student_id']:s['full_name'] for s in rows(conn,'SELECT student_id,full_name FROM students')}
        return dict(summary={},items=[{'الطالب':names.get(sid,sid),'المتبقي':p['due_now'],'الحالة':'مؤرشف' if p['account']['archived_at'] else 'معفي' if p['exempt'] else 'نشط'} for sid,p in accounts.items() if p['due_now']])
    if kind=='salaries':
        require(conn,'salaries.view')
        teacher=text(data,'teacher',20)
        return dict(summary={},items=rows(conn,'''SELECT t.full_name AS "المعلم",COALESCE(t.display_national_id,t.national_id) AS "الهوية",
            p.salary_month AS "الشهر",p.payment_date AS "التاريخ",p.amount AS "قيمة المستند",p.cash_amount AS "النقد المدفوع",p.record_state AS "حالة المستند"
            FROM teacher_payments p JOIN teachers t USING(national_id) WHERE p.payment_date BETWEEN %s AND %s
            AND (%s='' OR p.national_id=%s) ORDER BY p.payment_date,p.payment_id''',(start,end,teacher,teacher)))
    if kind=='expenses':
        require(conn,'expenses.view')
        return dict(summary={},items=rows(conn,'''SELECT category AS "المصروف",expense_date AS "تاريخ الفاتورة",
            amount AS "الإجمالي",amount_paid AS "المدفوع التراكمي",amount-amount_paid AS "المتبقي",payee AS "المستلم"
            FROM expenses WHERE cancelled_at IS NULL AND teacher_payment_id IS NULL AND teacher_advance_id IS NULL
            AND expense_date BETWEEN %s AND %s ORDER BY expense_date,expense_id''',(start,end)))
    raise ValueError('التقرير غير متاح.')
