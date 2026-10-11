"""Regression for the specific PR #1 review failures; isolated PostgreSQL."""
import os
import uuid
import unittest
from unittest.mock import patch

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit.testing.v1 import AppTest

import db
from sections import students
from tests.test_family_ui import SCRIPT, DSN


def _connect():
    c = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    c.autocommit = False
    return c


def _count(conn, table):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM " + table)
        return cur.fetchone()["n"]


@unittest.skipUnless(DSN, "Requires independent TEST_POSTGRES_DSN")
class RequiredFixesPostgresTest(unittest.TestCase):
    def setUp(self):
        self.conn = _connect()
        self.conn.autocommit = True
        self.family = dict(father_name="", father_mobile="", mother_name="أم فحص",
                           mother_mobile="0599000001", contact_email="")
        self.child = dict(full_name="طفل فحص", birth_date="2022-05-02",
                          gender="ذكر", birth_place="", address="",
                          medical_details="", allergies="", general_notes="",
                          authorized_pickups=[])

    def tearDown(self):
        self.conn.close()

    def save(self, child, family, parent_id, token):
        with patch.object(db, "new_transaction_connection", side_effect=_connect):
            return db.save_child_with_family(child, family, parent_id, token)

    def test_matching_retry_same_token_is_idempotent_and_conflicts_rejected(self):
        before_p, before_s = _count(self.conn, "parents"), _count(self.conn, "students")
        token = str(uuid.uuid4())
        student_id, created = self.save(self.child, self.family, None, token)
        self.assertTrue(created)
        again_id, again = self.save(dict(self.child), dict(self.family), None, token)
        self.assertEqual((again_id, again), (student_id, False))
        for changed_child, changed_family, existing in [
            (dict(self.child, full_name="طفل مختلف"), self.family, None),
            (self.child, dict(self.family, mother_name="أم مختلفة"), None),
            (self.child, self.family, "OTHER_FAMILY"),
            (dict(self.child, medical_details="حساسية"), self.family, None),
            (dict(self.child, authorized_pickups=[{"name":"مخوّل","phone":"0500"}]), self.family, None),
        ]:
            with self.subTest(changed_child=changed_child, existing=existing):
                with self.assertRaisesRegex(ValueError, "تعارض"):
                    self.save(changed_child, changed_family, existing, token)
        self.assertEqual(_count(self.conn, "students"), before_s + 1)
        self.assertEqual(_count(self.conn, "parents"), before_p + 1)

    def test_legacy_request_token_without_fingerprint_is_not_silently_accepted(self):
        token = str(uuid.uuid4())
        sid, _ = self.save(self.child, self.family, None, token)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE students SET request_fingerprint=NULL WHERE student_id=%s", (sid,))
        with self.assertRaisesRegex(ValueError, "تعارض"):
            self.save(self.child, self.family, None, token)

    def test_medical_policy_uses_original_notes_but_preserves_note_free_legacy_flag(self):
        self.assertEqual(students._medical_flag("", 0, "تنبيه جديد"), 1)
        self.assertEqual(students._medical_flag("تنبيه سابق", 1, ""), 0)
        self.assertEqual(students._medical_flag("", 1, ""), 1)
        self.assertEqual(students._medical_flag("", 1, "", True), 0)
        self.assertEqual(students._medical_flag("", 1, "تنبيه جديد", True), 1)
        self.assertEqual(students._medical_flag(None, 0, None), 0)

    def test_nullable_values_not_shown_as_text(self):
        for empty in (None, pd.NA, float("nan"), "nan", "None"):
            self.assertEqual(students._text(empty), "")
        self.assertEqual(students._text("نص فعلي"), "نص فعلي")

    def test_pickups_allow_empty_and_require_complete_pairs(self):
        self.assertEqual(students._validate_pickups([{"name":"","phone":""}]), [])
        self.assertEqual(students._validate_pickups([{"name":"اختبار","phone":"0599"}]),
                         [{"name":"اختبار","phone":"0599"}])
        with self.assertRaisesRegex(ValueError, "اسم ورقم هاتف"):
            students._validate_pickups([{"name":"اختبار","phone":""}])

    def test_student_edit_legacy_fields_are_untouched(self):
        pid = "L" + uuid.uuid4().hex[:19]
        sid = "S" + uuid.uuid4().hex[:19]
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO parents (father_id, father_name, father_mobile,
                father_job, mother_id, father_id_type) VALUES (%s,%s,%s,%s,%s,%s)""",
                (pid, "أب اختبار", "050", "وظيفة محفوظة", "789", "قدس"))
            cur.execute("""INSERT INTO students (student_id, full_name, father_id,
                id_type, nationality, has_medical_condition)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (sid, "طفل بيانات قديمة", pid, "قدس", "فلسطيني", 1))
        with patch.object(db, "new_transaction_connection", side_effect=_connect):
            app = AppTest.from_string(SCRIPT).run(timeout=20)
            selected = next(x for x in app.selectbox if x.key == "student_select_edit")
            # Native tuple value=(student_id, display name).
            selected.set_value((sid, "طفل بيانات قديمة")).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.text_area(key=f"edit_{sid}_health").value, "")
            self.assertEqual(app.text_input(key=f"edit_{sid}_place").value, "")
            self.assertEqual(app.text_input(key=f"edit_{sid}_address").value, "")
            app.text_input(key=f"edit_{sid}_name").set_value("طفل بيانات قديمة معدل")
            next(b for b in app.button if b.label == "💾 حفظ التعديلات").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
        with self.conn.cursor() as cur:
            cur.execute("""SELECT s.full_name, s.medical_details, s.has_medical_condition,
                s.id_type, s.nationality, p.father_job, p.mother_id
                FROM students s JOIN parents p ON s.father_id=p.father_id
                WHERE s.student_id=%s""", (sid,))
            v = cur.fetchone()
        self.assertEqual(v["full_name"], "طفل بيانات قديمة معدل")
        self.assertIsNone(v["medical_details"])
        self.assertEqual(v["has_medical_condition"], 1)
        self.assertEqual(v["id_type"], "قدس")
        self.assertEqual(v["nationality"], "فلسطيني")
        self.assertEqual(v["father_job"], "وظيفة محفوظة")
        self.assertEqual(v["mother_id"], "789")

    def test_edit_add_remove_medical_note_updates_real_database(self):
        pid = "L" + uuid.uuid4().hex[:19]
        sid = "S" + uuid.uuid4().hex[:19]
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO parents(father_id,father_name) VALUES (%s,%s)",
                        (pid, "أب طبي"))
            cur.execute("""INSERT INTO students(student_id,full_name,father_id,
                has_medical_condition) VALUES (%s,%s,%s,0)""",
                (sid, "طفل صحي", pid))
        with patch.object(db, "new_transaction_connection", side_effect=_connect):
            app = AppTest.from_string(SCRIPT).run(timeout=20)
            app.selectbox(key="student_select_edit").set_value((sid, "طفل صحي")).run(timeout=20)
            app.text_area(key=f"edit_{sid}_health").set_value("تنبيه صحّي")
            next(b for b in app.button if b.label == "💾 حفظ التعديلات").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            with self.conn.cursor() as cur:
                cur.execute("SELECT has_medical_condition FROM students WHERE student_id=%s",(sid,))
                self.assertEqual(cur.fetchone()["has_medical_condition"],1)
            app.text_area(key=f"edit_{sid}_health").set_value("")
            next(b for b in app.button if b.label == "💾 حفظ التعديلات").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            with self.conn.cursor() as cur:
                cur.execute("SELECT has_medical_condition FROM students WHERE student_id=%s",(sid,))
                self.assertEqual(cur.fetchone()["has_medical_condition"],0)
