"""Real PostgreSQL timezone regressions for the financial civil-day boundary.

Runs only against the disposable loopback kindergarten_test database. A Berlin
session and Pacific/Honolulu process must not change the Nouakchott ledger day.
"""
import os
import time
import uuid
from datetime import datetime, time as clock_time, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

import db
import monthly_finance as F
import student_debt as D

DSN = os.getenv("TEST_POSTGRES_DSN")


def berlin_connection():
    connection = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    with connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'Europe/Berlin'")
    connection.commit()
    return connection


@pytest.mark.skipif(not DSN, reason="Requires disposable real PostgreSQL")
class BusinessTimezonePG(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = berlin_connection()
        cls.admin.autocommit = True
        with patch.object(db, "get_connection", return_value=cls.admin):
            db.init_db()
        cls.tx = patch.object(db, "new_transaction_connection", side_effect=berlin_connection)
        cls.tx.start()

    @classmethod
    def tearDownClass(cls):
        cls.tx.stop()
        cls.admin.close()

    def setUp(self):
        self.day = F.today()
        # One 4000-old-ouguiya tuition; no synthetic registration receipt.
        F.update_tariffs(0, 0, 4000, "timezone-fixture")
        self.original_process_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Pacific/Honolulu"
        if hasattr(time, "tzset"):
            time.tzset()
        self.assertEqual(F.today(), self.day)

    def tearDown(self):
        if self.original_process_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.original_process_tz
        if hasattr(time, "tzset"):
            time.tzset()

    def child(self, start):
        suffix = uuid.uuid4().hex[:19]
        student, parent = "S" + suffix, "P" + suffix
        with self.admin.cursor() as cursor:
            cursor.execute("INSERT INTO parents(father_id,mother_name,mother_mobile) "
                           "VALUES(%s,'أم الاختبار','0599123456')", (parent,))
            cursor.execute("INSERT INTO students(student_id,full_name,father_id) "
                           "VALUES(%s,'طالب اختبار التوقيت',%s)", (student,parent))
            cursor.execute("INSERT INTO monthly_accounts(student_id,status,start_date,created_by) "
                           "VALUES(%s,'regular',%s,'timezone-fixture')", (student,start))
        return student

    def boundary_instant(self):
        # At 23:30 UTC: Nouakchott is today, Berlin is already tomorrow.
        return datetime.combine(self.day, clock_time(23,30), timezone.utc)

    def test_real_database_and_process_calendar_dates_disagree(self):
        instant = self.boundary_instant()
        with self.admin.cursor() as cursor:
            cursor.execute("""SELECT current_setting('TimeZone') AS zone,
                (%s::timestamptz)::date AS database_day,
                (%s::timestamptz AT TIME ZONE 'Africa/Nouakchott')::date AS business_day""",
                (instant,instant))
            result=cursor.fetchone()
        self.assertEqual(result["zone"], "Europe/Berlin")
        self.assertEqual(result["database_day"],self.day+timedelta(days=1))
        self.assertEqual(result["business_day"],self.day)

    def test_dst_dates_with_berlin_server_and_nouakchott_business_day(self):
        for day in (datetime(2026,3,28),datetime(2026,7,15),
                    datetime(2026,10,25)):
            instant=day.replace(hour=23,minute=30,tzinfo=timezone.utc)
            with self.subTest(day=str(day.date())), self.admin.cursor() as cursor:
                cursor.execute("""SELECT (%s::timestamptz)::date AS db_day,
                    (%s::timestamptz AT TIME ZONE 'Africa/Nouakchott')::date AS local_day""",
                    (instant,instant))
                result=cursor.fetchone()
                self.assertEqual(result["local_day"],day.date())
                self.assertEqual(result["db_day"],day.date()+timedelta(days=1))

    def test_naive_student_creation_timestamp_default_uses_business_day(self):
        # students.created_at is TIMESTAMP WITHOUT TIME ZONE. Its future
        # default is the business wall-clock, not the Berlin session wall-clock.
        student=self.child(self.day)
        suggestion=F.account_setup_suggestion(self.admin,student)
        self.assertEqual(suggestion["created_on"],self.day)
        with self.admin.cursor() as cursor:
            cursor.execute("SELECT created_at::date AS raw_day FROM students WHERE student_id=%s",
                           (student,))
            self.assertEqual(cursor.fetchone()["raw_day"],self.day)

    def test_cancel_4000_restores_debt_and_removes_cash_then_waiver_allows_archive(self):
        student=self.child(self.day)
        before=F.financial_report(self.admin,self.day,self.day)
        receipt,created=F.take_payment(student,4000,actor="timezone-fixture",as_of=self.day)
        self.assertTrue(created)
        paid=F.projection(self.admin,student,self.day)
        self.assertEqual(paid["due_now"],0)
        self.assertEqual(paid["paid_periods"],1)
        during=F.financial_report(self.admin,self.day,self.day)
        self.assertEqual(during["total_cash"]-before["total_cash"],4000)

        F.cancel_receipt(receipt,"أُلغي نقد حقيقي",actor="timezone-fixture")
        # Deterministic real TIMESTAMPTZ row crossing the server's day cutoff.
        with self.admin.cursor() as cursor:
            cursor.execute("UPDATE monthly_receipts SET cancelled_at=%s WHERE receipt_id=%s",
                           (self.boundary_instant(),receipt))
            cursor.execute("""SELECT state,(cancelled_at)::date AS server_day,
                (cancelled_at AT TIME ZONE 'Africa/Nouakchott')::date AS local_day
                FROM monthly_receipts WHERE receipt_id=%s""",(receipt,))
            row=cursor.fetchone()
        self.assertEqual(row["state"],"cancelled")
        self.assertEqual(row["server_day"],self.day+timedelta(days=1))
        self.assertEqual(row["local_day"],self.day)
        after=F.financial_report(self.admin,self.day,self.day)
        self.assertEqual(after["total_cash"],before["total_cash"])
        projection=F.projection(self.admin,student,self.day)
        self.assertEqual(projection["due_now"],4000)
        self.assertEqual(projection["paid_periods"],0)
        with self.assertRaisesRegex(ValueError,"لا يمكن حذف الطالب؛ عليه مبلغ"):
            D.archive_student(student,actor="timezone-fixture")

        original_receipt_count=1
        waived,new=D.waive_debt(student,"قرار موثق دون قبض",True,actor="timezone-fixture")
        self.assertEqual((waived,new),(4000,True))
        self.assertEqual(F.projection(self.admin,student,self.day)["due_now"],0)
        self.assertEqual(F.projection(self.admin,student,self.day)["paid_periods"],0)
        with self.admin.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(student,))
            self.assertEqual(cursor.fetchone()["n"],original_receipt_count)
        D.archive_student(student,actor="timezone-fixture")
        with self.admin.cursor() as cursor:
            cursor.execute("SELECT archived_at FROM students WHERE student_id=%s",(student,))
            self.assertIsNotNone(cursor.fetchone()["archived_at"])

    def test_later_cancellation_corrects_prior_cash_report_without_fake_refund(self):
        yesterday=self.day-timedelta(days=1)
        student=self.child(self.day-timedelta(days=3))
        rid,_=F.take_payment(student,4000,actor="timezone-fixture",as_of=yesterday)
        historical=F.projection(self.admin,student,yesterday)
        past_cash=F.financial_report(self.admin,yesterday,yesterday)["total_cash"]
        self.assertEqual(historical["due_now"],0)
        F.cancel_receipt(rid,"أُلغي في اليوم التالي",actor="timezone-fixture")
        with self.admin.cursor() as cursor:
            cursor.execute("UPDATE monthly_receipts SET cancelled_at=%s WHERE receipt_id=%s",
                           (self.boundary_instant(),rid))
        self.assertEqual(F.projection(self.admin,student,yesterday)["due_now"],4000)
        self.assertEqual(F.financial_report(self.admin,yesterday,yesterday)["total_cash"],past_cash-4000)
        self.assertEqual(F.projection(self.admin,student,self.day)["due_now"],4000)

    def test_corrected_receipt_counts_on_original_date_not_decision_date(self):
        yesterday=self.day-timedelta(days=1)
        student=self.child(self.day-timedelta(days=3))
        rid,_=F.take_payment(student,4000,actor="timezone-fixture",as_of=yesterday)
        earlier=F.projection(self.admin,student,yesterday)
        self.assertEqual(earlier["due_now"],0)
        correction,_=F.correct_receipt(rid,3000,"تصحيح موثق",
                                       actor="timezone-fixture")
        with self.admin.cursor() as cursor:
            cursor.execute("UPDATE monthly_receipts SET cancelled_at=%s WHERE receipt_id=%s",
                           (self.boundary_instant(),rid))
            cursor.execute("UPDATE monthly_receipts SET created_at=%s WHERE receipt_id=%s",
                           (self.boundary_instant(),correction))
        self.assertEqual(F.projection(self.admin,student,yesterday)["due_now"],1000)
        self.assertEqual(F.projection(self.admin,student,self.day)["due_now"],1000)
        with self.assertRaisesRegex(ValueError,"لا يمكن حذف الطالب؛ عليه مبلغ"):
            D.archive_student(student,actor="timezone-fixture")


@pytest.mark.skipif(not DSN,reason="Requires disposable real PostgreSQL")
def test_both_app_connection_factories_pin_business_timezone():
    # The actual application connection methods, not hand-patched transactional
    # connections above, must pin the zone and survive rollback.
    secrets={"postgres":{"url":DSN}}
    with patch.object(db.st,"secrets",secrets):
        cached=db._session_connection.__wrapped__("timezone-factory-test")
        transaction=db.new_transaction_connection()
        try:
            for connection in (cached,transaction):
                with connection.cursor() as cursor:
                    cursor.execute("SHOW TimeZone")
                    row=cursor.fetchone()
                    zone=list(row.values())[0]
                assert zone=="Africa/Nouakchott"
                if not connection.autocommit:
                    connection.rollback()
                    with connection.cursor() as cursor:
                        cursor.execute("SHOW TimeZone")
                        assert list(cursor.fetchone().values())[0]=="Africa/Nouakchott"
        finally:
            transaction.close()
            cached.close()
