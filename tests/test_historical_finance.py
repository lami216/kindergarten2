"""Real PostgreSQL regressions for legacy annual receipts and immutable audit.

The new monthly subsystem must not change the old currency or hard-delete
historical income evidence.
"""
import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor

import db
import helpers as H
import historical_finance as L
import monthly_finance as F

DSN = os.environ.get("TEST_POSTGRES_DSN")


def connect():
    c=psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    # Match production connections, including CURRENT_DATE near midnight when
    # CI deliberately sets a different server timezone.
    return db._pin_business_timezone(c,autocommit=False)


@unittest.skipUnless(DSN, "isolated PostgreSQL is required")
class HistoricalReceiptAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=connect()
        cls.admin.autocommit=True
        with patch.object(db,"get_connection",return_value=cls.admin):
            db.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()

    def setUp(self):
        code=uuid.uuid4().hex
        pid="P"+code[:19]
        sid="S"+code[:19]
        year="Y"+code[:18]
        with self.admin.cursor() as c:
            c.execute("INSERT INTO parents(father_id,father_name) VALUES(%s,'ولي قديم')",(pid,))
            c.execute("INSERT INTO students(student_id,full_name,father_id) VALUES(%s,'طفل قديم',%s)",
                      (sid,pid))
            c.execute("INSERT INTO academic_years(year_id) VALUES(%s)",(year,))
            c.execute("""INSERT INTO classes(class_type,section)
                VALUES(%s,%s) RETURNING class_id""",("تجريبي "+code[:7],code[:7]))
            classroom=c.fetchone()["class_id"]
            c.execute("""INSERT INTO registrations(student_id,class_id,year_id,status,annual_tuition)
                VALUES(%s,%s,%s,%s,%s) RETURNING registration_id""",
                (sid,classroom,year,H.STATUS_NEW,Decimal("3500.00")))
            self.registration=c.fetchone()["registration_id"]
            c.execute("""INSERT INTO payments(registration_id,amount,payment_for,
                         payer_name,payment_date)
                VALUES(%s,%s,'رسوم تسجيل','ولي قديم',CURRENT_DATE)
                RETURNING receipt_number""",(self.registration,Decimal("120.50")))
            self.receipt=c.fetchone()["receipt_number"]
        self.tx=patch.object(db,"new_transaction_connection",side_effect=connect)
        self.tx.start()

    def tearDown(self):
        self.tx.stop()

    def row(self):
        with self.admin.cursor() as c:
            c.execute("SELECT * FROM payments WHERE receipt_number=%s",(self.receipt,))
            return c.fetchone()

    def audit(self):
        with self.admin.cursor() as c:
            c.execute("""SELECT action,actor,reason,before_state,after_state
                 FROM historical_payment_audit WHERE receipt_number=%s
                 ORDER BY audit_id""",(self.receipt,))
            return c.fetchall()

    def test_edit_retains_old_amount_payer_and_reason_with_real_balance(self):
        self.assertEqual(H.compute_paid_toward_tuition(self.admin,self.registration),
                         Decimal("120.50"))
        rid=L.change_receipt(self.receipt,actor="مديرة الاختبار",reason="تصحيح كتابة",
                             new_amount="90.25",payer="أم جديدة",
                             payment_for="أقساط تعليمية",details="تصحيح")
        self.assertEqual(rid,self.registration)
        self.assertEqual(self.row()["amount"],Decimal("90.25"))
        audit=self.audit()
        self.assertEqual(len(audit),1)
        self.assertEqual(audit[0]["before_state"]["amount"],"120.50")
        self.assertEqual(audit[0]["after_state"]["amount"],"90.25")
        self.assertEqual(audit[0]["reason"],"تصحيح كتابة")
        self.assertEqual(audit[0]["actor"],"مديرة الاختبار")
        self.assertEqual(H.compute_paid_toward_tuition(self.admin,self.registration),
                         Decimal("90.25"))

    def test_cancel_keeps_original_receipt_but_removes_financial_effect(self):
        before=L.change_receipt(self.receipt,actor="مديرة",reason="خطأ مبلغ",
                                new_amount=130,payer="ولي قديم",payment_for="رسوم تسجيل")
        self.assertEqual(before,self.registration)
        L.change_receipt(self.receipt,actor="مديرة",reason="لم يُقبض المال",cancel=True)
        row=self.row()
        self.assertEqual(row["receipt_state"],"cancelled")
        self.assertEqual(row["amount"],Decimal("130.00"))
        self.assertEqual(row["cancel_reason"],"لم يُقبض المال")
        self.assertIsNotNone(row["cancelled_at"])
        self.assertEqual(len(self.audit()),2)
        self.assertEqual(self.audit()[1]["before_state"]["receipt_state"],"active")
        self.assertEqual(self.audit()[1]["after_state"]["receipt_state"],"cancelled")
        self.assertEqual(H.compute_paid_toward_tuition(self.admin,self.registration),0)
        self.assertEqual(H.compute_registration_status(self.admin,self.registration),
                         H.STATUS_NEW)
        with self.assertRaisesRegex(ValueError,"ملغى"):
            L.change_receipt(self.receipt,actor="مديرة",reason="مرة ثانية",cancel=True)

    def test_validation_error_preserves_original_and_does_not_audit(self):
        for data in ({"cancel":True,"reason":""},
                     {"new_amount":0,"payer":"ولي","payment_for":"رسوم تسجيل","reason":"تصحيح"},
                     {"new_amount":"1.001","payer":"ولي","payment_for":"رسوم تسجيل","reason":"تصحيح"},
                     {"new_amount":50,"payer":"","payment_for":"رسوم تسجيل","reason":"تصحيح"}):
            with self.assertRaises(ValueError):
                L.change_receipt(self.receipt,actor="مديرة",**data)
        self.assertEqual(self.row()["receipt_state"],"active")
        self.assertEqual(self.row()["amount"],Decimal("120.50"))
        self.assertEqual(len(self.audit()),0)

    def test_audit_failure_rolls_back_mutation(self):
        with patch.object(L,"_audit",side_effect=RuntimeError("simulated failure")):
            with self.assertRaisesRegex(RuntimeError,"simulated"):
                L.change_receipt(self.receipt,actor="مديرة",reason="اختبار",cancel=True)
        self.assertEqual(self.row()["receipt_state"],"active")
        self.assertEqual(len(self.audit()),0)

    def test_concurrent_cancellations_cannot_double_cancel(self):
        def void(reason):
            try:
                L.change_receipt(self.receipt,actor="مديرة",reason=reason,cancel=True)
                return "ok"
            except ValueError:
                return "already"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(void,["أول","ثان"]))
        self.assertEqual(sorted(outcomes),["already","ok"])
        self.assertEqual(len(self.audit()),1)

    def test_migration_idempotent_does_not_rewrite_history(self):
        original=self.row()["amount"]
        F.migrate(self.admin)
        F.migrate(self.admin)
        self.assertEqual(self.row()["amount"],original)
        with self.admin.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM finance_schema_versions WHERE version=3")
            self.assertEqual(c.fetchone()["n"],1)
            c.execute("SELECT SUM(amount) AS n FROM payments WHERE receipt_state='active'")
            self.assertGreaterEqual(c.fetchone()["n"],original)
