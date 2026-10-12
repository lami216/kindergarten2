"""Isolated PostgreSQL 16 contract cases; no SQLite, live DB or test tariffs on production."""
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
import uuid
import unittest
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
import db
import monthly_finance as F

DSN = os.getenv("TEST_POSTGRES_DSN")


def connect():
    c=psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    c.autocommit=False
    return c


@unittest.skipUnless(DSN, "isolated PostgreSQL required")
class MonthlyFinanceDBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=connect()
        cls.admin.autocommit=True
        cls.patcher=patch.object(db,"new_transaction_connection",side_effect=connect)
        cls.patcher.start()
        with patch.object(db,"get_connection",return_value=cls.admin):
            db.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.admin.close()

    def setUp(self):
        F.update_tariffs(1000,2000,3000,"fixture")
        self.family={"father_name":"","father_mobile":"","mother_name":"أم شهرية",
                     "mother_mobile":"0599000123","contact_email":""}
        self.child={"full_name":"طفل مالي "+uuid.uuid4().hex[:8],
                    "birth_date":date(2022,1,5),"gender":"ذكر","birth_place":"",
                    "address":"","medical_details":"","allergies":"",
                    "general_notes":"","authorized_pickups":[]}
        self.anchor=date(2026,1,31)

    def create(self,mode="regular",cash=0,reg=False,gilet=False,existing=None):
        opt={"mode":mode,"cash":cash,"registration":reg,"gilet":gilet,
             "start_date":self.anchor.isoformat(),"payer":"أم شهرية"}
        sid,new=db.save_child_with_family(self.child,self.family,existing,
                                          str(uuid.uuid4()),finance=opt,actor="tester")
        self.assertTrue(new)
        return sid

    def projection(self,sid,as_of=date(2026,4,30)):
        return F.projection(self.admin,sid,as_of)

    def count(self,table):
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM "+table)
            return c.fetchone()["n"]

    def test_unpaid_regular_has_registration_due_but_no_gilet(self):
        sid=self.create()
        p=self.projection(sid,self.anchor)
        self.assertEqual(p["fees"]["registration"],{"price":1000,"paid":0})
        self.assertNotIn("gilet",p["fees"])
        self.assertEqual(len(p["receipts"]),0)
        self.assertEqual(p["due_now"],4000)

    def test_full_exemption_no_income_no_future_periods(self):
        sid=self.create(mode="exempt")
        p=self.projection(sid,date(2028,12,31))
        self.assertTrue(p["exempt"])
        self.assertEqual(p["fees"],{})
        self.assertEqual(p["periods"],[])
        self.assertEqual(p["due_now"],0)
        with self.assertRaisesRegex(ValueError,"معفي"):
            F.take_payment(sid,500,actor="tester")
        with self.admin.cursor() as c:
            c.execute("SELECT action FROM monthly_audit WHERE student_id=%s",(sid,))
            self.assertIn("exemption",[x["action"] for x in c.fetchall()])

    def test_12000_exact_single_receipt_three_periods(self):
        sid=self.create(cash=12000,reg=True,gilet=True)
        p=self.projection(sid,self.anchor)
        self.assertEqual(len(p["receipts"]),1)
        self.assertEqual(p["paid_periods"],3)
        self.assertEqual([x["paid"] for x in p["periods"][:3]],[3000,3000,3000])
        self.assertEqual(p["fees"]["registration"]["paid"],1000)
        self.assertEqual(p["fees"]["gilet"]["paid"],2000)
        with self.admin.cursor() as c:
            c.execute("""SELECT CASE WHEN a.fee_id IS NOT NULL THEN f.kind ELSE 'month' END AS kind,
                          SUM(a.amount) AS amount FROM monthly_allocations a
                          LEFT JOIN monthly_fees f ON f.fee_id=a.fee_id
                          JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
                          WHERE r.student_id=%s AND a.active GROUP BY 1""",(sid,))
            total={x["kind"]:int(x["amount"]) for x in c.fetchall()}
        self.assertEqual(total,{"registration":1000,"gilet":2000,"month":9000})

    def test_11000_keeps_partial_future_period(self):
        sid=self.create(cash=11000,reg=True,gilet=True)
        p=self.projection(sid,self.anchor)
        self.assertEqual([x["paid"] for x in p["periods"]],[3000,3000,2000])
        self.assertEqual(p["paid_periods"],2)
        self.assertEqual(p["future_partial"],1000)
        self.assertEqual(p["due_now"],0)

    def test_underfunded_selected_items_roll_back_everything(self):
        previous=[self.count(t) for t in ("parents","students","monthly_accounts",
                                           "monthly_receipts")]
        with self.assertRaisesRegex(ValueError,"المبلغ"):
            self.create(cash=2999,reg=True,gilet=True)
        self.assertEqual(previous,[self.count(t) for t in
                         ("parents","students","monthly_accounts","monthly_receipts")])

    def test_month_only_initial_keeps_registration_due(self):
        sid=self.create(cash=3000)
        p=self.projection(sid,self.anchor)
        self.assertEqual(p["paid_periods"],1)
        self.assertEqual(p["fees"]["registration"]["paid"],0)
        self.assertEqual(p["due_now"],1000)

    def test_later_payment_skips_three_paid_months(self):
        sid=self.create(cash=12000,reg=True,gilet=True)
        rid,new=F.take_payment(sid,6000,as_of=date(2026,4,30),token=uuid.uuid4(),actor="tester")
        self.assertTrue(new)
        with self.admin.cursor() as c:
            c.execute("""SELECT p.period_no FROM monthly_allocations a
                JOIN monthly_periods p ON p.period_id=a.period_id
                WHERE a.receipt_id=%s ORDER BY period_no""",(rid,))
            self.assertEqual([r["period_no"] for r in c.fetchall()],[3,4])
        self.assertEqual(self.projection(sid)["paid_periods"],5)

    def test_partial_1500_then_4500_completes_four_before_five(self):
        sid=self.create(cash=12000,reg=True,gilet=True)
        r1,_=F.take_payment(sid,1500,as_of=date(2026,4,30),actor="tester")
        r2,_=F.take_payment(sid,4500,as_of=date(2026,4,30),actor="tester")
        with self.admin.cursor() as c:
            c.execute("""SELECT r.receipt_id,p.period_no,a.amount
                FROM monthly_allocations a
                JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
                JOIN monthly_periods p ON p.period_id=a.period_id
                WHERE r.receipt_id IN (%s,%s) ORDER BY r.receipt_id,p.period_no""",(r1,r2))
            result=[(x["receipt_id"],x["period_no"],x["amount"]) for x in c.fetchall()]
        self.assertEqual(result,[(r1,3,1500),(r2,3,1500),(r2,4,3000)])

    def test_schedule_anniversary_31_and_leap_year(self):
        a=date(2024,1,31)
        self.assertEqual(F.anniversary(a,1),date(2024,2,29))
        self.assertEqual(F.anniversary(a,2),date(2024,3,31))
        self.assertEqual(F.anniversary(date(2023,1,31),1),date(2023,2,28))
        self.assertEqual(F.anniversary(date(2023,1,31),2),date(2023,3,31))
        self.assertEqual(F.anniversary(a,13),date(2025,2,28))

    def test_tariff_change_keeps_existing_period_and_receipt_snapshots(self):
        sid=self.create(cash=6000)
        original=self.projection(sid,date(2026,2,28))
        F.update_tariffs(9000,8000,7000,"change")
        current=self.projection(sid,date(2026,3,31))
        self.assertEqual([x["price"] for x in current["periods"][:2]],[3000,3000])
        self.assertEqual(current["fees"]["registration"]["price"],1000)
        self.assertEqual(current["receipts"][0]["amount"],6000)
        self.assertEqual(current["periods"][2]["price"],7000)

    def test_repeated_token_and_conflicting_retry(self):
        sid=self.create()
        token=uuid.uuid4()
        a,new=F.take_payment(sid,1500,token=token,actor="tester")
        b,again=F.take_payment(sid,1500,token=token,actor="tester")
        self.assertEqual((a,new),(b,not again))
        with self.assertRaisesRegex(ValueError,"تعارض"):
            F.take_payment(sid,1600,token=token,actor="tester")

    def test_cancel_reopens_earliest_unpaid_and_keeps_audit(self):
        sid=self.create(cash=9000)
        first_id=self.projection(sid,self.anchor)["receipts"][0]["receipt_id"]
        F.cancel_receipt(first_id,"مدخل مكرر",actor="tester")
        p=self.projection(sid,self.anchor)
        self.assertEqual(p["paid_periods"],0)
        self.assertEqual(p["due_now"],4000)
        with self.admin.cursor() as c:
            c.execute("SELECT state,amount,cancelled_by,cancel_reason FROM monthly_receipts WHERE receipt_id=%s",
                      (first_id,))
            self.assertEqual(c.fetchone()["state"],"cancelled")
            c.execute("SELECT COUNT(*) AS n FROM monthly_audit WHERE receipt_id=%s AND action='receipt_cancelled'",
                      (first_id,))
            self.assertEqual(c.fetchone()["n"],1)
        next_id,_=F.take_payment(sid,3000,actor="tester")
        with self.admin.cursor() as c:
            c.execute("""SELECT p.period_no FROM monthly_allocations a JOIN monthly_periods p
              ON p.period_id=a.period_id WHERE a.receipt_id=%s""",(next_id,))
            self.assertEqual(c.fetchone()["period_no"],0)

    def test_correction_reapplies_allocations_atomically(self):
        sid=self.create(cash=6000)
        old_id=self.projection(sid,self.anchor)["receipts"][0]["receipt_id"]
        new_id,_=F.correct_receipt(old_id,4500,"كتابة خاطئة",actor="tester")
        p=self.projection(sid,self.anchor)
        self.assertEqual(p["paid_periods"],1)
        self.assertEqual(p["periods"][1]["paid"],1500)
        self.assertEqual([r["state"] for r in p["receipts"]],["active","cancelled"])
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM monthly_audit WHERE receipt_id=%s AND action='receipt_corrected'",
                      (new_id,))
            self.assertEqual(c.fetchone()["n"],1)

    def test_concurrent_receipts_do_not_double_fund_month(self):
        sid=self.create()
        with ThreadPoolExecutor(max_workers=2) as e:
            results=list(e.map(lambda _: F.take_payment(sid,3000,actor="tester"),range(2)))
        self.assertEqual(sum(int(created) for _,created in results),2)
        p=self.projection(sid,self.anchor)
        self.assertEqual([x["paid"] for x in p["periods"][:2]],[3000,3000])

    def test_mother_only_existing_family_and_no_second_parent(self):
        original=self.create(cash=12000,reg=True,gilet=True)
        with self.admin.cursor() as c:
            c.execute("SELECT father_id FROM students WHERE student_id=%s",(original,))
            fid=c.fetchone()["father_id"]
        before=self.count("parents")
        self.child["full_name"]="شقيقة "+uuid.uuid4().hex[:7]
        sibling=self.create(existing=fid)
        self.assertEqual(self.count("parents"),before)
        p=self.projection(sibling,self.anchor)
        self.assertEqual(p["due_now"],4000)

    def test_cannot_cascade_delete_children_receipts_or_guardians(self):
        sid=self.create(cash=3000)
        with self.admin.cursor() as c:
            c.execute("SELECT father_id FROM students WHERE student_id=%s",(sid,))
            pid=c.fetchone()["father_id"]
        with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
            with connect() as c:
                with c.cursor() as cur:
                    cur.execute("DELETE FROM students WHERE student_id=%s",(sid,))
        with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
            with connect() as c:
                with c.cursor() as cur:
                    cur.execute("DELETE FROM parents WHERE father_id=%s",(pid,))

    def test_report_reconciles_active_receipt_once(self):
        sid=self.create(cash=12000,reg=True,gilet=True)
        rep=F.financial_report(self.admin,date(2026,1,1),date(2026,4,30))
        self.assertGreaterEqual(rep["registration_cash"],1000)
        self.assertGreaterEqual(rep["monthly_cash"],9000)
        self.assertEqual(rep["registration_cash"]+rep["gilet_cash"]+rep["monthly_cash"],
                         rep["new_cash"])
        self.assertGreaterEqual(rep["prepaid_cash"],6000)
        rid=self.projection(sid,self.anchor)["receipts"][0]["receipt_id"]
        F.cancel_receipt(rid,"إلغاء قبض",actor="tester")
        after=F.financial_report(self.admin,date(2026,1,1),date(2026,4,30))
        self.assertEqual(rep["new_cash"]-after["new_cash"],12000)
