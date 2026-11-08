"""Monthly salary entitlements and explicit advance recoveries; cash stays in payroll.

All writers lock the teacher first. A payment is cash plus named recoveries,
never a second expense for an advance. Historical deductions are not guessed.
"""
import calendar
from datetime import date,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import hashlib,json
import re
import db,access_control as A,record_history as H,records as R
from monthly_finance import today

ZERO=Decimal('0.00')

def valid_month(value):
    return isinstance(value,str) and bool(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',value)) and '1990-01'<=value<='2099-12'

def business_month(value):
    if isinstance(value,datetime) and value.tzinfo:value=value.astimezone(ZoneInfo('Africa/Nouakchott'))
    return str(value)[:7]

def cash(value):
    from expense_finance import cash as validate
    return validate(value,zero=True)

def month(value):
    from payroll_finance import _month
    value=_month(value)
    if not '1990-01'<=value<='2099-12':raise ValueError('شهر الراتب خارج النطاق المسموح.')
    return value

def migrate(conn):
    with conn.cursor() as c:
        c.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='teacher_advances' AND column_name='legacy_repaid') AS exists")
        had=c.fetchone()['exists']
        c.execute('''CREATE TABLE IF NOT EXISTS teacher_salary_months (
          month_id BIGSERIAL PRIMARY KEY,national_id VARCHAR(20) NOT NULL REFERENCES teachers(national_id) ON DELETE RESTRICT,
          salary_month VARCHAR(7) NOT NULL,base_salary NUMERIC(12,2) NOT NULL CHECK(base_salary>=0),
          bonus NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(bonus>=0),
          deductions NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(deductions>=0),
          review_required BOOLEAN NOT NULL DEFAULT false,source TEXT NOT NULL DEFAULT 'current',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),UNIQUE(national_id,salary_month),
          CHECK(base_salary+bonus>=deductions));
          CREATE UNIQUE INDEX IF NOT EXISTS teacher_payment_owner ON teacher_payments(payment_id,national_id);
          CREATE UNIQUE INDEX IF NOT EXISTS teacher_advance_owner ON teacher_advances(advance_id,national_id);
          CREATE TABLE IF NOT EXISTS teacher_advance_settlements (
          settlement_id BIGSERIAL PRIMARY KEY,payment_id INT NOT NULL REFERENCES teacher_payments(payment_id) ON DELETE RESTRICT,
          advance_id INT NOT NULL REFERENCES teacher_advances(advance_id) ON DELETE RESTRICT,
          national_id VARCHAR(20) NOT NULL,
          amount NUMERIC(12,2) NOT NULL CHECK(amount>0),active BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          FOREIGN KEY(payment_id,national_id) REFERENCES teacher_payments(payment_id,national_id),
          FOREIGN KEY(advance_id,national_id) REFERENCES teacher_advances(advance_id,national_id));
          CREATE INDEX IF NOT EXISTS teacher_recoveries_payment ON teacher_advance_settlements(payment_id) WHERE active;
          CREATE INDEX IF NOT EXISTS teacher_recoveries_advance ON teacher_advance_settlements(advance_id) WHERE active;
          ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS legacy_repaid NUMERIC(12,2) NOT NULL DEFAULT 0;
          ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS review_required BOOLEAN NOT NULL DEFAULT false;
          ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS managed_month BOOLEAN NOT NULL DEFAULT false;''')
        if not had:
            c.execute('''UPDATE teacher_advances SET legacy_repaid=CASE WHEN is_deducted THEN COALESCE(cash_amount,amount) ELSE 0 END,
              review_required=NOT is_deducted WHERE entry_cancelled_at IS NULL;
              INSERT INTO teacher_salary_months(national_id,salary_month,base_salary,bonus,deductions,review_required,source)
              SELECT national_id,salary_month,GREATEST(COALESCE(base_salary,0),COALESCE(deductions,0)-COALESCE(bonus,0)),COALESCE(bonus,0),COALESCE(deductions,0),
              (SELECT COUNT(*)>1 FROM teacher_payments other WHERE other.national_id=p.national_id
                AND other.salary_month=p.salary_month AND other.entry_cancelled_at IS NULL)
                OR (COALESCE(base_salary,0)+COALESCE(bonus,0)-COALESCE(deductions,0)-COALESCE(advance,0)<>COALESCE(cash_amount,amount)),'legacy'
              FROM (SELECT DISTINCT ON(national_id,salary_month) * FROM teacher_payments
              WHERE entry_cancelled_at IS NULL ORDER BY national_id,salary_month,payment_id) p
              ON CONFLICT(national_id,salary_month) DO NOTHING;''')
            c.execute('''INSERT INTO teacher_salary_months(national_id,salary_month,base_salary,review_required,source)
              SELECT t.national_id,to_char(m,'YYYY-MM'),COALESCE(t.salary,0),true,'legacy'
              FROM teachers t CROSS JOIN LATERAL generate_series(
                date_trunc('month',GREATEST(COALESCE(t.hire_date,((CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nouakchott')::date)),DATE '1990-01-01')::timestamp),
                date_trunc('month',LEAST(COALESCE((t.archived_at AT TIME ZONE 'Africa/Nouakchott')::date,((CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nouakchott')::date)),((CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nouakchott')::date))::timestamp),interval '1 month') m
              ON CONFLICT(national_id,salary_month) DO NOTHING''')

