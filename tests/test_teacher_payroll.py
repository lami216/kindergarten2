"""Month balances, recoveries and reversals through authenticated real HTTP."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from tests.test_live_pages_http import browser,login,post
from tests.test_access_control import access
import access_control as A

def setup_teacher(client,session,hire='2026-09-01'):
    r=post(client,session,'tools.change',dict(table='teachers',mode='create',values=dict(full_name='معلم الرواتب',national_id='SAL-19',salary='2000',hire_date=hire,department_id=1),reason='إعداد اختبار',confirmed=True,request_token=str(uuid.uuid4())))
    assert r.status_code==200,r.text
    return r.json()['id']

def account(c,s,t):return post(c,s,'teachers.finance',{'teacher':t}).json()
def quote(c,s,t,payment=None):return post(c,s,'payroll.quote',dict(teacher=t,month='2026-10',**({'payment':payment} if payment else {}))).json()
def loan(c,s,t,amount=500):
    r=post(c,s,'payroll.save',dict(kind='advance',teacher=t,month='2026-10',date='2026-10-10',amount=str(amount),reason='سلفة اختبار',confirmed=True,request_token=str(uuid.uuid4())))
    assert r.status_code==200,r.text
    return r.json()['id']
def salary(c,s,t,amount,repay=(),q=None,token=None):
    q=q or quote(c,s,t)
    p=q['period']
    return post(c,s,'payroll.save',dict(kind='salary',managed=True,teacher=t,month='2026-10',date='2026-11-02',base=p['base_salary'],bonus=p['bonus'],deductions=p['deductions'],payment_cash=str(amount),settlements=list(repay),account_revision=q['revision'],reason='صرف اختبار',confirmed=True,request_token=token or str(uuid.uuid4())))
def correct(c,s,t,row,kind='salary',**values):
    return post(c,s,'payroll.correct',dict(kind=kind,id=row['id'],revision=row['revision'],account_revision=account(c,s,t)['revision'],reason='تصحيح اختبار',confirmed=True,**values))

def test_salary_with_named_advance_has_one_cash_outflow_and_paid_month(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    r=salary(c,s,t,1500,[{'id':aid,'amount':'500'}]);assert r.status_code==200,r.text
    a=account(c,s,t);p=next(p for p in a['periods'] if p['salary_month']=='2026-10')
    assert (p['cash_paid'],p['recovered'],p['remaining'],p['status'])==(1500,500,0,'paid')
    assert a['advances'][0]['remaining']==0 and a['summary']['salary_cash']==1500
    with conn.cursor() as q:
        q.execute('SELECT SUM(cash_amount) n FROM (SELECT cash_amount FROM teacher_payments UNION ALL SELECT cash_amount FROM teacher_advances) x')
        assert q.fetchone()['n']==2000
    report=post(c,s,'reports.finance',dict(start='2026-10-01',end='2026-11-02')).json()
    assert report['summary']['salary']==1500 and report['summary']['advance']==500 and report['summary']['outgoing']==2000
    assert sum(r['amount'] for r in report['items'] if r['category']!='income')==2000

def test_partial_payments_count_one_month_and_retries_never_duplicate(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t);token=str(uuid.uuid4());q=quote(c,s,t)
    r=salary(c,s,t,300,[{'id':aid,'amount':'200'}],q,token);assert r.status_code==200,r.text
    assert salary(c,s,t,300,[{'id':aid,'amount':'200'}],q,token).json()['created'] is False
    assert account(c,s,t)['summary']['partial_months']==1
    assert salary(c,s,t,1200,[{'id':aid,'amount':'300'}]).status_code==200
    a=account(c,s,t);assert a['summary']['paid_months']==1 and a['summary']['partial_months']==0
    assert salary(c,s,t,1).status_code==422

def test_salary_cancellation_reopens_month_and_advance(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    assert salary(c,s,t,1500,[{'id':aid,'amount':'500'}]).status_code==200
    row=account(c,s,t)['salaries'][0];r=correct(c,s,t,row,cancel=True);assert r.status_code==200,r.text
    a=account(c,s,t);p=next(p for p in a['periods'] if p['salary_month']=='2026-10')
    assert p['remaining']==2000 and a['advances'][0]['remaining']==500 and a['salaries'][0]['cash_amount']==0

@pytest.mark.parametrize('new_amount',[0,200])
def test_advance_correction_reopens_salary_without_changing_paid_salary_cash(browser,new_amount):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    assert salary(c,s,t,1500,[{'id':aid,'amount':'500'}]).status_code==200
    row=account(c,s,t)['advances'][0]
    r=correct(c,s,t,row,'advance',cancel=new_amount==0,amount=str(new_amount),month='2026-10',date='2026-10-10')
    assert r.status_code==200,r.text
    a=account(c,s,t);p=next(p for p in a['periods'] if p['salary_month']=='2026-10')
    assert a['salaries'][0]['cash_amount']==1500 and p['remaining']==500-new_amount and p['recovered']==new_amount

def test_edit_salary_recalculates_recovery_and_preserves_atomic_failure(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    assert salary(c,s,t,1500,[{'id':aid,'amount':'500'}]).status_code==200
    row=account(c,s,t)['salaries'][0]
    r=correct(c,s,t,row,month='2026-10',date='2026-11-02',base='2000',payment_cash='1000',settlements=[{'id':aid,'amount':'500'}]);assert r.status_code==200,r.text
    a=account(c,s,t);row=a['salaries'][0];before=a['revision']
    r=correct(c,s,t,row,month='2026-10',date='2026-10-01',base='2000',payment_cash='1000',settlements=[{'id':aid,'amount':'500'}])
    assert r.status_code==422 and account(c,s,t)['revision']==before

def test_old_window_and_other_teacher_recovery_are_refused(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);q=quote(c,s,t);aid=loan(c,s,t)
    assert salary(c,s,t,100,q=q).status_code==422
    with browser[1].cursor() as cur:cur.execute("INSERT INTO teachers(national_id,full_name,salary) VALUES('OTHER','معلم آخر',2000)")
    assert salary(c,s,'OTHER',1500,[{'id':aid,'amount':'500'}]).status_code==422

def test_month_and_cash_date_before_hire_are_refused(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s)
    q=post(c,s,'payroll.quote',dict(teacher=t,month='2026-08'));assert q.status_code==422
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-08',date='2026-11-02',base='2000',reason='غير صحيح',confirmed=True,request_token=str(uuid.uuid4())))
    assert r.status_code==422

def test_reconcile_historic_manual_deduction_preserves_cash(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-10',date='2026-11-02',base='2000',deductions='500',reason='خصم قديم',confirmed=True,request_token=str(uuid.uuid4())))
    assert r.status_code==200,r.text
    with conn.cursor() as cur:cur.execute('UPDATE teacher_advances SET review_required=true WHERE advance_id=%s',(aid,))
    a=account(c,s,t)
    r=post(c,s,'payroll.reconcile',dict(teacher=t,advance=aid,payment=a['salaries'][0]['id'],amount='500',revision=a['revision'],reason='هذا الخصم سدد السلفة سابقًا',confirmed=True))
    assert r.status_code==200,r.text
    a=account(c,s,t);assert a['salaries'][0]['cash_amount']==1500 and a['advances'][0]['remaining']==0
    p=next(p for p in a['periods'] if p['salary_month']=='2026-10');assert p['remaining']==0 and p['entitlement']==2000

def test_document_void_does_not_reopen_paid_month(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);assert salary(c,s,t,2000).status_code==200
    a=account(c,s,t);row=a['salaries'][0]
    r=post(c,s,'tools.change',dict(table='teacher_payments',mode='void_document',id=row['id'],revision=row['revision'],reason='مستند فقط',confirmed=True))
    assert r.status_code==200,r.text
    a=account(c,s,t);assert a['summary']['paid_months']==1 and a['summary']['salary_cash']==2000

def test_month_edit_cannot_erase_existing_settlement(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);assert salary(c,s,t,1000).status_code==200
    a=account(c,s,t)
    r=post(c,s,'payroll.month',dict(teacher=t,month='2026-10',base='800',bonus=0,deductions=0,revision=a['revision'],reason='خطأ',confirmed=True))
    assert r.status_code==422

def test_teacher_salary_change_preserves_elapsed_months(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);snapshot=c.get('/api/snapshot').json();teacher=snapshot['teachers'][0]
    r=post(c,s,'tools.change',dict(table='teachers',mode='edit',id=t,revision=teacher['revision'],values={'salary':'3000'},reason='راتب جديد',confirmed=True))
    assert r.status_code==200,r.text
    a=account(c,s,t);assert next(p for p in a['periods'] if p['salary_month']=='2026-10')['base_salary']==2000

def test_two_operators_cannot_overpay_one_remaining_balance(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);assert salary(c,s,t,1000).status_code==200
    q=quote(c,s,t)
    with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda _:salary(c,s,t,600,q=q),range(2)))
    assert sorted(r.status_code for r in responses)==[200,422]
    p=next(p for p in account(c,s,t)['periods'] if p['salary_month']=='2026-10')
    assert p['settled']==1600 and p['remaining']==400

def test_salary_fully_settled_from_advance_creates_no_new_cash(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t,2000)
    r=salary(c,s,t,0,[{'id':aid,'amount':'2000'}]);assert r.status_code==200,r.text
    a=account(c,s,t);assert a['summary']['paid_months']==1 and a['summary']['salary_cash']==0 and a['advances'][0]['remaining']==0

def test_view_only_worker_cannot_change_month_or_recoveries(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s)
    A.save_user(employee_name='قارئ الرواتب',name='salary_viewer',password='1234',permissions=['salaries.view'])
    worker=login(c,'salary_viewer','1234');before=account(c,worker,t)
    r=post(c,worker,'payroll.month',dict(teacher=t,month='2026-10',base='10',bonus=0,deductions=0,revision=before['revision'],reason='محاولة ممنوعة',confirmed=True));assert r.status_code==403
    assert salary(c,worker,t,100).status_code==403 and account(c,worker,t)['revision']==before['revision']

def test_archive_invalidates_prepared_salary(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);q=quote(c,s,t);teacher=c.get('/api/snapshot').json()['teachers'][0]
    r=post(c,s,'tools.change',dict(table='teachers',mode='cancel',id=t,revision=teacher['revision'],reason='أرشفة اختبار',confirmed=True));assert r.status_code==200,r.text
    assert salary(c,s,t,2000,q=q).status_code==422

def test_salary_pdf_is_private_and_bilingual(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);r=salary(c,s,t,1000);assert r.status_code==200
    for lang in ('ar','fr'):
        pdf=c.post('/api/payroll.pdf',json={'id':r.json()['id']},headers={'Origin':'https://kindergarten.test','X-CSRF-Token':s['csrf'],'X-App-Language':lang})
        assert pdf.status_code==200 and pdf.content.startswith(b'%PDF') and len(pdf.content)>5000
    A.save_user(employee_name='عامل بلا رواتب',name='no_payroll',password='1234',permissions=['students.view'])
    w=login(c,'no_payroll','1234');assert post(c,w,'payroll.pdf',{'id':r.json()['id']}).status_code==403

def test_advance_date_cannot_move_past_its_recoveries(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    assert salary(c,s,t,1500,[{'id':aid,'amount':'500'}]).status_code==200
    a=account(c,s,t)
    r=correct(c,s,t,a['advances'][0],'advance',amount='500',date='2026-11-03',month='2026-11')
    assert r.status_code==422 and account(c,s,t)['revision']==a['revision']

def test_upgrade_preserves_historic_cash_and_flags_ambiguous_legacy_deductions(browser,access):
    import schema_migrations as M
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-10',date='2026-11-02',base='2000',deductions='500',reason='سجل قديم',confirmed=True,request_token=str(uuid.uuid4())));assert r.status_code==200
    with conn.cursor() as q:
        q.execute("INSERT INTO teachers(national_id,full_name,salary,hire_date) VALUES('BROKEN','معلم سجل غير مطابق',2000,'2026-09-01')")
        q.execute("INSERT INTO teacher_payments(national_id,salary_month,payment_date,base_salary,amount,cash_amount) VALUES('BROKEN','2026-10','2026-11-02',2000,2500,2500)")
        q.execute('SELECT password_hash,permissions FROM app_users ORDER BY username');users=q.fetchall()
        q.execute('''DROP TABLE teacher_advance_settlements; DROP TABLE teacher_salary_months;
          ALTER TABLE teacher_payments DROP COLUMN managed_month;
          ALTER TABLE teacher_advances DROP COLUMN legacy_repaid,DROP COLUMN review_required;
          DELETE FROM app_schema_migrations WHERE version=19;
          INSERT INTO app_schema_migrations(version) VALUES(18) ON CONFLICT DO NOTHING''')
    migration=access[1]();assert M.upgrade(migration);assert not M.upgrade(migration);migration.close()
    a=account(c,s,t);assert a['salaries'][0]['cash_amount']==1500 and a['advances'][0]['cash_amount']==500
    assert a['advances'][0]['review_required'] and a['summary']['review_months']>=1 and a['summary']['advance_balance']==0
    assert next(p for p in a['periods'] if p['salary_month']=='2026-10')['status']=='paid'
    broken=account(c,s,'BROKEN');p=next(p for p in broken['periods'] if p['salary_month']=='2026-10')
    assert broken['summary']['salary_cash']==2500 and p['base_salary']==2000 and p['overpaid']==500 and p['status']=='review'
    response=correct(c,s,'BROKEN',broken['salaries'][0],month='2026-10',date='2026-11-02',base='2000',payment_cash='2000',settlements=[])
    assert response.status_code==200,response.text
    fixed=account(c,s,'BROKEN');response=post(c,s,'payroll.month',dict(teacher='BROKEN',month='2026-10',base='2000',bonus=0,deductions=0,revision=fixed['revision'],reason='تأكيد الاستحقاق بعد تصحيح الخطأ',confirmed=True))
    assert response.status_code==200,response.text
    assert account(c,s,'BROKEN')['summary']['paid_months']==1
    with conn.cursor() as q:
        q.execute('SELECT password_hash,permissions FROM app_users ORDER BY username');assert q.fetchall()==users

def test_generic_editor_cannot_reinterpret_a_managed_partial_salary(browser):
    import payroll_finance as P
    c,_=browser;s=login(c);t=setup_teacher(c,s);assert salary(c,s,t,500).status_code==200
    a=account(c,s,t);r=a['salaries'][0]
    response=post(c,s,'tools.change',dict(table='teacher_payments',mode='edit',id=r['id'],revision=r['revision'],values=dict(salary_month='2026-10',payment_date='2026-11-02',base_salary='2000',bonus=0,deductions=0),reason='محرر عام',confirmed=True))
    assert response.status_code==422 and account(c,s,t)['revision']==a['revision']

def test_partial_historic_reconciliation_does_not_assume_rest_is_unpaid(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t,700)
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-10',date='2026-11-02',base='2000',deductions='500',reason='خصم قديم',confirmed=True,request_token=str(uuid.uuid4())));assert r.status_code==200
    with conn.cursor() as cur:cur.execute('UPDATE teacher_advances SET review_required=true WHERE advance_id=%s',(aid,))
    a=account(c,s,t)
    r=post(c,s,'payroll.reconcile',dict(teacher=t,advance=aid,payment=a['salaries'][0]['id'],amount='500',revision=a['revision'],reason='تسديد قديم جزئي',confirmed=True));assert r.status_code==200,r.text
    a=account(c,s,t);assert a['advances'][0]['remaining']==200 and a['advances'][0]['review_required'] and a['summary']['advance_balance']==0

def test_payer_without_edit_permission_can_recover_advance_and_flag_is_consistent(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    A.save_user(employee_name='صارف الرواتب',name='salary_payer',password='1234',permissions=['salaries.create'])
    w=login(c,'salary_payer','1234');r=salary(c,w,t,1500,[{'id':aid,'amount':'500'}]);assert r.status_code==200,r.text
    a=account(c,w,t);assert a['advances'][0]['is_deducted'] and a['advances'][0]['remaining']==0
    assert correct(c,w,t,a['salaries'][0],cancel=True).status_code==403

def test_known_legacy_repayment_can_be_linked_then_cancelled_without_guessing_month(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);aid=loan(c,s,t)
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-10',date='2026-11-02',base='2000',reason='سجل سابق',confirmed=True,request_token=str(uuid.uuid4())));assert r.status_code==200
    with conn.cursor() as q:
        q.execute('UPDATE teacher_payments SET amount=1500,cash_amount=1500,advance=500,managed_month=false WHERE payment_id=%s',(r.json()['id'],))
        q.execute('UPDATE teacher_advances SET legacy_repaid=500,is_deducted=true WHERE advance_id=%s',(aid,))
    a=account(c,s,t);assert a['summary']['paid_months']==1 and a['advances'][0]['remaining']==0
    assert correct(c,s,t,a['advances'][0],'advance',cancel=True).status_code==422
    response=post(c,s,'payroll.reconcile',dict(teacher=t,advance=aid,payment=r.json()['id'],amount='500',revision=a['revision'],reason='ربط التسديد السابق',confirmed=True));assert response.status_code==200,response.text
    a=account(c,s,t);assert a['advances'][0]['legacy_repaid']==0 and a['advances'][0]['is_deducted']
    assert correct(c,s,t,a['salaries'][0],cancel=True).status_code==200
    a=account(c,s,t);assert a['advances'][0]['remaining']==500 and not a['advances'][0]['is_deducted']

def test_wrong_unlinked_historical_recovery_has_explicit_audited_correction(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s)
    r=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month='2026-10',date='2026-11-02',base='2000',reason='سجل سابق',confirmed=True,request_token=str(uuid.uuid4())));assert r.status_code==200
    with conn.cursor() as q:q.execute('UPDATE teacher_payments SET amount=1500,cash_amount=1500,advance=500,managed_month=false WHERE payment_id=%s',(r.json()['id'],))
    a=account(c,s,t)
    response=post(c,s,'payroll.clear-unlinked',dict(teacher=t,payment=r.json()['id'],amount='500',revision=a['revision'],reason='ثبت أن التسديد القديم خطأ',confirmed=True));assert response.status_code==200,response.text
    a=account(c,s,t);assert a['salaries'][0]['cash_amount']==1500 and a['salaries'][0]['advance']==0
    assert next(p for p in a['periods'] if p['salary_month']=='2026-10')['remaining']==500

def test_correcting_hire_date_does_not_create_debt_before_employment(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s);teacher=c.get('/api/snapshot').json()['teachers'][0]
    r=post(c,s,'tools.change',dict(table='teachers',mode='edit',id=t,revision=teacher['revision'],values={'hire_date':'2026-11-01'},reason='تصحيح بداية العمل',confirmed=True));assert r.status_code==200,r.text
    a=account(c,s,t);assert [p['salary_month'] for p in a['periods']]==['2026-11'] and a['summary']['overdue']==0

def test_teacher_view_does_not_reveal_salary_without_money_permission(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s)
    A.save_user(employee_name='عارض ملفات المعلمين',name='teacher_viewer',password='1234',permissions=['teachers.view'])
    w=login(c,'teacher_viewer','1234');snapshot=c.get('/api/snapshot').json();row=snapshot['teachers'][0]
    assert row['salary'] is None and 'salary' not in row['values']
    tools=post(c,w,'tools.list',dict(table='teachers',page=1)).json();assert 'salary' not in tools['items'][0]['values']
    assert post(c,w,'teachers.finance',{'teacher':t}).status_code==403

def test_first_month_is_full_even_when_employment_starts_midmonth(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s,'2026-10-15');q=quote(c,s,t)
    assert q['period']['entitlement']==2000 and salary(c,s,t,2000).status_code==200

def test_large_advance_carries_over_months_without_negative_cash_or_double_expense(browser):
    c,_=browser;s=login(c);t=setup_teacher(c,s)
    r=post(c,s,'payroll.save',dict(kind='advance',teacher=t,month='2026-09',date='2026-09-10',amount='5000',reason='سلفة كبيرة',confirmed=True,request_token=str(uuid.uuid4())));assert r.status_code==200
    aid=r.json()['id']
    for key,recovered,paid in [('2026-09',2000,0),('2026-10',2000,0),('2026-11',1000,1000)]:
        q=post(c,s,'payroll.quote',dict(teacher=t,month=key)).json()
        response=post(c,s,'payroll.save',dict(kind='salary',teacher=t,month=key,date='2026-11-02',managed=True,base='2000',payment_cash=str(paid),settlements=[{'id':aid,'amount':str(recovered)}],account_revision=q['revision'],reason='تسديد السلفة تدريجيًا',confirmed=True,request_token=str(uuid.uuid4())))
        assert response.status_code==200,response.text
    a=account(c,s,t);assert a['summary']['paid_months']==3 and a['summary']['salary_cash']==1000 and a['advances'][0]['remaining']==0
    report=post(c,s,'reports.finance',dict(start='2026-09-01',end='2026-11-02')).json();assert report['summary']['outgoing']==6000

def test_bad_legacy_month_keeps_file_and_cash_readable_until_audited_correction(browser):
    c,conn=browser;s=login(c);t=setup_teacher(c,s);r=salary(c,s,t,2000);assert r.status_code==200
    with conn.cursor() as q:q.execute("UPDATE teacher_payments SET salary_month='أكتوبر' WHERE payment_id=%s",(r.json()['id'],))
    a=account(c,s,t);assert a['summary']['review_months']==1 and a['summary']['salary_cash']==2000
    pdf=post(c,s,'payroll.pdf',{'id':r.json()['id']});assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    response=correct(c,s,t,a['salaries'][0],month='2026-10',date='2026-11-02',base='2000',payment_cash='2000',settlements=[])
    assert response.status_code==200,response.text
    a=account(c,s,t);assert a['summary']['review_months']==0 and a['summary']['paid_months']==1 and a['summary']['salary_cash']==2000

