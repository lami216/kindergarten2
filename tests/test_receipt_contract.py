"""Owner-approved corrected-ledger receipt contract against disposable PostgreSQL16."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

import db
import monthly_finance as F
import student_debt as D
import receipt_history as H
from receipt_pdf import render_receipt_pdf

DSN=os.getenv("TEST_POSTGRES_DSN")


def connection():
    c=psycopg2.connect(DSN,cursor_factory=RealDictCursor)
    c.autocommit=False
    return c


@pytest.mark.skipif(not DSN,reason="requires disposable PostgreSQL")
class ChildReceiptContractPG(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=connection()
        cls.admin.autocommit=True
        with patch.object(db,"get_connection",return_value=cls.admin):
            db.init_db()
        cls.transaction=patch.object(db,"new_transaction_connection",side_effect=connection)
        cls.transaction.start()

    @classmethod
    def tearDownClass(cls):
        cls.transaction.stop()
        cls.admin.close()

    def setUp(self):
        F.update_tariffs(0,0,3000,"receipt-qa")
        self.start=F.today()-timedelta(days=54)
        self.today=F.today()

    def child(self,*,mode="regular",start=None):
        suffix=uuid.uuid4().hex[:19]
        sid,pid="S"+suffix,"P"+suffix
        with self.admin.cursor() as c:
            c.execute("INSERT INTO parents(father_id,mother_name,mother_mobile) "
                      "VALUES(%s,'أم العقد','0599000000')",(pid,))
            c.execute("INSERT INTO students(student_id,full_name,father_id) "
                      "VALUES(%s,'طفل عقد الوصل',%s)",(sid,pid))
            c.execute("INSERT INTO monthly_accounts(student_id,status,start_date,created_by) "
                      "VALUES(%s,%s,%s,'receipt-qa')",(sid,mode,start or self.start))
        return sid

    def receipts(self,sid):
        with self.admin.cursor() as c:
            c.execute("SELECT * FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id",(sid,))
            return [dict(x) for x in c.fetchall()]

    def audit(self,sid):
        with self.admin.cursor() as c:
            c.execute("SELECT * FROM monthly_audit WHERE student_id=%s ORDER BY audit_id",(sid,))
            return [dict(x) for x in c.fetchall()]

    def cash(self):
        return F.financial_report(self.admin,date(2026,1,1),F.today())

    def test_cancel_three_period_receipt_retains_partial_and_future_does_not_become_due(self):
        # Anchor at two actual months ago; third period is future for this fixture.
        anchor=F.anniversary(self.today,-2) if False else date(self.today.year,self.today.month,1)
        anchor=F.anniversary(anchor,-2).replace(day=min(20,anchor.day+19))
        # Exactly two completed anniversary starts, third is upcoming.
        sid=self.child(start=anchor)
        part,_=F.take_payment(sid,1500,actor="receipt-qa",as_of=anchor)
        large,_=F.take_payment(sid,7500,actor="receipt-qa",as_of=anchor)
        before=F.projection(self.admin,sid,self.today)
        items=H.receipt_detail(self.admin,large)["items"]
        self.assertEqual(len([x for x in items if x["period_no"] is not None]),3)
        previous_report=self.cash()
        self.assertTrue(F.cancel_receipt(large,"خطأ قبض مالي",actor="receipt-qa"))
        after=F.projection(self.admin,sid,self.today)
        delta=self.cash()
        self.assertEqual(before["periods"][0]["paid"],3000)
        self.assertEqual(after["periods"][0]["paid"],1500)
        self.assertEqual(after["periods"][1]["paid"],0)
        self.assertEqual(after["periods"][2]["paid"],0)
        self.assertEqual(after["paid_through"],None)
        self.assertEqual(after["due_now"],4500)
        self.assertEqual(after["periods"][2]["start"]>self.today,True)
        self.assertEqual(delta["total_cash"],previous_report["total_cash"]-7500)
        self.assertEqual(delta["expenses"],previous_report["expenses"])
        self.assertEqual(delta["remaining_cash"],previous_report["remaining_cash"]-7500)
        self.assertEqual(H.receipt_detail(self.admin,large)["receipt"]["state"],"cancelled")
        self.assertTrue(all(not x["active"] for x in H.receipt_detail(self.admin,large)["items"]))
        self.assertTrue(all(x["active"] for x in H.receipt_detail(self.admin,part)["items"]))
        with self.admin.cursor() as c:
            c.execute("SELECT cancelled_at,cancelled_by,cancel_reason FROM monthly_receipts WHERE receipt_id=%s",(large,))
            row=c.fetchone()
            self.assertIsNotNone(row["cancelled_at"])
            self.assertEqual(row["cancelled_by"],"receipt-qa")
            self.assertEqual(row["cancel_reason"],"خطأ قبض مالي")

    def test_correct_twice_chain_amount_date_payer_and_idempotency(self):
        sid=self.child()
        old,_=F.take_payment(sid,6000,actor="receipt-qa",as_of=self.start)
        baseline=self.cash()
        token=str(uuid.uuid4())
        revision=F.receipt_revision(self.admin,sid)
        mid,new=F.correct_receipt(old,4500,"تحقق من المبلغ",actor="receipt-qa",
                   token=token,expected_revision=revision,payer="أم الوصل")
        self.assertTrue(new)
        self.assertEqual(F.correct_receipt(old,4500,"تحقق من المبلغ",actor="receipt-qa",
                         token=token,payer="أم الوصل"),(mid,False))
        with self.assertRaisesRegex(ValueError,"تعارض"):
            F.correct_receipt(old,4000,"تحقق من المبلغ",actor="receipt-qa",
                              token=token,payer="أم الوصل")
        new_date=self.start+timedelta(days=3)
        last,_=F.correct_receipt(mid,3500,"تصحيح ثان",actor="receipt-qa",
                    received_on=new_date,payer="ولي أمر مصحح",
                    expected_revision=F.receipt_revision(self.admin,sid))
        self.assertEqual([r["state"] for r in self.receipts(sid)],
                         ["cancelled","cancelled","active"])
        rows=self.receipts(sid)
        self.assertEqual([r["corrects_id"] for r in rows],[None,old,mid])
        self.assertEqual(rows[-1]["received_on"],new_date)
        self.assertEqual(rows[-1]["payer"],"ولي أمر مصحح")
        self.assertEqual(self.cash()["total_cash"],baseline["total_cash"]-2500)
        after=F.projection(self.admin,sid,self.today)
        self.assertEqual(after["periods"][0]["paid"],3000)
        self.assertEqual(after["periods"][1]["paid"],500)
        original=H.receipt_detail(self.admin,old)
        self.assertEqual(original["receipt"]["amount"],6000)
        self.assertTrue(original["replacements"])
        self.assertEqual(len([x for x in self.audit(sid) if x["action"]=="receipt_corrected"]),2)

    def test_double_cancel_token_stale_preview_and_concurrent_edit_cancel(self):
        sid=self.child()
        rid,_=F.take_payment(sid,3000,as_of=self.start,actor="receipt-qa")
        token=str(uuid.uuid4())
        rev=F.receipt_revision(self.admin,sid)
        self.assertTrue(F.cancel_receipt(rid,"مكرر",actor="receipt-qa",
                         token=token,expected_revision=rev))
        self.assertFalse(F.cancel_receipt(rid,"مكرر",actor="receipt-qa",token=token))
        with self.assertRaisesRegex(ValueError,"تعارض"):
            F.cancel_receipt(rid,"سبب آخر",actor="receipt-qa",token=token)
        with self.assertRaises(ValueError):
            F.cancel_receipt(rid,"قرار ثان",actor="receipt-qa")
        self.assertEqual(len([a for a in self.audit(sid) if a["action"]=="receipt_cancelled"]),1)
        self.assertEqual(F.projection(self.admin,sid)["periods"][0]["paid"],0)
        sid2=self.child()
        second,_=F.take_payment(sid2,3000,as_of=self.start,actor="receipt-qa")
        stale=F.receipt_revision(self.admin,sid2)
        F.take_payment(sid2,1000,actor="receipt-qa")
        with self.assertRaisesRegex(ValueError,"تغيّر الحساب"):
            F.cancel_receipt(second,"معاينة قديمة",actor="receipt-qa",
                             expected_revision=stale)
        self.assertEqual(H.receipt_detail(self.admin,second)["receipt"]["state"],"active")
        # Two genuine sessions compete for exactly the same student/account.
        rev=F.receipt_revision(self.admin,sid2)
        def edit():
            return F.correct_receipt(second,2000,"تصحيح متزامن",
                       token=str(uuid.uuid4()),actor="receipt-qa",expected_revision=rev)
        def cancel():
            return F.cancel_receipt(second,"إلغاء متزامن",
                       token=str(uuid.uuid4()),actor="receipt-qa",expected_revision=rev)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(edit),pool.submit(cancel)]
            outcomes=[]
            for future in futures:
                try: outcomes.append(("ok",future.result()))
                except ValueError as error: outcomes.append(("error",str(error)))
        self.assertEqual([x[0] for x in outcomes].count("ok"),1)
        self.assertEqual([x[0] for x in outcomes].count("error"),1)
        self.assertEqual(H.receipt_detail(self.admin,second)["receipt"]["state"],"cancelled")

    def test_failed_cancel_audit_rollback_and_non_cash_waiver_archival(self):
        sid=self.child()
        rid,_=F.take_payment(sid,3000,actor="receipt-qa",as_of=self.start)
        before_audit=len(self.audit(sid))
        with patch.object(F,"_audit",side_effect=RuntimeError("failed audit")):
            with self.assertRaisesRegex(RuntimeError,"failed audit"):
                F.cancel_receipt(rid,"rollback",actor="receipt-qa")
        self.assertEqual(len(self.audit(sid)),before_audit)
        self.assertEqual(H.receipt_detail(self.admin,rid)["receipt"]["state"],"active")
        self.assertTrue(all(x["active"] for x in H.receipt_detail(self.admin,rid)["items"]))
        F.cancel_receipt(rid,"قرار مبرر",actor="receipt-qa")
        self.assertEqual(F.projection(self.admin,sid)["paid_periods"],0)
        with self.assertRaisesRegex(ValueError,"لا يمكن حذف الطالب؛ عليه مبلغ"):
            D.archive_student(sid,actor="receipt-qa")
        waived,new=D.waive_debt(sid,"إسقاط موثق",True,actor="receipt-qa")
        self.assertGreater(waived,0)
        self.assertTrue(new)
        self.assertEqual(F.projection(self.admin,sid)["due_now"],0)
        D.archive_student(sid,actor="receipt-qa")
        self.assertEqual(len(self.receipts(sid)),1)
        self.assertEqual(F.projection(self.admin,sid,materialize=False)["paid_periods"],0)

    def test_history_filters_pagination_source_links_and_pdf_readonly(self):
        from pypdf import PdfReader
        sid=self.child()
        rid,_=F.take_payment(sid,6000,actor="receipt-qa",as_of=self.start)
        new,_=F.correct_receipt(rid,4500,"تدقيق رقم",actor="receipt-qa")
        first=H.history(self.admin,student_id=sid,query=str(rid),page_size=2)
        self.assertGreaterEqual(first["total"],2)
        self.assertEqual(len(first["rows"]),2)
        self.assertTrue(all(r["student_id"]==sid for r in first["rows"]))
        self.assertTrue(H.history(self.admin,student_id=sid,receipt_id=rid)["total"]>=3)
        self.assertTrue(H.history(self.admin,student_id=sid,action="receipt_corrected")["total"]>=1)
        self.assertEqual(H.history(self.admin,student_id=sid,start=date(2000,1,1),
                         end=date(2000,1,2))["total"],0)
        self.assertEqual(H.receipt_detail(self.admin,rid)["replacements"][0]["receipt_id"],new)
        before=(len(self.receipts(sid)),len(self.audit(sid)))
        for ident in (rid,new):
            pdf=render_receipt_pdf(self.admin,ident,student_id=sid)
            self.assertTrue(pdf.startswith(b"%PDF-"))
            reader=PdfReader(BytesIO(pdf))
            self.assertGreaterEqual(len(reader.pages),1)
            fonts=reader.pages[0]["/Resources"]["/Font"]
            self.assertTrue(any("/FontFile2" in str(font.get_object()) for font in fonts.values()))
            # Keep synthetic export evidence; never use real child data.
            out=Path("visual-evidence/receipt-contract")
            out.mkdir(parents=True,exist_ok=True)
            (out/f"{ident}-{'cancelled' if ident==rid else 'corrected'}.pdf").write_bytes(pdf)
        self.assertEqual(before,(len(self.receipts(sid)),len(self.audit(sid))))
        with self.assertRaisesRegex(ValueError,"غير موجود"):
            H.receipt_detail(self.admin,rid,student_id="SNOTMINE")
