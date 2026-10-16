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

import db
conn = db.get_connection()
st.markdown(f'<div id="qa-session" data-backend="{conn.get_backend_pid()}"></div>',unsafe_allow_html=True)
if hasattr(db, 'assert_schema_ready'):
    db.assert_schema_ready(conn)
    import access_control as A
    A.can=lambda permission:True
    A.require=lambda cursor,permission: {'is_admin':True,'username':'Chromium QA'}
    A.actor=lambda cursor,permission,legacy_actor=None:legacy_actor or 'Chromium QA'
    import record_history
    with conn.cursor() as cursor:
        record_history.context(cursor, st.session_state['auth_user'], local=False)
section = sidebar.render(conn)
if section == "students":
    students.render(conn)
elif section == "parents":
    parents.render(conn)
elif section == "payments":
    from sections import payments
    payments.render(conn)
elif section in ("reports","dashboard","expenses","salaries","registration","records","history"):
    from sections import reports, dashboard, expenses, salaries, registration, record_manager, change_history
    routes={"reports":reports.render,"dashboard":dashboard.render,
            "expenses":expenses.render,"salaries":salaries.render,
            "registration":registration.render,'records':record_manager.render,'history':change_history.render}
    routes[section](conn)
else:
    st.info("صفحة ليست ضمن مسارات اختبار المالية.")
