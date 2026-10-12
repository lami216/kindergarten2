"""Hermes financial-review regressions on disposable PostgreSQL 16 only."""
import os
import uuid
from datetime import date,timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

import db
import monthly_finance as F
import payroll_finance as P
import expense_finance as E
import student_debt as D

DSN=os.getenv("TEST_POSTGRES_DSN")


def connect():
    c=psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    c.autocommit=False
    return c


@pytest.mark.skipif(not DSN,reason="Must use disposable PostgreSQL")
class FinanceReviewPG(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn=connect()
        cls.conn.autocommit=True
        with patch.object(db,"get_connection",return_value=cls.conn):
            db.init_db()
        cls.db_patch=patch.object(db,"new_transaction_connection",side_effect=connect)
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        cls.conn.close()

    def setUp(self):
        F.update_tariffs(1000,2000,3000,"review-fixture")
        self.tid="T"+uuid.uuid4().hex[:19]
        with self.conn.cursor() as c:
            c.execute("INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,5000)",
                      (self.tid,"معلمة محفوظة"))

    def count(self,query,params=()):
        with self.conn.cursor() as c:
            c.execute(query,params)
            row=c.fetchone()
            return next(iter(row.values()))

    def child(self,*,start=None,cash=0):
        pid="P"+uuid.uuid4().hex[:19]
        sid="S"+uuid.uuid4().hex[:19]
        anchor=start or F.today()
        with self.conn.cursor() as c:
            c.execute("INSERT INTO parents(father_id,mother_name,mother_mobile) VALUES(%s,'أم مالية','0599000999')",(pid,))
            c.execute("INSERT INTO students(student_id,full_name,father_id) VALUES(%s,'طفل دين',%s)",(sid,pid))
            c.execute("""INSERT INTO monthly_accounts(student_id,status,start_date,created_by)
                         VALUES(%s,'regular',%s,'fixture')""",(sid,anchor))
            c.execute("INSERT INTO monthly_fees(student_id,kind,price) VALUES(%s,'registration',1000)",(sid,))
        if cash:
            F.take_payment(sid,cash,actor="fixture",as_of=anchor)
        return sid,pid

    def test_payroll_retry_conflict_and_teacher_archive_retains_cash(self):
        token=str(uuid.uuid4())
        one,created=P.save_salary(self.tid,"2026-10",5000,actor="fixture",token=token)
        repeat,fresh=P.save_salary(self.tid,"2026-10",5000,actor="fixture",token=token)
        self.assertEqual(one,repeat)
        self.assertTrue(created)
        self.assertFalse(fresh)
        with self.assertRaisesRegex(ValueError,"تعارض"):
            P.save_salary(self.tid,"2026-10",5100,actor="fixture",token=token)
        advance_token=str(uuid.uuid4())
        aid,yes=P.save_advance(self.tid,"2026-10",1000,actor="fixture",token=advance_token)
        self.assertTrue(yes)
        self.assertEqual(P.save_advance(self.tid,"2026-10",1000,actor="fixture",token=advance_token)[0],aid)
        with self.assertRaisesRegex(ValueError,"تعارض"):
            P.save_advance(self.tid,"2026-10",2000,actor="fixture",token=advance_token)
        P.amend("teacher_payments",one,actor="fixture",reason="تصحيح الشهر",
                month="2026-09",notes="تدقيق")
        P.amend("teacher_payments",one,actor="fixture",reason="إلغاء وثيقة لا استرداد",
                cancel=True)
        P.archive_teacher(self.tid,actor="fixture")
        with self.conn.cursor() as c:
            c.execute("SELECT amount,cash_amount,record_state FROM teacher_payments WHERE payment_id=%s",(one,))
            row=c.fetchone()
        self.assertEqual(row["cash_amount"],Decimal("5000"))
        self.assertEqual(row["record_state"],"cancelled")
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM payroll_audit WHERE payment_id=%s",(one,)),3)
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM teacher_advances WHERE advance_id=%s",(aid,)),1)
        with self.assertRaises(psycopg2.Error):
            with connect() as c:
                with c.cursor() as cursor:
                    cursor.execute("DELETE FROM teachers WHERE national_id=%s",(self.tid,))

    def test_payroll_concurrent_identical_saves_and_audit_rollback(self):
        token=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies=list(pool.map(lambda _:P.save_salary(self.tid,"2026-10",2000,
                               actor="fixture",token=token),range(2)))
        self.assertEqual(len({r[0] for r in replies}),1)
        self.assertEqual(sorted(x[1] for x in replies),[False,True])
        target=replies[0][0]
        with patch.object(P,"_audit",side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError,"audit failure"):
                P.amend("teacher_payments",target,actor="fixture",
                        reason="اختبار",cancel=True)
        with self.conn.cursor() as c:
            c.execute("SELECT record_state FROM teacher_payments WHERE payment_id=%s",(target,))
            self.assertEqual(c.fetchone()["record_state"],"active")

    def test_date_snapshot_later_payment_does_not_rewrite_old_balance(self):
        anchor=date(2026,1,1)
        sid,_=self.child(start=anchor)
        old=F.projection(self.conn,sid,anchor)
        self.assertEqual(old["due_now"],4000)
        F.take_payment(sid,3000,as_of=date(2026,2,1),actor="fixture")
        self.assertEqual(F.projection(self.conn,sid,anchor)["due_now"],4000)
        self.assertEqual(F.projection(self.conn,sid,date(2026,2,1))["periods"][0]["paid"],3000)
        march,_=self.child(start=date(2026,3,1))
        self.assertEqual(F.projection(self.conn,march,anchor)["due_now"],0)
        report=F.financial_report(self.conn,anchor,anchor)
        self.assertGreaterEqual(report["due_now"],4000)

    def test_expense_correction_keeps_original_cash_date_and_true_settlement(self):
        july=date(2026,7,1)
        with self.conn.cursor() as c:
            c.execute("""INSERT INTO expenses(expense_date,category,amount,amount_paid)
                         VALUES(%s,'تصحيح مصروف',2000,2000) RETURNING expense_id""",(july,))
            eid=c.fetchone()["expense_id"]
        today=F.today()
        base_today=F.financial_report(self.conn,today,today)["operational_cash"]
        before=F.financial_report(self.conn,july,july)["operational_cash"]
        tok=str(uuid.uuid4())
        self.assertTrue(E.correct(eid,amount_total=2000,amount_paid=1000,
            category="تصحيح مصروف",expense_date=july,reason="خطأ إدخال سابق",
            actor="fixture",token=tok))
        self.assertFalse(E.correct(eid,amount_total=2000,amount_paid=1000,
            category="تصحيح مصروف",expense_date=july,reason="خطأ إدخال سابق",
            actor="fixture",token=tok))
        self.assertEqual(F.financial_report(self.conn,july,july)["operational_cash"],
                         before-1000)
        self.assertEqual(F.financial_report(self.conn,today,today)["operational_cash"],
                         base_today)
        with patch.object(E,"_audit",side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError,"audit failure"):
                E.settle(eid,500,actor="fixture",reason="اختبار",token=str(uuid.uuid4()))
        with self.conn.cursor() as c:
            c.execute("SELECT amount_paid FROM expenses WHERE expense_id=%s",(eid,))
            self.assertEqual(c.fetchone()["amount_paid"],Decimal("1000"))
        t=str(uuid.uuid4())
        self.assertTrue(E.settle(eid,500,actor="fixture",reason="نقد جديد",token=t))
        self.assertFalse(E.settle(eid,500,actor="fixture",reason="نقد جديد",token=t))
        with self.assertRaisesRegex(ValueError,"تعارض"):
            E.settle(eid,600,actor="fixture",reason="نقد جديد",token=t)
        self.assertEqual(F.financial_report(self.conn,today,today)["operational_cash"],base_today+500)
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM expense_cash_amendments WHERE expense_id=%s",(eid,)),1)

    def test_debt_refusal_explicit_waiver_and_reopened_archived_debt(self):
        sid,pid=self.child(cash=1500)
        with self.assertRaisesRegex(ValueError,"لا يمكن حذف الطالب؛ عليه مبلغ"):
            D.archive_student(sid,actor="fixture")
        token=str(uuid.uuid4())
        before=self.count("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,))
        total,created=D.waive_debt(sid,"إقرار إداري",True,actor="fixture",token=token)
        self.assertEqual(total,2500)
        self.assertTrue(created)
        self.assertEqual(D.waive_debt(sid,"إقرار إداري",True,actor="fixture",token=token),(2500,False))
        with self.assertRaisesRegex(ValueError,"تعارض"):
            D.waive_debt(sid,"سبب مختلف",True,actor="fixture",token=token)
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,)),before)
        p=F.projection(self.conn,sid)
        self.assertEqual(p["due_now"],0)
        self.assertEqual(p["paid_periods"],0)
        self.assertEqual(p["fees"]["registration"].get("waived",0),1000)
        self.assertEqual(p["periods"][0]["paid"],1500)
        self.assertEqual(p["periods"][0].get("waived",0),1500)
        D.archive_student(sid,actor="fixture")
        with self.conn.cursor() as c:
            c.execute("SELECT archived_at FROM students WHERE student_id=%s",(sid,))
            self.assertIsNotNone(c.fetchone()["archived_at"])
            c.execute("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s",(sid,))
            rid=c.fetchone()["receipt_id"]
        F.cancel_receipt(rid,"إلغاء قبض قديم",actor="fixture")
        p=F.projection(self.conn,sid)
        self.assertEqual(p["due_now"],1500)
        count=self.count("SELECT COUNT(*) AS n FROM monthly_periods WHERE student_id=%s",(sid,))
        F.ensure_started(sid,as_of=F.today()+timedelta(days=90))
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM monthly_periods WHERE student_id=%s",(sid,)),count)
        with self.assertRaises(psycopg2.Error):
            with connect() as c:
                with c.cursor() as cursor:
                    cursor.execute("DELETE FROM parents WHERE father_id=%s",(pid,))

    def test_actual_fee_collection_allows_archive_without_waiver(self):
        sid,_=self.child()
        fee,created=D.pay_unpaid_fee(sid,"registration",actor="fixture")
        self.assertTrue(created)
        self.assertEqual(self.count("SELECT COUNT(*) AS n FROM monthly_receipts WHERE receipt_id=%s",(fee,)),1)
        F.take_payment(sid,3000,actor="fixture")
        D.archive_student(sid,actor="fixture")
        self.assertEqual(F.projection(self.conn,sid)["due_now"],0)
