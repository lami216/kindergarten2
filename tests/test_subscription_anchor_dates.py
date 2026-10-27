"""Registration/service start, collection date and salary period stay distinct."""
from datetime import date, timedelta
import uuid
import pytest

import monthly_finance as F
from tests.test_access_control import access
from tests.test_live_pages_http import browser, intake, login, post


@pytest.mark.parametrize('anchor,paid_on,starts,ends',[
    (date(2026,8,10),date(2026,8,15),
     ['2026-08-10','2026-09-10','2026-10-10','2026-11-10','2026-12-10','2027-01-10'],'2027-02-10'),
    (date(2026,8,10),date(2026,11,15),
     ['2026-08-10','2026-09-10','2026-10-10','2026-11-10','2026-12-10','2027-01-10'],'2027-02-10'),
    (date(2024,1,31),date(2024,2,5),
     ['2024-01-31','2024-02-29','2024-03-31','2024-04-30','2024-05-31','2024-06-30'],'2024-07-31'),
])
def test_delayed_six_month_payment_does_not_move_subscription(browser,monkeypatch,anchor,paid_on,starts,ends):
    client,conn=browser;session=login(client)
    monkeypatch.setattr(F,'today',lambda:anchor)
    created=post(client,session,'students.create',intake(mode='pay',registration=True,gilet=False,amount='1000'))
    assert created.status_code==200,created.text
    student=created.json()['id']
    monkeypatch.setattr(F,'today',lambda:paid_on)
    preview=post(client,session,'payments.preview',dict(student=student,amount='18000',date=str(paid_on)))
    assert preview.status_code==200,preview.text
    data=preview.json()
    assert [month['start'] for month in data['months']]==starts
    assert data['months'][-1]['end']==ends
    saved=post(client,session,'payments.create',dict(student=student,amount='18000',date=str(paid_on),
        revision=data['revision'],tariff=data['tariff'],confirmed=True,request_token=str(uuid.uuid4())))
    assert saved.status_code==200,saved.text
    with conn.cursor() as c:
        c.execute('SELECT start_date FROM monthly_accounts WHERE student_id=%s',(student,))
        assert c.fetchone()['start_date']==anchor
        c.execute('SELECT starts,ends FROM monthly_periods WHERE student_id=%s ORDER BY period_no',(student,))
        periods=c.fetchall()
        assert [str(row['starts']) for row in periods]==starts
        assert str(periods[-1]['ends'])==ends
        c.execute('SELECT received_on,amount FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id',(student,))
        receipts=c.fetchall()
        assert [(row['received_on'],int(row['amount'])) for row in receipts]==[(anchor,1000),(paid_on,18000)]
    before=post(client,session,'reports.finance',dict(start=str(anchor),end=str(paid_on-timedelta(days=1))))
    assert before.status_code==200,before.text
    assert before.json()['summary']['income']==1000
    on_day=post(client,session,'reports.finance',dict(start=str(paid_on),end=str(paid_on)))
    assert on_day.status_code==200,on_day.text
    assert on_day.json()['summary']['income']==18000
    # Correcting the collection date must preserve the original schedule too.
    corrected_day=paid_on+timedelta(days=3)
    monkeypatch.setattr(F,'today',lambda:corrected_day)
    F.correct_receipt(saved.json()['id'],18000,'Correct cash date only',actor='owner',received_on=corrected_day)
    with conn.cursor() as c:
        c.execute('SELECT start_date FROM monthly_accounts WHERE student_id=%s',(student,))
        assert c.fetchone()['start_date']==anchor
        c.execute('SELECT starts FROM monthly_periods WHERE student_id=%s ORDER BY period_no',(student,))
        assert [str(row['starts']) for row in c.fetchall()]==starts


def test_teacher_hire_salary_month_and_disbursement_date_are_independent(browser,monkeypatch):
    client,conn=browser;session=login(client)
    monkeypatch.setattr(F,'today',lambda:date(2026,9,5))
    created=post(client,session,'tools.change',dict(table='teachers',mode='create',reason='Dates QA',confirmed=True,
        request_token=str(uuid.uuid4()),values=dict(full_name='Teacher dates QA',national_id='HIRE-DATE-QA',
        hire_date='2026-08-10',department_id=1,salary='3000')))
    assert created.status_code==200,created.text
    teacher=created.json()['id']
    saved=post(client,session,'payroll.save',dict(kind='salary',teacher=teacher,month='2026-08',date='2026-09-05',
        base='3000',bonus='0',deductions='0',reason='August salary paid in September',confirmed=True,
        request_token=str(uuid.uuid4())))
    assert saved.status_code==200,saved.text
    with conn.cursor() as c:
        c.execute('SELECT hire_date FROM teachers WHERE national_id=%s',(teacher,))
        assert c.fetchone()['hire_date']==date(2026,8,10)
        c.execute('SELECT salary_month,payment_date FROM teacher_payments WHERE payment_id=%s',(saved.json()['id'],))
        row=c.fetchone()
        assert str(row['salary_month'])=='2026-08' and row['payment_date']==date(2026,9,5)
