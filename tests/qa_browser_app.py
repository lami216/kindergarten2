"""Disposable QA entrypoint: same production CSS/sidebar/sections, no production auth.

Runs ONLY when TEST_POSTGRES_DSN is configured, with synthetic PostgreSQL data.
"""
import os

import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

from style import apply_style
import sidebar
from sections import students, parents

if not os.environ.get("TEST_POSTGRES_DSN"):
    raise RuntimeError("QA browser app requires isolated TEST_POSTGRES_DSN")

st.set_page_config(page_title="QA — الروضة", layout="wide", initial_sidebar_state="expanded")
# Synthetic authenticated actor, limited to this isolated QA entrypoint.
st.session_state["auth_user"] = "Chromium QA"
apply_style()

@st.cache_resource
def _connection():
    conn = psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],
                            cursor_factory=RealDictCursor)
    conn.autocommit = True
    return conn

conn = _connection()
section = sidebar.render(conn)
if section == "students":
    students.render(conn)
elif section == "parents":
    parents.render(conn)
elif section == "payments":
    from sections import payments
    payments.render(conn)
elif section in ("reports","dashboard","expenses","salaries","registration"):
    from sections import reports, dashboard, expenses, salaries, registration
    routes={"reports":reports.render,"dashboard":dashboard.render,
            "expenses":expenses.render,"salaries":salaries.render,
            "registration":registration.render}
    routes[section](conn)
else:
    st.info("صفحة ليست ضمن مسارات اختبار المالية.")
