"""Financial contract regression on isolated PostgreSQL 16; no live databases."""
import os
import uuid
import unittest
from datetime import date
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor

import db
import monthly_finance as F

DSN=os.environ.get("TEST_POSTGRES_DSN")


def connect():
    connection=psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    connection.autocommit=False
    return connection


@unittest.skipUnless(DSN,"Disposable PostgreSQL required")
class SingleCurrencyCashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=connect()
        cls.admin.autocommit=True
        cls.override=patch.object(db,"new_transaction_connection",side_effect=connect)
        cls.override.start()
        with patch.object(db,"get_connection",return_value=cls.admin):
            db.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.override.stop()
        cls.admin.close()

    def setUp(self):
        F.update_tariffs(1000,2000,3000,"synthetic-test")
        self.day=date(2024,7,16)
        self.tomorrow=date(2024,7,17)
        self.family=dict(father_name="",father_mobile="",mother_name="أم نقدية",
                         mother_mobile="0599002024",contact_email="")
        self.child=dict(full_name="طفل "+uuid.uuid4().hex[:8],
                        birth_date=date(2021,5,3),gender="ذكر",birth_place="",
                        address="",medical_details="",allergies="",
                        general_notes="",authorized_pickups=[])

    def register(self,*,cash=0,registration=False,gilet=False,mode="regular"):
        options=dict(mode=mode,cash=cash,registration=registration,gilet=gilet,
                     start_date=self.day.isoformat(),payer="أم نقدية")
        with patch.object(F,"today",return_value=self.day):
            sid,_=db.save_child_with_family(self.child,self.family,None,
                str(uuid.uuid4()),finance=options,actor="fixture")
        return sid

    def report(self,start=None,end=None):
        return F.financial_report(self.admin,start or self.day,end or self.tomorrow)

    def test_cash_12000_then_expense_2000_then_monthly_6000_and_cancel(self):
        baseline=self.report()
        sid=self.register(cash=12000,registration=True,gilet=True)
        p=self.report()
        self.assertEqual(p["total_cash"]-baseline["total_cash"],12000)
        self.assertEqual(p["registration_cash"]-baseline["registration_cash"],1000)
        self.assertEqual(p["gilet_cash"]-baseline["gilet_cash"],2000)
        self.assertEqual(p["monthly_cash"]-baseline["monthly_cash"],9000)
        self.assertEqual(p["registration_children"]-baseline["registration_children"],1)
        self.assertEqual(p["gilet_count"]-baseline["gilet_count"],1)
        self.assertEqual(p["prepaid_cash"]-baseline["prepaid_cash"],6000)
        self.assertEqual(p["expenses"],baseline["expenses"])
        with self.admin.cursor() as c:
            c.execute("""INSERT INTO expenses(expense_date,category,amount,amount_paid)
                         VALUES(%s,'اختبار نقدي',2000,2000)""",(self.day,))
        after_exp=self.report()
        self.assertEqual(after_exp["expenses"]-baseline["expenses"],2000)
        self.assertEqual(after_exp["remaining_cash"]-baseline["remaining_cash"],10000)
        rid,_=F.take_payment(sid,6000,as_of=self.tomorrow,actor="fixture")
        after_month=self.report()
        self.assertEqual(after_month["total_cash"]-baseline["total_cash"],18000)
        self.assertEqual(after_month["remaining_cash"]-baseline["remaining_cash"],16000)
        with self.admin.cursor() as c:
            c.execute("""SELECT DISTINCT p.period_no FROM monthly_allocations a
                   JOIN monthly_periods p ON p.period_id=a.period_id
                   WHERE a.receipt_id=%s ORDER BY p.period_no""",(rid,))
            self.assertEqual([r["period_no"] for r in c.fetchall()],[3,4])
        F.cancel_receipt(rid,"اختبار إلغاء",actor="fixture")
        after_cancel=self.report()
        self.assertEqual(after_cancel["total_cash"]-baseline["total_cash"],12000)
        self.assertEqual(after_cancel["remaining_cash"]-baseline["remaining_cash"],10000)
        with self.admin.cursor() as c:
            c.execute("""SELECT COUNT(*) AS n FROM monthly_allocations
                         WHERE receipt_id=%s AND active""",(rid,))
            self.assertEqual(c.fetchone()["n"],0)

    def test_partial_receipts_and_date_boundaries(self):
        baseline=self.report(self.day,self.day)
        sid=self.register(cash=1500,registration=True)
        first=self.report(self.day,self.day)
        self.assertEqual(first["total_cash"]-baseline["total_cash"],1500)
        self.assertEqual(first["registration_cash"]-baseline["registration_cash"],1000)
        self.assertEqual(first["monthly_cash"]-baseline["monthly_cash"],500)
        self.assertEqual(first["registration_children"]-baseline["registration_children"],1)
        F.take_payment(sid,2500,as_of=self.tomorrow,actor="fixture")
        day1=self.report(self.day,self.day)
        day2=self.report(self.tomorrow,self.tomorrow)
        self.assertEqual(day1["total_cash"]-baseline["total_cash"],1500)
        self.assertGreaterEqual(day2["total_cash"],2500)
        self.assertEqual(F.projection(self.admin,sid,self.tomorrow)["periods"][0]["paid"],3000)
        self.assertEqual(F.projection(self.admin,sid,self.tomorrow)["periods"][1]["paid"],1000)

    def test_advances_salary_and_explicitly_linked_mirror_not_double_counted(self):
        baseline=self.report()
        teacher="T"+uuid.uuid4().hex[:19]
        with self.admin.cursor() as c:
            c.execute("INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,5000)",
                      (teacher,"معلمة مالية تجريبية"))
            c.execute("""INSERT INTO teacher_advances(national_id,amount,advance_date,
                           salary_month,is_deducted) VALUES(%s,1000,%s,'2024-07',TRUE)""",
                      (teacher,self.day))
            c.execute("""INSERT INTO teacher_payments(national_id,amount,payment_date,salary_month,
                           base_salary,bonus,deductions,advance)
                           VALUES(%s,3000,%s,'2024-07',4000,0,1000,1000)
                           RETURNING payment_id""",(teacher,self.tomorrow))
            pid=c.fetchone()["payment_id"]
            c.execute("""INSERT INTO expenses(expense_date,category,amount,amount_paid,
                           teacher_payment_id) VALUES(%s,'صورة صرف راتب',3000,3000,%s)""",
                      (self.tomorrow,pid))
        now=self.report()
        self.assertEqual(now["salary_cash"]-baseline["salary_cash"],3000)
        self.assertEqual(now["advance_cash"]-baseline["advance_cash"],1000)
        self.assertEqual(now["operational_cash"],baseline["operational_cash"])
        self.assertEqual(now["expenses"]-baseline["expenses"],4000)
        self.assertEqual(self.report(self.day,self.day)["advance_cash"]-
                         F.financial_report(self.admin,self.day,self.day)["advance_cash"],0)
        self.assertEqual(self.report(self.tomorrow,self.tomorrow)["salary_cash"]-
                         F.financial_report(self.admin,self.tomorrow,self.tomorrow)["salary_cash"],0)
        # Unpaid entitlement is never reported as spent cash.
        with self.admin.cursor() as c:
            c.execute("UPDATE teachers SET salary=9000 WHERE national_id=%s",(teacher,))
        self.assertEqual(self.report()["expenses"],now["expenses"])

    def test_expense_later_settlement_retains_original_cash_date(self):
        day=self.day
        before=self.report(day,day)
        with self.admin.cursor() as c:
            c.execute("""INSERT INTO expenses(expense_date,category,amount,amount_paid)
                         VALUES(%s,'تسديد لاحق',2000,500) RETURNING expense_id""",(day,))
            exp=c.fetchone()["expense_id"]
        self.assertEqual(self.report(day,day)["operational_cash"]-
                         before["operational_cash"],500)
        with self.admin.cursor() as c:
            c.execute("UPDATE expenses SET amount_paid=1500 WHERE expense_id=%s",(exp,))
        self.assertEqual(self.report(day,day)["operational_cash"]-
                         before["operational_cash"],500)
        today_report=self.report(F.today(),F.today())
        self.assertGreaterEqual(today_report["operational_cash"],1000)
        with self.admin.cursor() as c:
            c.execute("SELECT amount,event_date,source FROM expense_cash_events WHERE expense_id=%s ORDER BY event_id",(exp,))
            events=c.fetchall()
        self.assertEqual([int(e["amount"]) for e in events],[500,1000])
        self.assertEqual(events[0]["event_date"],day)
        self.assertEqual(events[1]["event_date"],F.today())
        F.migrate(self.admin)
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM expense_cash_events WHERE expense_id=%s",(exp,))
            self.assertEqual(c.fetchone()["n"],2)

    def test_explicit_setup_regular_exempt_idempotent_and_no_fake_receipt(self):
        sid,_=db.save_child_with_family(self.child,self.family,None,str(uuid.uuid4()))
        proposal=F.account_setup_suggestion(self.admin,sid)
        self.assertFalse(proposal["already_set"])
        self.assertFalse(proposal["legacy_funded"])
        self.assertIsNone(proposal["registered_on"])
        self.assertEqual(proposal["created_on"],F.today())
        before=None
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,))
            before=c.fetchone()["n"]
        self.assertTrue(F.initialize_existing_account(sid,self.day,"regular",True,actor="tester"))
        self.assertFalse(F.initialize_existing_account(sid,self.day,"regular",True,actor="tester"))
        with self.assertRaises(ValueError):
            F.initialize_existing_account(sid,self.tomorrow,"exempt",True,actor="tester")
        account=F.projection(self.admin,sid,self.day)
        self.assertEqual(account["fees"]["registration"]["price"],1000)
        self.assertEqual(account["fees"]["registration"]["paid"],0)
        self.assertEqual(account["receipts"],[])
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,))
            self.assertEqual(c.fetchone()["n"],before)
        self.child["full_name"]+=" معفى"
        exempt_sid,_=db.save_child_with_family(self.child,self.family,None,str(uuid.uuid4()))
        self.assertTrue(F.initialize_existing_account(exempt_sid,self.day,"exempt",True))
        exempt=F.projection(self.admin,exempt_sid,self.day)
        self.assertTrue(exempt["exempt"])
        self.assertEqual(exempt["receipts"],[])
        self.assertEqual(exempt["fees"],{})
