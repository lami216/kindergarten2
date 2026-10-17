"""
app.py — نظام إدارة الروضة (Kindergarten Management System)

This file only does three things: set up the page, gate it behind login,
and route to the selected section module. All page content lives in
sections/*.py — edit those files independently without touching this one.
"""

import os
import streamlit as st

from db import assert_schema_ready, get_connection
from schema_migrations import SchemaNotReady
import psycopg2
from style import apply_style
import auth
import sidebar

from sections import (
    dashboard, parents, students,  teachers,
    classes, academic_years, registration, payments, salaries, expenses, reports, record_manager, change_history,
)

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "school-logo.jpg")

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="روضة أطفال فودي حبيب ساكرا", page_icon="🌱", layout="wide")
apply_style()

try:
    conn = get_connection()
    assert_schema_ready(conn)
except SchemaNotReady:
    st.info('التطبيق قيد التحديث. يرجى المحاولة بعد إتمام التحديث من المسؤول.')
    st.stop()
except psycopg2.Error:
    st.error('تعذّر الاتصال بقاعدة البيانات. يرجى المحاولة مجددًا بعد قليل.')
    if st.button('إعادة المحاولة'):
        st.rerun()
    st.stop()
if not auth.check_authentication(conn):
    st.stop()
import access_control as A
profile=st.session_state['_access_profile']
if not profile['is_admin']:
    from sections import staff_workspace
    try:
        staff_workspace.render(conn)
    except A.AccessDenied:
        A.clear_state()
        st.rerun()
    st.stop()
import record_history
with conn.cursor() as cursor:
    record_history.context(cursor, st.session_state.get('auth_user'), local=False)

# --------------------------------------------------------------------------
# Navigation + routing
# --------------------------------------------------------------------------
ROUTES = {
    "dashboard": dashboard.render,
    "parents": parents.render,
    "students": students.render,
    "teachers": teachers.render,
    "classes": classes.render,
    "years": academic_years.render,
    "registration": registration.render,
    "payments": payments.render,
    "salaries": salaries.render,
    "reports": reports.render,
    "expenses": expenses.render,
    "records": record_manager.render,
    "history": change_history.render,
}
from sections import admin_users
ROUTES['admin']=admin_users.render

current_page = sidebar.render(conn)
ROUTES[current_page](conn)
if current_page not in ('records','history','dashboard','reports','admin') and not (current_page=='students' and st.session_state.get('student_file_id')):
    targets={'students':'students','parents':'parents','teachers':'teachers','classes':'classes',
             'years':'academic_years','registration':'school_departments','expenses':'expenses',
             'salaries':'teacher_payments','payments':'monthly_receipts'}
    st.divider()
    left,right=st.columns(2)
    if left.button('✏️ تعديل أو حذف السجلات',key='open_record_manager',use_container_width=True):
        st.session_state['records_target']=targets[current_page]
        st.session_state['current_page']='records'
        st.rerun()
    if right.button('🕘 سجل التغييرات',key='open_change_history',use_container_width=True):
        st.session_state['current_page']='history'
        st.rerun()

