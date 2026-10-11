"""
db.py — Database initialization and connection management.
Uses st.cache_resource to maintain a persistent connection to PostgreSQL/Supabase.
"""

import json
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st


@st.cache_resource
def get_connection():
    """
    Returns a cached PostgreSQL database connection.
    st.cache_resource ensures the TCP connection to Supabase stays alive
    and is reused across page reruns instead of reconnecting on every click.
    """
    if "postgres" in st.secrets:
        conn = psycopg2.connect(
            st.secrets["postgres"]["url"],
            cursor_factory=RealDictCursor
        )
    else:
        conn = psycopg2.connect(
            host="YOUR_SUPABASE_HOST",
            database="postgres",
            user="postgres",
            password="YOUR_PASSWORD",
            port="5432",
            cursor_factory=RealDictCursor
        )
    
    conn.autocommit = True
    return conn



def new_transaction_connection():
    """Independent transaction: never mutate the cached autocommit connection."""
    if "postgres" in st.secrets:
        connection = psycopg2.connect(st.secrets["postgres"]["url"], cursor_factory=RealDictCursor)
    else:
        connection = psycopg2.connect(
            host="YOUR_SUPABASE_HOST", database="postgres", user="postgres",
            password="YOUR_PASSWORD", port="5432", cursor_factory=RealDictCursor
        )
    connection.autocommit = False
    return connection


def contact_validation_error(father_name, father_mobile, mother_name, mother_mobile):
    """A complete name/phone pair for at least one parent; no fabricated father."""
    father_name, father_mobile = father_name.strip(), father_mobile.strip()
    mother_name, mother_mobile = mother_name.strip(), mother_mobile.strip()
    if bool(father_name) != bool(father_mobile):
        return "يرجى إدخال اسم الأب ورقم هاتفه معاً."
    if bool(mother_name) != bool(mother_mobile):
        return "يرجى إدخال اسم الأم ورقم هاتفها معاً."
    if not ((father_name and father_mobile) or (mother_name and mother_mobile)):
        return "يلزم اسم ورقم هاتف الأب أو الأم على الأقل."
    return None