def teacher(c,ident,*,lock=False):
    c.execute('SELECT * FROM teachers WHERE national_id=%s'+(' FOR UPDATE' if lock else ' FOR SHARE'),(ident,))
    row=c.fetchone()
    if not row:raise ValueError('ملف المعلم غير موجود.')
    return row

def data(c,ident):
    t=teacher(c,ident)
    result={'teacher':t}
    for key,query in (
      ('months','SELECT * FROM teacher_salary_months WHERE national_id=%s ORDER BY salary_month'),
      ('salaries','SELECT * FROM teacher_payments WHERE national_id=%s ORDER BY payment_id DESC'),
      ('advances','SELECT * FROM teacher_advances WHERE national_id=%s ORDER BY advance_date,advance_id'),
      ('settlements','SELECT s.* FROM teacher_advance_settlements s JOIN teacher_payments p USING(payment_id) WHERE p.national_id=%s ORDER BY settlement_id')):
        c.execute(query,(ident,));result[key]=c.fetchall()
    result['revision']=hashlib.sha256(json.dumps(result,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
    return result

def check_revision(state,expected):
    if expected is not None and expected!=state['revision']:raise ValueError('تغيّر حساب المعلم منذ فتح النافذة؛ أعد فتحها وراجع المبالغ الجديدة.')

def validate_start(t,key,on=None):
    start=t.get('hire_date')
    if start and (key<str(start)[:7] or (on and date.fromisoformat(str(on))<start)):
        raise ValueError('شهر الراتب أو تاريخ الصرف يسبق بداية عمل المعلم؛ صحح التاريخ أولًا.')
    if t.get('archived_at') and key>business_month(t['archived_at']):raise ValueError('هذا الشهر بعد أرشفة ملف المعلم؛ راجع تاريخ العملية.')

def period(state,key):
    row=next((r for r in state['months'] if r['salary_month']==key),None)
    if row:return dict(row)
    # Missing historical months never inherit a later edited salary: teacher
    # edits materialize elapsed months before updating the current salary.
    legacy_cutoff=max([business_month(p['created_at']) for p in state['months'] if p['source']=='legacy']+[''])
    needs_review=key<=legacy_cutoff
    return dict(month_id=None,national_id=state['teacher']['national_id'],salary_month=key,
      base_salary=state['teacher']['salary'] or ZERO,bonus=ZERO,deductions=ZERO,
      review_required=needs_review,source='legacy' if needs_review else 'current')

def totals(state,p,exclude=None):
    entries=[r for r in state['salaries'] if r['salary_month']==p['salary_month'] and r['entry_cancelled_at'] is None and r['payment_id']!=exclude]
    ids={r['payment_id'] for r in entries}
    paid=sum((r['cash_amount'] for r in entries),ZERO)
    recovered=sum((r['amount'] for r in state['settlements'] if r['active'] and r['payment_id'] in ids),ZERO)
    # Known legacy advance deductions keep the original historic settlement.
    recovered+=sum((max(ZERO,(r.get('advance') or ZERO)-sum((s['amount'] for s in state['settlements'] if s['active'] and s['payment_id']==r['payment_id']),ZERO)) for r in entries if not r['managed_month']),ZERO)
    entitlement=p['base_salary']+p['bonus']-p['deductions']
    return dict(entitlement=entitlement,cash_paid=paid,recovered=recovered,settled=paid+recovered,
      remaining=max(ZERO,entitlement-paid-recovered),overpaid=max(ZERO,paid+recovered-entitlement))

def advances(state,exclude=None):
    items=[]
    for a in state['advances']:
        recovered=sum((r['amount'] for r in state['settlements'] if r['active'] and r['advance_id']==a['advance_id'] and r['payment_id']!=exclude),ZERO)
        recovered+=a['legacy_repaid']
        original=a['cash_amount'] if a['entry_cancelled_at'] is None else ZERO
        payments={p['payment_id']:p for p in state['salaries']}
        links=[dict(payment_id=s['payment_id'],salary_month=payments[s['payment_id']]['salary_month'],amount=s['amount']) for s in state['settlements'] if s['active'] and s['advance_id']==a['advance_id']]
        item=dict(**a,repaid=recovered,remaining=max(ZERO,original-recovered),recoveries=links,revision=R.revision(a))
        item['invalid_month']=not valid_month(a['salary_month'])
        if item['invalid_month']:item['review_required']=True
        items.append(item)
    return items

def _put_period(c,p):
    c.execute('''INSERT INTO teacher_salary_months(national_id,salary_month,base_salary,bonus,deductions)
      VALUES(%s,%s,%s,%s,%s) ON CONFLICT(national_id,salary_month) DO NOTHING''',
      (p['national_id'],p['salary_month'],p['base_salary'],p['bonus'],p['deductions']))

def prepare_salary(c,t,args,*,exclude=None):
    ident=t['national_id'];key=month(args['month']);validate_start(t,key,args['date'])
    state=data(c,ident);check_revision(state,args.get('account_revision'))
    p=period(state,key)
    if p['month_id'] is None:
        p.update(base_salary=args['base'],bonus=args['bonus'],deductions=args['deductions'])
    elif not args.get('managed') and exclude and not any(r['salary_month']==key and r['payment_id']!=exclude and r['entry_cancelled_at'] is None for r in state['salaries']):
        # A legacy correction can change a single entry's entitlement. New UI
        # edits the shared month explicitly, so partial payments stay coherent.
        p.update(base_salary=args['base'],bonus=args['bonus'],deductions=args['deductions'])
        c.execute('UPDATE teacher_salary_months SET base_salary=%s,bonus=%s,deductions=%s WHERE month_id=%s',
          (p['base_salary'],p['bonus'],p['deductions'],p['month_id']))
    s=totals(state,p,exclude)
    if p['review_required'] and exclude is None:raise ValueError('راجع استحقاق هذا الشهر القديم قبل تسجيل صرف جديد.')
    requested=cash(args.get('payment_cash') if args.get('payment_cash') is not None else args['amount'])
    allocations=args.get('settlements') or []
    if not isinstance(allocations,list) or len(allocations)>100:raise ValueError('توزيع تسديد السلف غير صحيح.')
    available={a['advance_id']:a for a in advances(state,exclude)};seen=set();clean=[]
    for item in allocations:
        if not isinstance(item,dict) or set(item)!={'id','amount'} or type(item['id']) is not int or item['id'] in seen:raise ValueError('توزيع تسديد السلف غير صحيح.')
        seen.add(item['id']);amount=cash(item['amount'])
        if not amount:continue
        a=available.get(item['id'])
        if not a or a['entry_cancelled_at'] or a['review_required']:raise ValueError('السلفة غير متاحة للتسديد أو تحتاج ربطها بخصم قديم.')
        if a['advance_date']>date.fromisoformat(str(args['date'])) or a['salary_month']>key:raise ValueError('لا يمكن خصم سلفة قبل تاريخ صرفها أو شهر تسديدها.')
        if amount>a['remaining']:raise ValueError('مبلغ تسديد السلفة أكبر من رصيدها المتبقي؛ حدّث النافذة.')
        clean.append(dict(id=item['id'],amount=amount))
    recovery=sum((a['amount'] for a in clean),ZERO)
    if requested+recovery<=0:raise ValueError('أدخل مبلغ صرف أو تسديد سلفة أكبر من صفر.')
    if requested+recovery>s['remaining']:raise ValueError('المبلغ مع تسديد السلف يتجاوز المتبقي من راتب الشهر؛ لا تسجل الراتب مرة أخرى.')
    _put_period(c,p)
    args.update(amount=requested,advance=recovery,settlements=clean,managed=bool(args.get('managed')),
      base=p['base_salary'],bonus=p['bonus'],deductions=p['deductions'])

def persist_settlements(c,payment_id,args):
    c.execute('UPDATE teacher_advance_settlements SET active=false WHERE payment_id=%s AND active',(payment_id,))
    for a in args.get('settlements',[]):
        c.execute('INSERT INTO teacher_advance_settlements(payment_id,advance_id,amount,national_id) SELECT payment_id,%s,%s,national_id FROM teacher_payments WHERE payment_id=%s',(a['id'],a['amount'],payment_id))
    c.execute('SELECT national_id FROM teacher_payments WHERE payment_id=%s',(payment_id,));sync_advances(c,c.fetchone()['national_id'])

def sync_advances(c,ident):
    c.execute('''UPDATE teacher_advances a SET is_deducted=(a.entry_cancelled_at IS NULL AND a.cash_amount>0 AND a.cash_amount<=a.legacy_repaid+
      COALESCE((SELECT SUM(s.amount) FROM teacher_advance_settlements s WHERE s.advance_id=a.advance_id AND s.active),0))
      WHERE a.national_id=%s AND a.is_deducted IS DISTINCT FROM
      (a.entry_cancelled_at IS NULL AND a.cash_amount>0 AND a.cash_amount<=a.legacy_repaid+
      COALESCE((SELECT SUM(s.amount) FROM teacher_advance_settlements s WHERE s.advance_id=a.advance_id AND s.active),0))''',(ident,))

def trim_advance(c,advance_id,new_value):
    """Correcting a mistaken advance reopens salary balances, not new cash."""
    c.execute('SELECT * FROM teacher_advances WHERE advance_id=%s',(advance_id,));a=c.fetchone()
    keep=min(a['legacy_repaid'],new_value)
    if keep!=a['legacy_repaid']:c.execute('UPDATE teacher_advances SET legacy_repaid=%s WHERE advance_id=%s',(keep,advance_id))
    c.execute('SELECT * FROM teacher_advance_settlements WHERE advance_id=%s AND active ORDER BY settlement_id',(advance_id,))
    for r in c.fetchall():
        kept=min(r['amount'],max(ZERO,new_value-keep));keep+=kept;released=r['amount']-kept
        if not released:continue
        if kept:c.execute('UPDATE teacher_advance_settlements SET amount=%s WHERE settlement_id=%s',(kept,r['settlement_id']))
        else:c.execute('UPDATE teacher_advance_settlements SET active=false WHERE settlement_id=%s',(r['settlement_id'],))
        c.execute('UPDATE teacher_payments SET advance=GREATEST(0,advance-%s) WHERE payment_id=%s',(released,r['payment_id']))

def quote(conn,values):
    from live_pages import text
    with conn.cursor() as c:
        A.require(c,'salaries.view');ident=text(values,'teacher',20,True);key=month(text(values,'month',7,True))
        state=data(c,ident);validate_start(state['teacher'],key)
        exclude=values.get('payment')
        if exclude is not None and (type(exclude) is not int or not any(r['payment_id']==exclude for r in state['salaries'])):raise ValueError('عملية الراتب غير موجودة.')
        p=period(state,key)
        return dict(period=dict(**p,**totals(state,p,exclude)),advances=advances(state,exclude),revision=state['revision'],
          teacher=state['teacher']['full_name'],archived=bool(state['teacher']['archived_at']))

def month_keys(first,last):
    y,m=map(int,first.split('-'));end_y,end_m=map(int,last.split('-'))
    while (y,m)<=(end_y,end_m):
        yield f'{y:04}-{m:02}';m+=1
        if m==13:y+=1;m=1

def account(conn,values):
    from live_pages import text
    with conn.cursor() as c:
        A.require(c,'salaries.view');ident=text(values,'teacher',20,True);state=data(c,ident)
    t=state['teacher'];now=today();year=values.get('year',now.year)
    if type(year) is not int or not 1990<=year<=2099:raise ValueError('السنة غير صحيحة.')
    starts=max('1990-01',str(t['hire_date'])[:7]) if t['hire_date'] else min([r['salary_month'] for r in state['months'] if valid_month(r['salary_month'])]+[str(now)[:7]])
    ends=min(str(now)[:7],business_month(t['archived_at'])) if t['archived_at'] else str(now)[:7]
    cash_months={r['salary_month'] for r in state['salaries'] if valid_month(r['salary_month']) and not r['entry_cancelled_at'] and (r['cash_amount'] or r['advance'])}
    invalid_keys={r['salary_month'] for r in state['salaries'] if not valid_month(r['salary_month']) and not r['entry_cancelled_at']}
    keys=sorted(set(month_keys(starts,ends))|{r['salary_month'] for r in state['months'] if valid_month(r['salary_month']) and r['salary_month']>=starts and (not t['archived_at'] or r['salary_month']<=ends)}|cash_months)
    entries=[]
    for key in keys:
        p=period(state,key);s=totals(state,p);y,m=map(int,key.split('-'));due=date(y,m,calendar.monthrange(y,m)[1])
        outside=key<starts or (t['archived_at'] and key>ends)
        status='review' if p['review_required'] or s['overpaid'] or outside else 'none' if not s['entitlement'] else 'paid' if not s['remaining'] else 'partial' if s['settled'] else 'due' if due<=now else 'current'
        entries.append(dict(**p,**s,status=status,due_on=due,revision=R.revision(p)))
    loans=advances(state)
    return dict(revision=state['revision'],year=year,years=sorted({int(k[:4]) for k in keys}|{now.year},reverse=True),
      periods=[p for p in entries if p['salary_month'].startswith(str(year)+'-')],
      summary=dict(paid_months=sum(p['status']=='paid' for p in entries),partial_months=sum(p['status']=='partial' for p in entries),
        overdue=sum((p['remaining'] for p in entries if p['due_on']<=now and p['status']!='review'),ZERO),
        review_months=len(invalid_keys)+sum(p['status']=='review' for p in entries),advance_balance=sum((a['remaining'] for a in loans if not a['review_required']),ZERO),
        review_advances=sum(a['review_required'] and a['remaining']>0 for a in loans),salary_cash=sum((r['cash_amount'] for r in state['salaries']),ZERO)),
      salaries=[dict(**r,id=r['payment_id'],revision=R.revision(r),settlements=[dict(id=s['advance_id'],amount=s['amount']) for s in state['settlements'] if s['active'] and s['payment_id']==r['payment_id']]) for r in state['salaries']],
      advances=[dict(**a,id=a['advance_id']) for a in loans],pages=1,page=1)

def change_month(values,actor):
    from live_pages import text
    ident=text(values,'teacher',20,True);key=month(text(values,'month',7,True));reason=text(values,'reason',2000,True)
    if values.get('confirmed') is not True:raise ValueError('راجع الاستحقاق وأكد التعديل.')
    base,bonus,deductions=[cash(values.get(k,0)) for k in ('base','bonus','deductions')]
    if deductions>base+bonus:raise ValueError('الخصومات أكبر من الراتب والمكافأة.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'salaries.edit',actor);H.context(c,actor,reason);t=teacher(c,ident,lock=True)
            state=data(c,ident);check_revision(state,text(values,'revision',64,True));validate_start(t,key)
            p=period(state,key);p.update(base_salary=base,bonus=bonus,deductions=deductions)
            if totals(state,p)['overpaid']:raise ValueError('الاستحقاق أقل مما سُدد بالفعل؛ صحح الدفعات أو تسديد السلف أولًا.')
            _put_period(c,p)
            c.execute('UPDATE teacher_salary_months SET base_salary=%s,bonus=%s,deductions=%s,review_required=false WHERE national_id=%s AND salary_month=%s',
              (base,bonus,deductions,ident,key))
        conn.commit();return {'ok':True}
    except BaseException:conn.rollback();raise
    finally:conn.close()

def freeze_elapsed(c,t):
    """Salary changes apply to future/unstarted months; prior rates stay fixed."""
    first=max('1990-01',str(t['hire_date'])[:7]) if t.get('hire_date') else str(today())[:7]
    for key in month_keys(first,str(today())[:7]):
        _put_period(c,dict(national_id=t['national_id'],salary_month=key,base_salary=t['salary'] or ZERO,bonus=ZERO,deductions=ZERO))

def adjust_start(c,t,new_start):
    if not new_start or not t['hire_date'] or new_start>=t['hire_date']:return
    end=str(t['hire_date'])[:7]
    for key in month_keys(max('1990-01',str(new_start)[:7]),min(end,str(today())[:7])):
        if key==end:continue
        c.execute('''INSERT INTO teacher_salary_months(national_id,salary_month,base_salary,review_required,source)
          VALUES(%s,%s,%s,true,'date_correction') ON CONFLICT(national_id,salary_month) DO NOTHING''',(t['national_id'],key,t['salary'] or ZERO))

def reconcile(values,actor):
    """Reclassify an explicit old deduction as loan recovery, cash unchanged."""
    from live_pages import text
    ident=text(values,'teacher',20,True);reason=text(values,'reason',2000,True);amount=cash(values.get('amount'))
    if amount<=0 or values.get('confirmed') is not True:raise ValueError('أدخل مبلغ التسوية وأكد أنه خصم سابق، دون صرف جديد.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'salaries.edit',actor);H.context(c,actor,reason);teacher(c,ident,lock=True);state=data(c,ident)
            check_revision(state,text(values,'revision',64,True))
            a=next((a for a in advances(state) if a['advance_id']==values.get('advance')),None)
            p=next((p for p in state['salaries'] if p['payment_id']==values.get('payment')),None)
            unlinked=max(ZERO,(p.get('advance') or ZERO)-sum((s['amount'] for s in state['settlements'] if s['active'] and s['payment_id']==p['payment_id']),ZERO)) if p and not p['managed_month'] else ZERO
            from_advance=bool(unlinked>=amount)
            if not a or not p or p['entry_cancelled_at'] or a['entry_cancelled_at'] or amount>a['remaining']+a['legacy_repaid'] or (not from_advance and amount>p['deductions']):
                raise ValueError('اختر خصمًا سابقًا لنفس المعلم يغطي مبلغ التسوية.')
            month(p['salary_month']);month(a['salary_month'])
            if p['payment_date']<a['advance_date'] or p['salary_month']<a['salary_month']:raise ValueError('لا يمكن خصم سلفة قبل تاريخ صرفها أو شهر تسديدها.')
            monthly=period(state,p['salary_month'])
            if not from_advance and monthly['deductions']<amount:raise ValueError('راجع خصومات استحقاق الشهر أولًا؛ التسوية لا تغيّر النقد.')
            if not from_advance:c.execute('UPDATE teacher_salary_months SET deductions=deductions-%s WHERE month_id=%s',(amount,monthly['month_id']))
            c.execute('UPDATE teacher_payments SET deductions=deductions-%s,advance=advance+%s,managed_month=%s WHERE payment_id=%s',(0 if from_advance else amount,0 if from_advance else amount,unlinked-amount<=0 if from_advance else not unlinked,p['payment_id']))
            c.execute('INSERT INTO teacher_advance_settlements(payment_id,advance_id,amount,national_id) VALUES(%s,%s,%s,%s)',(p['payment_id'],a['advance_id'],amount,ident))
            c.execute('UPDATE teacher_advances SET legacy_repaid=GREATEST(0,legacy_repaid-%s) WHERE advance_id=%s',(amount,a['advance_id']))
            c.execute('''UPDATE teacher_advances a SET review_required=(a.review_required AND a.cash_amount>a.legacy_repaid+
              COALESCE((SELECT SUM(s.amount) FROM teacher_advance_settlements s WHERE s.advance_id=a.advance_id AND s.active),0))
              WHERE advance_id=%s''',(a['advance_id'],))
            sync_advances(c,ident)
        conn.commit();return {'ok':True}
    except BaseException:conn.rollback();raise
    finally:conn.close()

def confirm_advance(values,actor):
    from live_pages import text
    ident=text(values,'teacher',20,True);reason=text(values,'reason',2000,True)
    if values.get('confirmed') is not True:raise ValueError('أكد أن السلفة لم تسدد سابقًا.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'salaries.edit',actor);H.context(c,actor,reason);teacher(c,ident,lock=True);state=data(c,ident)
            check_revision(state,text(values,'revision',64,True))
            c.execute('UPDATE teacher_advances SET review_required=false WHERE national_id=%s AND advance_id=%s AND entry_cancelled_at IS NULL RETURNING advance_id',(ident,values.get('advance')))
            if not c.fetchone():raise ValueError('السلفة غير موجودة.')
        conn.commit();return {'ok':True}
    except BaseException:conn.rollback();raise
    finally:conn.close()

def legacy_status(values,actor):
    from live_pages import text
    ident=text(values,'teacher',20,True);reason=text(values,'reason',2000,True);repaid=cash(values.get('amount'))
    if values.get('confirmed') is not True:raise ValueError('راجع التصحيح وأكده.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'salaries.edit',actor);H.context(c,actor,reason);teacher(c,ident,lock=True);state=data(c,ident)
            check_revision(state,text(values,'revision',64,True))
            a=next((a for a in advances(state) if a['advance_id']==values.get('advance')),None)
            if not a or a['entry_cancelled_at'] or repaid>a['cash_amount']-(a['repaid']-a['legacy_repaid']):raise ValueError('قيمة التسديد السابق أكبر من رصيد السلفة.')
            c.execute('UPDATE teacher_advances SET legacy_repaid=%s,review_required=false WHERE advance_id=%s',(repaid,a['advance_id']))
            sync_advances(c,ident)
        conn.commit();return {'ok':True}
    except BaseException:conn.rollback();raise
    finally:conn.close()

def clear_unlinked(values,actor):
    """Explicitly remove a mistaken old recovery without inventing its lender."""
    from live_pages import text
    ident=text(values,'teacher',20,True);reason=text(values,'reason',2000,True);amount=cash(values.get('amount'))
    if not amount or values.get('confirmed') is not True:raise ValueError('راجع التصحيح وأكده.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'salaries.edit',actor);H.context(c,actor,reason);teacher(c,ident,lock=True);state=data(c,ident)
            check_revision(state,text(values,'revision',64,True))
            p=next((p for p in state['salaries'] if p['payment_id']==values.get('payment')),None)
            linked=sum((s['amount'] for s in state['settlements'] if s['active'] and s['payment_id']==values.get('payment')),ZERO)
            if not p or p['entry_cancelled_at'] or p['managed_month'] or amount>p['advance']-linked:raise ValueError('مبلغ التصحيح أكبر من التسديد القديم غير المرتبط.')
            c.execute('UPDATE teacher_payments SET advance=advance-%s,managed_month=(advance-%s=%s) WHERE payment_id=%s',(amount,amount,linked,p['payment_id']))
        conn.commit();return {'ok':True}
    except BaseException:conn.rollback();raise
    finally:conn.close()
