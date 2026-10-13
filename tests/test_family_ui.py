"""Exercise real Streamlit forms against the isolated CI PostgreSQL instance."""
import os
import uuid
import unittest
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit.testing.v1 import AppTest

import db

DSN = os.environ.get("TEST_POSTGRES_DSN")
SCRIPT = """
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st
from sections import students
# The production router authenticates before rendering this form. Model that
# real identity explicitly instead of relying on an invented default actor.
st.session_state['auth_user'] = 'family-ui-qa'
conn = psycopg2.connect(os.environ["TEST_POSTGRES_DSN"], cursor_factory=RealDictCursor)
conn.autocommit = True
try:
    students.render(conn)
finally:
    conn.close()
"""
PARENT_SCRIPT = """
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from sections import parents
conn = psycopg2.connect(os.environ["TEST_POSTGRES_DSN"], cursor_factory=RealDictCursor)
conn.autocommit = True
try:
    parents.render(conn)
finally:
    conn.close()
"""


@unittest.skipUnless(DSN, "PostgreSQL testing DSN required")
class FamilyAppTest(unittest.TestCase):
    @staticmethod
    def connect():
        c = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        c.autocommit = False
        return c

    def test_mother_only_form_preserves_fields_after_validation_error_then_saves(self):
        name = "طفل واجهة " + uuid.uuid4().hex[:8]
        with patch.object(db, "new_transaction_connection", side_effect=self.connect):
            app = AppTest.from_string(SCRIPT).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            labels = [w.label for w in app.text_input]
            for old in ("رقم هوية الطالب", "نوع الهوية", "الجنسية", "مهنة الأب"):
                self.assertFalse(any(old in label for label in labels), old)
            self.assertTrue(any("اسم الطفل" in label for label in labels))
            app.text_input(key="kid_name").set_value(name)
            app.text_input(key="kid_mother_name").set_value("أم تجربة واجهة")
            next(b for b in app.button if "حفظ بيانات الطفل" in b.label).click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("هاتف" in e.value for e in app.error))
            self.assertEqual(app.text_input(key="kid_name").value, name)
            app.text_input(key="kid_mother_phone").set_value("0599555555")
            next(b for b in app.button if "حفظ بيانات الطفل" in b.label).click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
        with psycopg2.connect(DSN, cursor_factory=RealDictCursor) as connection:
            with connection.cursor() as cur:
                cur.execute("""SELECT p.father_name, p.mother_name
                    FROM students s JOIN parents p ON s.father_id=p.father_id
                    WHERE s.full_name=%s""", (name,))
                row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["father_name"])
        self.assertEqual(row["mother_name"], "أم تجربة واجهة")

    def test_parent_page_only_edits_and_lists_children(self):
        app = AppTest.from_string(PARENT_SCRIPT).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(any("إضافة ولي أمر جديد" in t.label for t in app.tabs))
        self.assertFalse(any("حفظ ولي الأمر" in b.label for b in app.button))
        self.assertEqual(len(app.dataframe), 1)
        self.assertIn("الأطفال المرتبطون", app.dataframe[0].value.columns)
