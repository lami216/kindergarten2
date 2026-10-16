"""Current placement, independent from historical academic and financial records."""
import psycopg2
import db


def migrate(conn):
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS school_departments (
                department_id SERIAL PRIMARY KEY,
                name VARCHAR(180) NOT NULL CHECK(length(btrim(name))>0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            ALTER TABLE school_departments ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
            ALTER TABLE school_departments ADD COLUMN IF NOT EXISTS archived_by TEXT;
            DROP INDEX IF EXISTS school_department_name_unique;
            CREATE UNIQUE INDEX school_department_name_unique ON school_departments(lower(name)) WHERE archived_at IS NULL;
            CREATE TABLE IF NOT EXISTS student_departments (
                student_id VARCHAR(20) PRIMARY KEY REFERENCES students(student_id) ON DELETE RESTRICT,
                department_id INTEGER NOT NULL REFERENCES school_departments(department_id) ON DELETE RESTRICT,
                assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS student_department_members ON student_departments(department_id);
            CREATE TABLE IF NOT EXISTS department_transfers (
                transfer_id BIGSERIAL PRIMARY KEY,
                student_id VARCHAR(20) NOT NULL REFERENCES students(student_id) ON DELETE RESTRICT,
                from_department_id INTEGER REFERENCES school_departments(department_id) ON DELETE RESTRICT,
                to_department_id INTEGER NOT NULL REFERENCES school_departments(department_id) ON DELETE RESTRICT,
                actor VARCHAR(100) NOT NULL,
                transferred_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS department_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            SELECT pg_advisory_xact_lock(hashtextextended('school_departments_initial_placement',0));
            DO $$ BEGIN
                IF NOT EXISTS(SELECT 1 FROM department_migrations WHERE migration_id='legacy_placement_v1') THEN
                    INSERT INTO school_departments(name)
                    SELECT DISTINCT btrim(class_type||' '||section||COALESCE(' · '||NULLIF(btrim(class_name),''),''))
                    FROM classes WHERE btrim(class_type||' '||section)<>'' ON CONFLICT DO NOTHING;
                    INSERT INTO student_departments(student_id,department_id)
                    SELECT placement.student_id,d.department_id FROM (
                        SELECT DISTINCT ON(r.student_id) r.student_id,
                            btrim(c.class_type||' '||c.section||COALESCE(' · '||NULLIF(btrim(c.class_name),''),'')) AS name
                        FROM registrations r JOIN classes c ON c.class_id=r.class_id
                        JOIN students s ON s.student_id=r.student_id
                        LEFT JOIN academic_years y ON y.year_id=r.year_id
                        WHERE s.archived_at IS NULL
                        ORDER BY r.student_id,y.start_date DESC NULLS LAST,r.registration_date DESC,r.registration_id DESC
                    ) placement JOIN school_departments d ON lower(d.name)=lower(placement.name)
                    WHERE true
                    ON CONFLICT(student_id) DO NOTHING;
                    INSERT INTO department_migrations(migration_id) VALUES('legacy_placement_v1');
                END IF;
            END $$;
        """)


def create(name):
    name=' '.join(str(name or '').split())
    if not name or len(name)>100:
        raise ValueError('أدخل اسم قسم لا يتجاوز 100 حرف.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            A.require(c,'departments.create')
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended('department_mutation',0))")
            c.execute('INSERT INTO school_departments(name) VALUES(%s) RETURNING department_id',(name,))
            result=c.fetchone()['department_id']
        conn.commit()
        return result
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError('هذا القسم موجود بالفعل.') from None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def transfer(student_ids,department_id,*,actor):
    ids=sorted(set(student_ids))
    if not ids:
        raise ValueError('اختر طفلًا واحدًا على الأقل.')
    actor=str(actor or '').strip()
    if not actor or len(actor)>100:
        raise ValueError('أعد تسجيل الدخول قبل حفظ النقل.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'departments.edit',actor)
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended('department_mutation',0))")
            import record_history
            record_history.context(c,actor,'نقل الأطفال بين الأقسام')
            c.execute('SELECT department_id FROM school_departments WHERE department_id=%s AND archived_at IS NULL FOR SHARE',(department_id,))
            if not c.fetchone():
                raise ValueError('القسم المحدد غير موجود.')
            # Stable child locks serialize transfers and preserve atomic batches.
            c.execute('SELECT student_id,archived_at FROM students WHERE student_id=ANY(%s) ORDER BY student_id FOR UPDATE',(ids,))
            rows=c.fetchall()
            if len(rows)!=len(ids) or any(r['archived_at'] is not None for r in rows):
                raise ValueError('بعض الأطفال غير موجودين أو مؤرشفون؛ حدّث القائمة.')
            c.execute('SELECT student_id,department_id FROM student_departments WHERE student_id=ANY(%s)',(ids,))
            old={r['student_id']:r['department_id'] for r in c.fetchall()}
            changed=0
            for student in ids:
                if old.get(student)==department_id:
                    continue
                c.execute('''INSERT INTO student_departments(student_id,department_id) VALUES(%s,%s)
                    ON CONFLICT(student_id) DO UPDATE SET department_id=EXCLUDED.department_id,assigned_at=now()''',(student,department_id))
                c.execute('''INSERT INTO department_transfers(student_id,from_department_id,to_department_id,actor)
                    VALUES(%s,%s,%s,%s)''',(student,old.get(student),department_id,actor))
                changed+=1
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
