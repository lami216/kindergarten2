"""Integration tests require an isolated PostgreSQL database, never the preview DB."""
import os
import uuid
import unittest
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor

import db

DSN = os.environ.get("TEST_POSTGRES_DSN")


@unittest.skipUnless(DSN, "Requires independent TEST_POSTGRES_DSN (PostgreSQL)")
class FamilyRegistrationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_tx = patch.object(db, "new_transaction_connection", side_effect=cls.connect)
        cls.mock_tx.start()
        cls.admin = cls.connect()
        cls.admin.autocommit = True
        with patch.object(db, "get_connection", return_value=cls.admin):
            db.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()
        cls.mock_tx.stop()

    @staticmethod
    def connect():
        connection = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        connection.autocommit = False
        return connection

    def setUp(self):
        self.family = dict(father_name="", father_mobile="", mother_name="أم تجريبية",
                           mother_mobile="0599000001", contact_email="")
        self.child = dict(full_name="طفل اختبار", birth_date="2022-05-02",
                          gender="ذكر", birth_place="", address="",
                          medical_details="", allergies="", general_notes="",
                          authorized_pickups=[])

    def _count(self, table):
        with self.admin.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM " + table)
            return cur.fetchone()["n"]

    def test_mother_only_atomic_idempotent_and_sibling(self):
        before = self._count("parents")
        token = str(uuid.uuid4())
        first_id, created = db.save_child_with_family(self.child, self.family, None, token)
        self.assertTrue(created)
        self.assertEqual(self._count("parents"), before + 1)
        same_id, again = db.save_child_with_family(self.child, self.family, None, token)
        self.assertFalse(again)
        self.assertEqual(same_id, first_id)
        self.assertEqual(self._count("parents"), before + 1)
        with self.admin.cursor() as cur:
            cur.execute("SELECT father_id FROM students WHERE student_id=%s", (first_id,))
            family_id = cur.fetchone()["father_id"]
            cur.execute("SELECT father_name, mother_name FROM parents WHERE father_id=%s",
                        (family_id,))
            stored = cur.fetchone()
        self.assertIsNone(stored["father_name"])
        self.assertEqual(stored["mother_name"], "أم تجريبية")
        second = dict(self.child, full_name="أخت تجريبية")
        db.save_child_with_family(second, {}, family_id, str(uuid.uuid4()))
        with self.admin.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM students WHERE father_id=%s", (family_id,))
            self.assertEqual(cur.fetchone()["n"], 2)
        self.assertEqual(self._count("parents"), before + 1)

    def test_both_parents_and_all_optional_values(self):
        family = dict(self.family, father_name="أب تجريبي", father_mobile="0599000002",
                      contact_email="test@example.net")
        child = dict(self.child, full_name="طفلة تجريبية", birth_place="البيرة",
                     address="عنوان تجريبي", medical_details="تنبيه صحي",
                     allergies="حساسية تجريبية", general_notes="ملاحظات",
                     authorized_pickups=[{"name":"شخص أول", "phone":"0599000003"},
                                         {"name":"شخص ثان", "phone":"0599000004"}])
        sid, created = db.save_child_with_family(child, family, None, str(uuid.uuid4()))
        self.assertTrue(created)
        with self.admin.cursor() as cur:
            cur.execute("""SELECT s.*, p.contact_email, p.father_mobile, p.mother_mobile
                FROM students s JOIN parents p ON p.father_id=s.father_id
                WHERE s.student_id=%s""", (sid,))
            row = cur.fetchone()
        self.assertEqual(row["father_mobile"], "0599000002")
        self.assertEqual(row["mother_mobile"], "0599000001")
        self.assertEqual(row["contact_email"], "test@example.net")
        self.assertEqual(row["birth_place"], "البيرة")
        self.assertEqual(row["address"], "عنوان تجريبي")
        self.assertEqual(row["medical_details"], "تنبيه صحي")
        self.assertEqual(row["allergies"], "حساسية تجريبية")
        self.assertEqual(row["general_notes"], "ملاحظات")
        self.assertEqual(len(row["authorized_pickups"]), 2)

    def test_failed_child_insert_rolls_back_parent(self):
        before = self._count("parents")
        bad = dict(self.child, full_name="ط" * 101)
        with self.assertRaises(psycopg2.Error):
            db.save_child_with_family(bad, self.family, None, str(uuid.uuid4()))
        self.assertEqual(self._count("parents"), before)

    def test_incomplete_contact_pairs_rejected(self):
        self.assertIsNotNone(db.contact_validation_error("أب", "", "", ""))
        self.assertIsNotNone(db.contact_validation_error("", "", "أم", ""))
        self.assertIsNotNone(db.contact_validation_error("", "", "", ""))
        self.assertIsNone(db.contact_validation_error("", "", "أم", "0599"))
        self.assertIsNone(db.contact_validation_error("أب", "0598", "أم", "0599"))

    def test_old_identity_and_work_fields_remain_after_concise_edit(self):
        pid = "L" + uuid.uuid4().hex[:19]
        with self.admin.cursor() as cur:
            cur.execute("""INSERT INTO parents(father_id, father_name, father_mobile,
                father_job, mother_id, father_id_type)
                VALUES(%s, %s, %s, %s, %s, %s)""",
                (pid, "قديم", "0500", "مهنة قديمة", "123", "قديم"))
            cur.execute("""UPDATE parents SET father_name=%s, father_mobile=%s,
                mother_name=%s, mother_mobile=%s, contact_email=%s
                WHERE father_id=%s""",
                ("قديم معدل", "0500", None, None, None, pid))
            cur.execute("""SELECT father_job, mother_id, father_id_type
                FROM parents WHERE father_id=%s""", (pid,))
            p = cur.fetchone()
        self.assertEqual(p["father_job"], "مهنة قديمة")
        self.assertEqual(p["mother_id"], "123")
        self.assertEqual(p["father_id_type"], "قديم")