def save_child_with_family(child, family, existing_parent_id, request_token):
    """Persist family + child atomically; request_token makes repeated clicks idempotent.

    Returns (student_id, created). Existing family is only linked, never overwritten.
    No secrets or raw database exception messages are passed to the UI.
    """
    if not child["full_name"].strip():
        raise ValueError("اسم الطفل مطلوب.")
    if not existing_parent_id:
        problem = contact_validation_error(
            family["father_name"], family["father_mobile"],
            family["mother_name"], family["mother_mobile"])
        if problem:
            raise ValueError(problem)
    connection = new_transaction_connection()
    try:
        with connection.cursor() as cur:
            # Serialise only repeated submissions of the same form token.
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (str(request_token),))
            cur.execute("SELECT student_id FROM students WHERE request_token=%s",
                        (str(request_token),))
            already = cur.fetchone()
            if already:
                connection.commit()
                return already["student_id"], False
            if existing_parent_id:
                cur.execute("SELECT father_id FROM parents WHERE father_id=%s FOR KEY SHARE",
                            (existing_parent_id,))
                if not cur.fetchone():
                    raise ValueError("ولي الأمر المحدد غير موجود، حدّث الصفحة واختر مجدداً.")
                parent_id = existing_parent_id
            else:
                parent_id = "P" + uuid.uuid4().hex[:19]
                cur.execute("""
                    INSERT INTO parents (father_id, father_name, father_mobile,
                                         mother_name, mother_mobile, contact_email)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (parent_id, family["father_name"].strip() or None,
                      family["father_mobile"].strip() or None,
                      family["mother_name"].strip() or None,
                      family["mother_mobile"].strip() or None,
                      family["contact_email"].strip() or None))
            student_id = "S" + uuid.uuid4().hex[:19]
            cur.execute("""
                INSERT INTO students
                    (student_id, full_name, birth_date, gender, birth_place, address,
                     medical_details, has_medical_condition, allergies, general_notes,
                     authorized_pickups, father_id, request_token)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """, (student_id, child["full_name"].strip(), child["birth_date"],
                  child["gender"], child["birth_place"].strip() or None,
                  child["address"].strip() or None,
                  child["medical_details"].strip() or None,
                  int(bool(child["medical_details"].strip())),
                  child["allergies"].strip() or None, child["general_notes"].strip() or None,
                  json.dumps(child["authorized_pickups"], ensure_ascii=False),
                  parent_id, str(request_token)))
        connection.commit()
        return student_id, True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    """
    Ensures required PostgreSQL tables exist on startup.
    Runs fast schema checks and structural migrations.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS academic_years (
                year_id VARCHAR(20) PRIMARY KEY,
                start_date DATE,
                end_date DATE,
                cohort_name VARCHAR(100)
            );

            CREATE TABLE IF NOT EXISTS teachers (
                national_id VARCHAR(20) PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                salary NUMERIC(10, 2) DEFAULT 0.00,
                mobile VARCHAR(20),
                address TEXT,
                hire_date DATE,
                experience_years INT DEFAULT 0,
                degree VARCHAR(50),
                specialization VARCHAR(100)
            );

            CREATE TABLE IF NOT EXISTS classes (
                class_id SERIAL PRIMARY KEY,
                class_type VARCHAR(50) NOT NULL,
                section VARCHAR(10) NOT NULL,
                class_name VARCHAR(100),
                teacher_id VARCHAR(20) REFERENCES teachers(national_id) ON DELETE SET NULL,
                UNIQUE(class_type, section)
            );

            CREATE TABLE IF NOT EXISTS parents (
                father_id VARCHAR(20) PRIMARY KEY,
                mother_id VARCHAR(20),
                father_name VARCHAR(100) NOT NULL,
                mother_name VARCHAR(100),
                father_job VARCHAR(100),
                mother_job VARCHAR(100),
                mother_work_type VARCHAR(100),
                father_id_type VARCHAR(50),
                mother_id_type VARCHAR(50),
                address TEXT,
                landline VARCHAR(20),
                status_refugee VARCHAR(50),
                father_work_phone VARCHAR(20),
                mother_work_phone VARCHAR(20),
                father_mobile VARCHAR(20),
                mother_mobile VARCHAR(20),
                emergency_contact_name VARCHAR(100),
                emergency_contact_phone VARCHAR(20),
                marital_status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS students (
                student_id VARCHAR(20) PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                birth_date DATE,
                birth_place VARCHAR(100),
                gender VARCHAR(10),
                id_type VARCHAR(50),
                nationality VARCHAR(50),
                has_medical_condition INT DEFAULT 0,
                medical_details TEXT,
                father_id VARCHAR(20) REFERENCES parents(father_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS registrations (
                registration_id SERIAL PRIMARY KEY,
                student_id VARCHAR(20) REFERENCES students(student_id) ON DELETE CASCADE,
                class_id INT REFERENCES classes(class_id) ON DELETE RESTRICT,
                year_id VARCHAR(20) REFERENCES academic_years(year_id) ON DELETE RESTRICT,
                status VARCHAR(50) NOT NULL,
                registration_date DATE DEFAULT CURRENT_DATE,
                annual_tuition NUMERIC(10, 2) DEFAULT 3500.00,
                UNIQUE(student_id, year_id)
            );

            CREATE TABLE IF NOT EXISTS teacher_payments (
                payment_id SERIAL PRIMARY KEY,
                national_id VARCHAR(20) REFERENCES teachers(national_id) ON DELETE CASCADE,
                amount NUMERIC(10, 2) NOT NULL,
                payment_date DATE DEFAULT CURRENT_DATE,
                salary_month VARCHAR(7) NOT NULL,
                base_salary NUMERIC(10, 2) DEFAULT 0.00,
                bonus NUMERIC(10, 2) DEFAULT 0.00,
                deductions NUMERIC(10, 2) DEFAULT 0.00,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            ALTER TABLE registrations 
            ADD COLUMN IF NOT EXISTS annual_tuition NUMERIC(10, 2) DEFAULT 3500.00;

            CREATE TABLE IF NOT EXISTS payments (
                receipt_number SERIAL PRIMARY KEY,
                registration_id INT REFERENCES registrations(registration_id) ON DELETE CASCADE,
                amount NUMERIC(10, 2) NOT NULL,
                payment_date DATE DEFAULT CURRENT_DATE,
                payment_method VARCHAR(50) DEFAULT 'كاش',
                payer_name VARCHAR(100),
                payment_for VARCHAR(50),
                payment_for_other TEXT
            );

            -- -------------------------------------------------------------
            -- OPERATIONAL EXPENSES TABLE (WITH PAYMENT STATUS & DEBT TRACKING)
            -- -------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS expenses (
                expense_id SERIAL PRIMARY KEY,
                expense_date DATE DEFAULT CURRENT_DATE,
                category VARCHAR(100) NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                amount_paid NUMERIC(10, 2) DEFAULT 0.00,
                payment_status VARCHAR(50) DEFAULT 'مدفوع بالكامل',
                payment_method VARCHAR(50) DEFAULT 'كاش',
                payee VARCHAR(150),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Migrations to ensure existing databases receive payment status columns
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS amount_paid NUMERIC(10, 2) DEFAULT 0.00;
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) DEFAULT 'مدفوع بالكامل';

            -- -------------------------------------------------------------
            -- CAPITAL ASSETS & EQUIPMENT TABLE
            -- -------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS assets (
                asset_id SERIAL PRIMARY KEY,
                purchase_date DATE DEFAULT CURRENT_DATE,
                item_name VARCHAR(150) NOT NULL,
                category VARCHAR(100) NOT NULL,
                quantity INT DEFAULT 1,
                unit_cost NUMERIC(10, 2) NOT NULL,
                total_cost NUMERIC(10, 2) NOT NULL,
                condition_status VARCHAR(50) DEFAULT 'ممتازة',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- -------------------------------------------------------------
            -- TEACHER ADVANCES TABLE
            -- -------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS teacher_advances (
                advance_id SERIAL PRIMARY KEY,
                national_id VARCHAR(20) REFERENCES teachers(national_id) ON DELETE CASCADE,
                amount NUMERIC(10, 2) NOT NULL,
                advance_date DATE NOT NULL,
                salary_month VARCHAR(7) NOT NULL,
                is_deducted BOOLEAN DEFAULT FALSE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Migration to ensure teacher_payments supports advance deductions
            ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS advance NUMERIC(10, 2) DEFAULT 0.00;

            -- Additive migration: preserve old identity, jobs and payment references.
            ALTER TABLE parents ALTER COLUMN father_name DROP NOT NULL;
            ALTER TABLE parents ADD COLUMN IF NOT EXISTS contact_email VARCHAR(254);
            ALTER TABLE students ADD COLUMN IF NOT EXISTS address TEXT;
            ALTER TABLE students ADD COLUMN IF NOT EXISTS allergies TEXT;
            ALTER TABLE students ADD COLUMN IF NOT EXISTS general_notes TEXT;
            ALTER TABLE students ADD COLUMN IF NOT EXISTS authorized_pickups JSONB NOT NULL DEFAULT '[]'::jsonb;
            ALTER TABLE students ADD COLUMN IF NOT EXISTS request_token UUID;
            CREATE UNIQUE INDEX IF NOT EXISTS students_request_token_unique
              ON students(request_token);
        """)