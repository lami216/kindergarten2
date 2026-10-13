"""Monthly tuition in old Mauritanian ouguiya. Separate from historical annual shekel records.

All writes use isolated psycopg2 transactions; receipts and their allocation rows
are never deleted. The *active* projection drives both UI and reports.
"""
import calendar
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import db

MAX_AMOUNT = 1_000_000_000
BUSINESS_TZ = ZoneInfo("Africa/Nouakchott")
CURRENCY = "أوقية قديمة"


def today():
    return datetime.now(BUSINESS_TZ).date()


def amount(value, *, zero=False):
    """Reject floats, fractions, booleans, negatives and values too large for policy."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("المبلغ يجب أن يكون عدداً صحيحاً بالأوقية القديمة.")
    if not (0 if zero else 1) <= value <= MAX_AMOUNT:
        raise ValueError("المبلغ خارج الحد المسموح.")
    return value


def anniversary(anchor, offset):
    """Recompute directly from ORIGINAL day, including 31st and leap years."""
    index = (anchor.year * 12 + anchor.month - 1) + offset
    year, zero_month = divmod(index, 12)
    month = zero_month + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def _actor(name):
    return (name or "مديرة الروضة").strip()[:100]


def migrate(conn):
    """Idempotent, additive, versioned PostgreSQL16 migration; no historical conversion."""
    with conn.cursor() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS finance_schema_versions (
            version INTEGER PRIMARY KEY, installed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS monthly_tariffs (
            id SMALLINT PRIMARY KEY CHECK (id=1),
            registration BIGINT NOT NULL CHECK(registration>=0 AND registration<=1000000000),
            gilet BIGINT NOT NULL CHECK(gilet>=0 AND gilet<=1000000000),
            tuition BIGINT NOT NULL CHECK(tuition>0 AND tuition<=1000000000),
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            changed_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS monthly_accounts (
            student_id VARCHAR(20) PRIMARY KEY REFERENCES students(student_id) ON DELETE RESTRICT,
            status VARCHAR(12) NOT NULL CHECK(status IN ('regular','exempt')),
            start_date DATE NOT NULL, created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            exempt_by TEXT, exempt_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS monthly_fees (
            fee_id BIGSERIAL PRIMARY KEY,
            student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id) ON DELETE RESTRICT,
            kind VARCHAR(15) NOT NULL CHECK(kind IN ('registration','gilet')),
            price BIGINT NOT NULL CHECK(price>=0 AND price<=1000000000),
            UNIQUE(student_id,kind)
        );
        CREATE TABLE IF NOT EXISTS monthly_periods (
            period_id BIGSERIAL PRIMARY KEY,
            student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id) ON DELETE RESTRICT,
            period_no INTEGER NOT NULL CHECK(period_no>=0),
            starts DATE NOT NULL, ends DATE NOT NULL,
            price BIGINT NOT NULL CHECK(price>0 AND price<=1000000000),
            CHECK (starts<ends), UNIQUE(student_id,period_no)
        );
        CREATE TABLE IF NOT EXISTS monthly_receipts (
            receipt_id BIGSERIAL PRIMARY KEY,
            student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id) ON DELETE RESTRICT,
            amount BIGINT NOT NULL CHECK(amount>0 AND amount<=1000000000),
            received_on DATE NOT NULL, payer TEXT NOT NULL,
            state VARCHAR(12) NOT NULL DEFAULT 'active' CHECK(state IN ('active','cancelled')),
            request_token UUID NOT NULL UNIQUE, request_hash VARCHAR(64) NOT NULL,
            created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            cancelled_by TEXT, cancelled_at TIMESTAMPTZ, cancel_reason TEXT,
            corrects_id BIGINT REFERENCES monthly_receipts(receipt_id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS monthly_allocations (
            allocation_id BIGSERIAL PRIMARY KEY,
            receipt_id BIGINT NOT NULL REFERENCES monthly_receipts(receipt_id) ON DELETE RESTRICT,
            fee_id BIGINT REFERENCES monthly_fees(fee_id) ON DELETE RESTRICT,
            period_id BIGINT REFERENCES monthly_periods(period_id) ON DELETE RESTRICT,
            amount BIGINT NOT NULL CHECK(amount>0 AND amount<=1000000000),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            CHECK ((fee_id IS NULL) <> (period_id IS NULL))
        );
        CREATE INDEX IF NOT EXISTS monthly_alloc_fee ON monthly_allocations(fee_id) WHERE active;
        CREATE INDEX IF NOT EXISTS monthly_alloc_period ON monthly_allocations(period_id) WHERE active;
        CREATE TABLE IF NOT EXISTS monthly_audit (
            audit_id BIGSERIAL PRIMARY KEY,
            student_id VARCHAR(20), receipt_id BIGINT,
            action TEXT NOT NULL, actor TEXT NOT NULL, happened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            before_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT
        );
        INSERT INTO finance_schema_versions(version) VALUES (1) ON CONFLICT DO NOTHING;
        """)
        # Version 2: historical financial records must not cascade-delete.
        c.execute("SELECT 1 FROM finance_schema_versions WHERE version=2")
        if not c.fetchone():
            for table, fk, target in (
                ("payments","payments_registration_id_fkey","registrations(registration_id)"),
                ("registrations","registrations_student_id_fkey","students(student_id)"),
                ("students","students_father_id_fkey","parents(father_id)"),
            ):
                c.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {fk}")
                column = {"payments":"registration_id","registrations":"student_id",
                          "students":"father_id"}[table]
                c.execute(f"ALTER TABLE {table} ADD CONSTRAINT {fk} FOREIGN KEY ({column}) "
                          f"REFERENCES {target} ON DELETE RESTRICT")
            c.execute("INSERT INTO finance_schema_versions(version) VALUES(2)")
        # Version 3: leave every historical receipt accessible after cancellation
        # and record a durable before/after snapshot for edits and voids.
        c.execute("SELECT 1 FROM finance_schema_versions WHERE version=3")
        if not c.fetchone():
            c.execute("""
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS
                    receipt_state VARCHAR(12) NOT NULL DEFAULT 'active';
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS cancelled_by TEXT;
                ALTER TABLE payments ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
                CREATE TABLE IF NOT EXISTS historical_payment_audit (
                    audit_id BIGSERIAL PRIMARY KEY,
                    receipt_number INTEGER NOT NULL REFERENCES payments(receipt_number)
                        ON DELETE RESTRICT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    happened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    reason TEXT NOT NULL,
                    before_state JSONB NOT NULL,
                    after_state JSONB NOT NULL
                );
                INSERT INTO finance_schema_versions(version) VALUES(3);
            """)

        # Stop before silently relabelling financial rows from an unknown past
        # currency. The published database preflight was empty, but that is not
        # proof for every deployment or a license to reinterpret old money.
        c.execute("SELECT 1 FROM finance_schema_versions WHERE version=4")
        if not c.fetchone():
            for table in ("payments","expenses","teacher_payments","teacher_advances"):
                c.execute("SELECT COUNT(*) AS n FROM "+table)
                if c.fetchone()["n"]:
                    raise ValueError(
                        "توقفت تهيئة المالية: توجد عمليات مالية سابقة في "
                        + table + "؛ يلزم فحص عملتها والنسخة الاحتياطية قبل تفعيل "
                        "دفتر النقدية الجديد. لم تتغير هذه العمليات.")

        # Version 4: preserve an immutable-date cash-event projection for expenses.
        # Legacy expense rows are backfilled only as labelled opening cash events;
        # values and originals remain untouched. A later settlement is dated when
        # the cash changes rather than silently backdated to the invoice date.
        c.execute("""
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS
                teacher_payment_id INTEGER UNIQUE REFERENCES teacher_payments(payment_id) ON DELETE RESTRICT;
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS
                teacher_advance_id INTEGER UNIQUE REFERENCES teacher_advances(advance_id) ON DELETE RESTRICT;
            CREATE TABLE IF NOT EXISTS expense_cash_events (
                event_id BIGSERIAL PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(expense_id) ON DELETE RESTRICT,
                event_date DATE NOT NULL,
                amount NUMERIC(12,2) NOT NULL CHECK (amount<>0),
                source VARCHAR(20) NOT NULL CHECK (source IN ('opening','insert','adjustment')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS expense_cash_opening_unique
                ON expense_cash_events(expense_id) WHERE source='opening';
            CREATE OR REPLACE FUNCTION record_expense_cash_event()
            RETURNS trigger LANGUAGE plpgsql AS $cash_event$
            DECLARE delta NUMERIC(12,2);
            BEGIN
                IF TG_OP='INSERT' THEN
                    delta := COALESCE(NEW.amount_paid,0);
                    IF delta<>0 THEN
                        INSERT INTO expense_cash_events(expense_id,event_date,amount,source)
                        VALUES(NEW.expense_id, NEW.expense_date, delta,'insert');
                    END IF;
                ELSIF TG_OP='UPDATE' THEN
                    delta := COALESCE(NEW.amount_paid,0)-COALESCE(OLD.amount_paid,0);
                    IF delta<>0 THEN
                        INSERT INTO expense_cash_events(expense_id,event_date,amount,source)
                        VALUES(NEW.expense_id,(NOW() AT TIME ZONE 'Africa/Nouakchott')::date,delta,'adjustment');
                    END IF;
                END IF;
                RETURN NEW;
            END $cash_event$;

            DROP TRIGGER IF EXISTS expense_cash_projection_write ON expenses;
            CREATE TRIGGER expense_cash_projection_write
                AFTER INSERT OR UPDATE OF amount_paid ON expenses
                FOR EACH ROW EXECUTE FUNCTION record_expense_cash_event();
        """)
        c.execute("""
            INSERT INTO expense_cash_events(expense_id,event_date,amount,source)
            SELECT e.expense_id,e.expense_date,e.amount_paid,'opening'
            FROM expenses e WHERE e.amount_paid<>0
            AND NOT EXISTS(SELECT 1 FROM expense_cash_events x WHERE x.expense_id=e.expense_id)
            ON CONFLICT DO NOTHING
        """)
        c.execute("INSERT INTO finance_schema_versions(version) VALUES(4) ON CONFLICT DO NOTHING")
        # Version 5: permanent payroll/advance cash evidence and archived teachers.
        # The amount actually disbursed is immutable. Cancelling the document
        # does not create a fictional refund or remove the cash outflow.
        c.execute("""
            ALTER TABLE teachers ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
            ALTER TABLE teachers ADD COLUMN IF NOT EXISTS archived_by TEXT;
            ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS request_token UUID;
            ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS request_hash VARCHAR(64);
            ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS record_state TEXT NOT NULL DEFAULT 'active';
            ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS cash_amount NUMERIC(10,2);
            UPDATE teacher_payments SET cash_amount=amount WHERE cash_amount IS NULL;
            ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS request_token UUID;
            ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS request_hash VARCHAR(64);
            ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS record_state TEXT NOT NULL DEFAULT 'active';
            ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS cash_amount NUMERIC(10,2);
            UPDATE teacher_advances SET cash_amount=amount WHERE cash_amount IS NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS payroll_salary_token_uniq
                ON teacher_payments(request_token) WHERE request_token IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS payroll_advance_token_uniq
                ON teacher_advances(request_token) WHERE request_token IS NOT NULL;
            CREATE TABLE IF NOT EXISTS payroll_audit (
                audit_id BIGSERIAL PRIMARY KEY,
                payment_id INTEGER REFERENCES teacher_payments(payment_id) ON DELETE RESTRICT,
                advance_id INTEGER REFERENCES teacher_advances(advance_id) ON DELETE RESTRICT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                before_state JSONB NOT NULL,
                after_state JSONB NOT NULL,
                CHECK ((payment_id IS NULL) <> (advance_id IS NULL))
            );
        """)
        c.execute("SELECT 1 FROM finance_schema_versions WHERE version=5")
        if not c.fetchone():
            for table, column, target in (
                ("teacher_payments","national_id","teachers(national_id)"),
                ("teacher_advances","national_id","teachers(national_id)"),
            ):
                c.execute("""SELECT conname FROM pg_constraint
                             WHERE conrelid=%s::regclass AND contype='f'
                               AND confrelid='teachers'::regclass""", (table,))
                for row in c.fetchall():
                    safe_name='"'+row["conname"].replace('"','""')+'"'
                    c.execute("ALTER TABLE "+table+" DROP CONSTRAINT "+safe_name)
                c.execute("ALTER TABLE "+table+" ADD CONSTRAINT "+
                          table+"_teacher_retained_fk FOREIGN KEY ("+column+") REFERENCES "+
                          target+" ON DELETE RESTRICT")
        c.execute("INSERT INTO finance_schema_versions(version) VALUES(5) ON CONFLICT DO NOTHING")
        # Version 6: debt waivers are ledger adjustments, not payments.
        # No historical identity/obligation is dropped on archiving.
        c.execute("""
            ALTER TABLE students ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
            ALTER TABLE students ADD COLUMN IF NOT EXISTS archived_by TEXT;
            ALTER TABLE monthly_accounts ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
            ALTER TABLE monthly_accounts ADD COLUMN IF NOT EXISTS departure_on DATE;
            ALTER TABLE monthly_accounts ADD COLUMN IF NOT EXISTS archived_by TEXT;
            CREATE TABLE IF NOT EXISTS monthly_waivers (
                waiver_id BIGSERIAL PRIMARY KEY,
                student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id)
                    ON DELETE RESTRICT,
                fee_id BIGINT REFERENCES monthly_fees(fee_id) ON DELETE RESTRICT,
                period_id BIGINT REFERENCES monthly_periods(period_id) ON DELETE RESTRICT,
                amount BIGINT NOT NULL CHECK(amount>0 AND amount<=1000000000),
                effective_on DATE NOT NULL,
                request_token UUID NOT NULL UNIQUE,
                request_hash VARCHAR(64) NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                before_state JSONB NOT NULL, after_state JSONB NOT NULL,
                CHECK ((fee_id IS NULL) <> (period_id IS NULL))
            );
            CREATE INDEX IF NOT EXISTS monthly_waiver_fee_idx ON monthly_waivers(fee_id);
            CREATE INDEX IF NOT EXISTS monthly_waiver_period_idx ON monthly_waivers(period_id);
            CREATE TABLE IF NOT EXISTS monthly_waiver_batches (
                request_token UUID PRIMARY KEY,
                student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id)
                   ON DELETE RESTRICT,
                request_hash VARCHAR(64) NOT NULL,
                effective_on DATE NOT NULL,
                actor TEXT NOT NULL, reason TEXT NOT NULL,
                gross_waived BIGINT NOT NULL CHECK(gross_waived>0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        c.execute("INSERT INTO finance_schema_versions(version) VALUES(6) ON CONFLICT DO NOTHING")
        # Version 7: a clerical correction NEVER manufactures cash today.
        # True additional settlement must explicitly create its own event.
        c.execute("""
            ALTER TABLE expense_cash_events
                DROP CONSTRAINT IF EXISTS expense_cash_events_source_check;
            ALTER TABLE expense_cash_events ADD CONSTRAINT expense_cash_events_source_check
                CHECK(source IN ('opening','insert','adjustment','settlement'));
            CREATE TABLE IF NOT EXISTS expense_cash_amendments (
                amendment_id BIGSERIAL PRIMARY KEY,
                event_id BIGINT NOT NULL REFERENCES expense_cash_events(event_id)
                    ON DELETE RESTRICT,
                expense_id INTEGER NOT NULL REFERENCES expenses(expense_id)
                    ON DELETE RESTRICT,
                delta NUMERIC(12,2) NOT NULL CHECK(delta<>0),
                actor TEXT NOT NULL, reason TEXT NOT NULL,
                corrected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS expense_audit (
                audit_id BIGSERIAL PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(expense_id)
                    ON DELETE RESTRICT,
                action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                before_state JSONB NOT NULL, after_state JSONB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expense_request_log (
                request_token UUID PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(expense_id)
                    ON DELETE RESTRICT,
                request_hash VARCHAR(64) NOT NULL,
                action TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE OR REPLACE FUNCTION record_expense_cash_event()
            RETURNS trigger LANGUAGE plpgsql AS $cash_event$
            BEGIN
                IF TG_OP='INSERT' AND COALESCE(NEW.amount_paid,0)>0 THEN
                    INSERT INTO expense_cash_events(expense_id,event_date,amount,source)
                    VALUES(NEW.expense_id,NEW.expense_date,NEW.amount_paid,'insert');
                END IF;
                RETURN NEW;
            END $cash_event$;
            DROP TRIGGER IF EXISTS expense_cash_projection_write ON expenses;
            CREATE TRIGGER expense_cash_projection_write
                AFTER INSERT ON expenses
                FOR EACH ROW EXECUTE FUNCTION record_expense_cash_event();
            ALTER TABLE expenses DROP CONSTRAINT IF EXISTS expense_valid_amount_paid;
            ALTER TABLE expenses ADD CONSTRAINT expense_valid_amount_paid
                CHECK(amount>0 AND amount_paid>=0 AND amount_paid<=amount);
        """)
        c.execute("INSERT INTO finance_schema_versions(version) VALUES(7) ON CONFLICT DO NOTHING")
        # Version 8: durable idempotency and a stable, indexed audit history.
        # No historical cash row or original allocation is rewritten.
        c.execute("""
            CREATE TABLE IF NOT EXISTS monthly_receipt_operations (
                request_token UUID PRIMARY KEY,
                request_hash VARCHAR(64) NOT NULL,
                receipt_id BIGINT NOT NULL REFERENCES monthly_receipts(receipt_id) ON DELETE RESTRICT,
                action TEXT NOT NULL CHECK (action IN ('cancel')),
                actor TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS monthly_audit_by_child_time
                ON monthly_audit(student_id, happened_at DESC, audit_id DESC);
            CREATE INDEX IF NOT EXISTS monthly_audit_by_receipt_time
                ON monthly_audit(receipt_id, happened_at DESC, audit_id DESC);
            CREATE INDEX IF NOT EXISTS monthly_receipts_correction_link
                ON monthly_receipts(corrects_id);
        """)
        c.execute("INSERT INTO finance_schema_versions(version) VALUES(8) ON CONFLICT DO NOTHING")
    if not conn.autocommit:
        conn.commit()


def prices(conn):
    with conn.cursor() as c:
        c.execute("SELECT registration,gilet,tuition FROM monthly_tariffs WHERE id=1")
        return c.fetchone()


def _tariffs(c):
    c.execute("SELECT registration,gilet,tuition FROM monthly_tariffs WHERE id=1")
    row = c.fetchone()
    if not row:
        raise ValueError("يرجى ضبط رسوم التسجيل والجيليه والشهرية في صفحة الدفعات أولاً.")
    return {key:int(row[key]) for key in ("registration","gilet","tuition")}


def _audit(c, student, receipt, action, actor, before, after, reason=None):
    c.execute("""INSERT INTO monthly_audit
        (student_id,receipt_id,action,actor,before_state,after_state,reason)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
        (student, receipt, action, _actor(actor),
         json.dumps(before, default=str, ensure_ascii=False),
         json.dumps(after, default=str, ensure_ascii=False), reason))


def update_tariffs(registration, gilet, tuition, actor):
    values = (amount(registration,zero=True),amount(gilet,zero=True),amount(tuition))
    conn = db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT pg_advisory_xact_lock(82416079)")
            # Snapshot every already-started unpaid period at the OLD tariff,
            # before updating prices. Future periods use the new tariff.
            c.execute("SELECT student_id FROM monthly_accounts WHERE status='regular' ORDER BY student_id")
            for row in c.fetchall():
                locked=_lock(c,row["student_id"])
                _due_started(c,row["student_id"],locked)
            c.execute("SELECT registration,gilet,tuition FROM monthly_tariffs WHERE id=1")
            old = c.fetchone()
            c.execute("""INSERT INTO monthly_tariffs(id,registration,gilet,tuition,changed_by)
                VALUES(1,%s,%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET registration=EXCLUDED.registration,
                gilet=EXCLUDED.gilet,tuition=EXCLUDED.tuition,
                changed_by=EXCLUDED.changed_by,changed_at=now()""",(*values,_actor(actor)))
            _audit(c,None,None,"tariff_change",actor,dict(old) if old else {},
                   dict(zip(("registration","gilet","tuition"),values)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _lock(c, student):
    c.execute("SELECT student_id,status,start_date,departure_on,archived_at FROM monthly_accounts WHERE student_id=%s FOR UPDATE",
              (student,))
    row = c.fetchone()
    if not row:
        raise ValueError("لا يوجد حساب شهري لهذا الطفل.")
    if row["status"] != "regular":
        raise ValueError("هذا الطفل معفي من الرسوم؛ لا تُسجل له دفعات.")
    return row


def _due_started(c, student, account, as_of=None):
    as_of = as_of or today()
    if isinstance(as_of,str):
        as_of = date.fromisoformat(as_of)
    # A report may ask for a future end date; this must NOT issue an
    # unfunded future monthly obligation.
    as_of = min(as_of, today())
    if account.get("departure_on"):
        as_of = min(as_of,account["departure_on"])
    anchor = account["start_date"]
    if as_of < anchor:
        return
    settings = _tariffs(c)
    for i in range(0,1200):
        start = anniversary(anchor,i)
        if start > as_of:
            break
        end = anniversary(anchor,i+1)
        c.execute("""INSERT INTO monthly_periods(student_id,period_no,starts,ends,price)
                     VALUES(%s,%s,%s,%s,%s) ON CONFLICT(student_id,period_no) DO NOTHING""",
                  (student,i,start,end,settings["tuition"]))
    else:
        raise ValueError("الجدول الزمني أطول من المسموح.")


def _fee(c, student, kind):
    c.execute("""SELECT f.fee_id,f.price,
        COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
                  WHERE a.fee_id=f.fee_id AND a.active),0) AS paid,
        COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                  WHERE w.fee_id=f.fee_id),0) AS waived
        FROM monthly_fees f WHERE f.student_id=%s AND f.kind=%s FOR UPDATE""",
        (student,kind))
    return c.fetchone()


def _fund_fee(c, receipt, student, kind, budget):
    row = _fee(c,student,kind)
    if not row:
        raise ValueError("الرسم غير متاح لهذا الطفل.")
    due = int(row["price"])-int(row["paid"])-int(row["waived"])
    if due < 0:
        raise ValueError("تجاوز في رصيد الرسم.")
    if due > budget:
        raise ValueError("المبلغ المدفوع لا يغطي الرسوم المحددة؛ تحقق من المبلغ.")
    if due:
        c.execute("""INSERT INTO monthly_allocations(receipt_id,fee_id,amount)
                     VALUES(%s,%s,%s)""",(receipt,row["fee_id"],due))
    return budget-due


def _fund_months(c, receipt, account, money, *, as_of=None):
    student = account["student_id"]
    if not money:
        return
    _due_started(c,student,account,as_of=as_of)
    c.execute("""SELECT p.period_id,p.period_no,p.price,
        COALESCE(SUM(a.amount) FILTER(WHERE a.active),0) AS paid,
        COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                  WHERE w.period_id=p.period_id),0) AS waived
        FROM monthly_periods p LEFT JOIN monthly_allocations a ON a.period_id=p.period_id
        WHERE p.student_id=%s GROUP BY p.period_id ORDER BY p.period_no""",(student,))
    rows = {row["period_no"]:row for row in c.fetchall()}
    settings = _tariffs(c)
    anchor = account["start_date"]
    index = 0
    while money:
        if index >= 1200:
            raise ValueError("عدد الفترات يتجاوز الحد المسموح.")
        row = rows.get(index)
        if row is None and account.get("departure_on"):
            raise ValueError("الحساب مؤرشف؛ لا تُنشأ شهور جديدة بعد المغادرة.")
        if row is None:
            c.execute("""INSERT INTO monthly_periods(student_id,period_no,starts,ends,price)
                VALUES(%s,%s,%s,%s,%s) RETURNING period_id""",
                (student,index,anniversary(anchor,index),
                 anniversary(anchor,index+1),settings["tuition"]))
            row = {"period_id":c.fetchone()["period_id"],"price":settings["tuition"],
                   "paid":0,"waived":0,"period_no":index}
        remaining = int(row["price"])-int(row["paid"])-int(row["waived"])
        if remaining < 0:
            raise ValueError("تجاوز في تمويل الفترة.")
        take = min(remaining,money)
        if take:
            c.execute("""INSERT INTO monthly_allocations(receipt_id,period_id,amount)
                VALUES(%s,%s,%s)""",(receipt,row["period_id"],take))
            money -= take
        index += 1


def _issue(c, account, cash, payer, actor, token, fingerprint,
           selected_registration=False, selected_gilet=False,
           *, as_of=None, schedule_as_of=None, corrects_id=None):
    amount(cash)
    c.execute("SELECT receipt_id,request_hash,state FROM monthly_receipts WHERE request_token=%s",
              (str(token),))
    duplicate = c.fetchone()
    if duplicate:
        if duplicate["request_hash"] != fingerprint:
            raise ValueError("تعارض طلب الدفعة؛ تغيرت البيانات لنفس رمز الحفظ.")
        return duplicate["receipt_id"],False
    day = as_of or today()
    c.execute("""INSERT INTO monthly_receipts
      (student_id,amount,received_on,payer,request_token,request_hash,created_by,corrects_id)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING receipt_id""",
      (account["student_id"],cash,day,payer,str(token),fingerprint,_actor(actor),corrects_id))
    receipt = c.fetchone()["receipt_id"]
    remain = cash
    if selected_registration:
        remain = _fund_fee(c,receipt,account["student_id"],"registration",remain)
    if selected_gilet:
        remain = _fund_fee(c,receipt,account["student_id"],"gilet",remain)
    _fund_months(c,receipt,account,remain,as_of=schedule_as_of or day)
    c.execute("SELECT COALESCE(SUM(amount),0) AS total FROM monthly_allocations WHERE receipt_id=%s AND active",
              (receipt,))
    if int(c.fetchone()["total"]) != cash:
        raise ValueError("تعذّر توزيع مبلغ الدفعة بالكامل.")
    c.execute("""SELECT allocation_id,fee_id,period_id,amount FROM monthly_allocations
                 WHERE receipt_id=%s ORDER BY allocation_id""",(receipt,))
    allocation_snapshot=[dict(x) for x in c.fetchall()]
    _audit(c,account["student_id"],receipt,"receipt_issued",actor,{},
           {"receipt_id":receipt,"amount":cash,"received_on":str(day),
            "payer":payer,"registration":selected_registration,
            "gilet":selected_gilet,"allocations":allocation_snapshot})
    return receipt,True


def preview(cash, registration, gilet, settings):
    """Pure UI preview; canonical prices are re-read under lock when saving."""
    amount(cash,zero=True)
    if not settings:
        raise ValueError("لم تُضبط الرسوم بعد. افتح إعدادات الرسوم في صفحة الدفعات.")
    reg=int(settings["registration"]) if registration else 0
    garment=int(settings["gilet"]) if gilet else 0
    if cash < reg+garment:
        raise ValueError("المبلغ لا يغطي رسوم التسجيل والجيليه المختارة.")
    remainder=cash-reg-garment
    monthly=int(settings["tuition"])
    if monthly<=0:
        raise ValueError("الرسوم الشهرية غير مضبوطة.")
    full,partial=divmod(remainder,monthly)
    return {"registration":reg,"gilet":garment,"monthly":remainder,
            "full_months":full,"next_partial":partial}


def initialize_in_transaction(c, student, options, actor, token):
    """Called inside the existing atomic family+student transaction."""
    mode = options.get("mode","regular")
    if mode not in ("regular","exempt"):
        raise ValueError("خيار الرسوم غير معروف.")
    anchor = options.get("start_date") or today()
    if isinstance(anchor,str):
        anchor=date.fromisoformat(anchor)
    if mode=="exempt":
        if options.get("cash") or options.get("registration") or options.get("gilet"):
            raise ValueError("المعفى لا تُسجل له دفعة نقدية.")
        c.execute("""INSERT INTO monthly_accounts
           (student_id,status,start_date,created_by,exempt_by,exempt_at)
           VALUES(%s,'exempt',%s,%s,%s,now())""",(student,anchor,_actor(actor),_actor(actor)))
        _audit(c,student,None,"exemption",actor,{},{"all_fees":"exempt","start_date":anchor})
        return None
    settings=_tariffs(c)
    c.execute("""INSERT INTO monthly_accounts(student_id,status,start_date,created_by)
                  VALUES(%s,'regular',%s,%s)""",(student,anchor,_actor(actor)))
    c.execute("""INSERT INTO monthly_fees(student_id,kind,price)
                  VALUES(%s,'registration',%s)""",(student,settings["registration"]))
    buy_gilet=bool(options.get("gilet",False))
    if buy_gilet:
        c.execute("INSERT INTO monthly_fees(student_id,kind,price) VALUES(%s,'gilet',%s)",
                  (student,settings["gilet"]))
    cash=options.get("cash",0)
    amount(cash,zero=True)
    if not cash:
        if options.get("registration") or buy_gilet:
            raise ValueError("حدد مبلغاً يغطي الرسوم المختارة.")
        return None
    account={"student_id":student,"start_date":anchor}
    receipt,_=_issue(c,account,cash,options.get("payer","ولي الأمر"),actor,
         uuid.uuid5(uuid.UUID(str(token)),"initial"),_hash(options),
         selected_registration=bool(options.get("registration")),
         selected_gilet=buy_gilet,as_of=today(),schedule_as_of=anchor)
    return receipt


def payment_preview(conn, student, cash):
    """Read-only explanation of the next amount-only month allocation.

    Periods use stored snapshots and the original anniversary anchor. A preview
    is never a receipt and never reserves amounts; save checks its audit revision.
    """
    cash=amount(cash)
    with conn.cursor() as c:
        c.execute("""SELECT student_id,status,start_date,departure_on,archived_at
                     FROM monthly_accounts WHERE student_id=%s""",(student,))
        account=c.fetchone()
        if not account: raise ValueError("يجب تهيئة الحساب أولاً.")
        if account["status"]!="regular": raise ValueError("الطفل معفى بالكامل.")
        if account["archived_at"]: raise ValueError("لا تُقبل دفعات جديدة لحساب مؤرشف.")
        c.execute("SELECT tuition FROM monthly_tariffs WHERE id=1")
        tariff=c.fetchone()
        if not tariff: raise ValueError("لم تُضبط الرسوم الشهرية بعد.")
        c.execute("""SELECT p.period_no,p.starts,p.ends,p.price,
                COALESCE(SUM(a.amount) FILTER(WHERE a.active),0) AS paid,
                COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                           WHERE w.period_id=p.period_id),0) AS waived
                FROM monthly_periods p LEFT JOIN monthly_allocations a
                     ON a.period_id=p.period_id
                WHERE p.student_id=%s GROUP BY p.period_id ORDER BY p.period_no""",
                  (student,))
        rows={r["period_no"]:dict(r) for r in c.fetchall()}
    revision=receipt_revision(conn,student)
    index=0
    left=cash
    result=[]
    while left:
        if index>=1200: raise ValueError("تجاوزت المعاينة الحد المسموح للأشهر.")
        row=rows.get(index)
        if row is None:
            if account["departure_on"]: raise ValueError("لا شهور جديدة بعد أرشفة الطفل.")
            starts=anniversary(account["start_date"],index)
            row={"period_no":index,"starts":starts,
                 "ends":anniversary(account["start_date"],index+1),
                 "price":int(tariff["tuition"]),"paid":0,"waived":0}
        remaining=int(row["price"])-int(row["paid"])-int(row["waived"])
        if remaining<0: raise ValueError("تجاوز سابق في تمويل أحد الأشهر.")
        use=min(left,remaining)
        if use:
            result.append({"start":row["starts"],"end":row["ends"],
                           "price":int(row["price"]),"previously_paid":int(row["paid"]),
                           "waived":int(row["waived"]),"allocating":use})
            left-=use
        index+=1
    return {"amount":cash,"revision":revision,"months":result}


def take_payment(student, cash, *, payer="", token=None, actor="مديرة الروضة", as_of=None, expected_revision=None):
    cash=amount(cash)
    token=str(token or uuid.uuid4())
    fp=_hash({"student":student,"amount":cash,"payer":payer.strip(),"kind":"monthly"})
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            # Lock account for all receipts/corrections and schedule generation.
            account=_lock(c,student)
            _assert_receipt_revision(c,student,expected_revision)
            c.execute("SELECT COALESCE(father_name,mother_name,'ولي الأمر') AS name FROM parents p "
                      "JOIN students s ON s.father_id=p.father_id WHERE s.student_id=%s",(student,))
            contact=c.fetchone()
            payer_name=payer.strip() or (contact["name"] if contact else "ولي الأمر")
            rid,new=_issue(c,account,cash,payer_name,actor,token,fp,as_of=as_of)
        connection.commit()
        return rid,new
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _cancel_in_tx(c, student, receipt_id, reason, actor):
    if not reason.strip():
        raise ValueError("يرجى كتابة سبب الإلغاء أو التصحيح.")
    c.execute("SELECT * FROM monthly_receipts WHERE receipt_id=%s AND student_id=%s FOR UPDATE",
              (receipt_id,student))
    row=c.fetchone()
    if not row or row["state"]!="active":
        raise ValueError("هذا الوصل غير متاح للتعديل.")
    c.execute("SELECT allocation_id,fee_id,period_id,amount FROM monthly_allocations "
              "WHERE receipt_id=%s AND active ORDER BY allocation_id",(receipt_id,))
    allocs=[dict(x) for x in c.fetchall()]
    c.execute("UPDATE monthly_allocations SET active=FALSE WHERE receipt_id=%s",(receipt_id,))
    c.execute("""UPDATE monthly_receipts SET state='cancelled',cancelled_at=now(),
               cancelled_by=%s,cancel_reason=%s WHERE receipt_id=%s""",
               (_actor(actor),reason.strip(),receipt_id))
    _audit(c,student,receipt_id,"receipt_cancelled",actor,
           {"receipt":dict(row),"allocations":allocs},{"active_allocations":[]},reason)
    return dict(row)


def receipt_revision(conn, student):
    """Monotonic account mutation marker for explicit preview confirmation."""
    with conn.cursor() as c:
        c.execute("SELECT COALESCE(MAX(audit_id),0) AS revision FROM monthly_audit "
                  "WHERE student_id=%s", (student,))
        return int(c.fetchone()["revision"])


def _assert_receipt_revision(c, student, expected_revision):
    if expected_revision is None:
        return
    c.execute("SELECT COALESCE(MAX(audit_id),0) AS revision FROM monthly_audit "
              "WHERE student_id=%s", (student,))
    if int(c.fetchone()["revision"]) != int(expected_revision):
        raise ValueError("تغيّر الحساب منذ المعاينة؛ أعد فتح الوصل وراجع التأثير قبل التأكيد.")


def cancel_receipt(receipt_id, reason, *, actor="مديرة الروضة",
                   token=None, expected_revision=None):
    """Void once; original allocations remain as inactive permanent evidence.

    Ordinary reports always use surviving valid receipts, including for old
    payment-date ranges. Audit retains the actual later decision timestamp.
    """
    if not str(reason or "").strip():
        raise ValueError("اكتب سبب إلغاء الوصل.")
    actor = _actor(actor)
    token = str(uuid.UUID(str(token or uuid.uuid4())))
    fingerprint = _hash({"action":"cancel","receipt":int(receipt_id),
                         "reason":str(reason).strip(),"actor":actor})
    connection = db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute("SELECT student_id FROM monthly_receipts WHERE receipt_id=%s",
                      (receipt_id,))
            row = c.fetchone()
            if not row:
                raise ValueError("الوصل غير موجود.")
            account = _lock(c,row["student_id"])
            c.execute("SELECT request_hash FROM monthly_receipt_operations "
                      "WHERE request_token=%s",(token,))
            duplicate = c.fetchone()
            if duplicate:
                if duplicate["request_hash"] != fingerprint:
                    raise ValueError("تعارض رمز الإلغاء؛ البيانات مختلفة عن الطلب السابق.")
                connection.commit()
                return False
            _assert_receipt_revision(c,account["student_id"],expected_revision)
            _cancel_in_tx(c,account["student_id"],receipt_id,str(reason),actor)
            c.execute("""INSERT INTO monthly_receipt_operations
                (request_token,request_hash,receipt_id,action,actor)
                VALUES(%s,%s,%s,'cancel',%s)""",
                (token,fingerprint,receipt_id,actor))
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def correct_receipt(receipt_id, new_amount, reason, *, actor="مديرة الروضة",
                    token=None, received_on=None, payer=None,
                    expected_revision=None):
    """Atomic immutable-version correction with exact replay and stale guard."""
    new_amount = amount(new_amount)
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("اكتب سبب تصحيح الوصل.")
    actor = _actor(actor)
    token = str(uuid.UUID(str(token or uuid.uuid4())))
    connection = db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute("SELECT * FROM monthly_receipts WHERE receipt_id=%s",(receipt_id,))
            old = c.fetchone()
            if not old:
                raise ValueError("الوصل غير موجود.")
            account = _lock(c,old["student_id"])
            correct_date = received_on if received_on is not None else old["received_on"]
            if isinstance(correct_date,str):
                correct_date = date.fromisoformat(correct_date)
            if not isinstance(correct_date,date) or not date(1990,1,1)<=correct_date<=today():
                raise ValueError("تاريخ الوصل المصحح غير صالح أو مستقبلي.")
            correct_payer = old["payer"] if payer is None else str(payer).strip()
            if not correct_payer or len(correct_payer)>150:
                raise ValueError("اسم دافع الوصل غير صالح.")
            fp = _hash({"correct":int(receipt_id),"new":new_amount,
                        "reason":reason,"date":str(correct_date),
                        "payer":correct_payer,"actor":actor})
            c.execute("SELECT receipt_id,request_hash FROM monthly_receipts WHERE request_token=%s",
                      (token,))
            duplicate = c.fetchone()
            if duplicate:
                if duplicate["request_hash"] != fp:
                    raise ValueError("تعارض رمز التصحيح؛ تغيّرت بيانات الطلب.")
                connection.commit()
                return duplicate["receipt_id"],False
            _assert_receipt_revision(c,account["student_id"],expected_revision)
            if old["state"] != "active":
                raise ValueError("الوصل ملغى أو مصحح بالفعل؛ افتح الوصل الساري في سلسلة التصحيحات.")
            c.execute("""SELECT allocation_id,fee_id,period_id,amount FROM monthly_allocations
                         WHERE receipt_id=%s AND active ORDER BY allocation_id""",(receipt_id,))
            original_allocations=[dict(x) for x in c.fetchall()]
            kinds=set()
            if original_allocations:
                c.execute("""SELECT DISTINCT f.kind FROM monthly_allocations a
                    JOIN monthly_fees f ON f.fee_id=a.fee_id
                    WHERE a.receipt_id=%s""",(receipt_id,))
                kinds={x["kind"] for x in c.fetchall()}
            previous=_cancel_in_tx(c,account["student_id"],receipt_id,reason,actor)
            new_id,_=_issue(c,account,new_amount,correct_payer,actor,token,fp,
                 selected_registration="registration" in kinds,
                 selected_gilet="gilet" in kinds,
                 as_of=correct_date,corrects_id=receipt_id)
            c.execute("""SELECT allocation_id,fee_id,period_id,amount
                         FROM monthly_allocations WHERE receipt_id=%s AND active
                         ORDER BY allocation_id""",(new_id,))
            new_allocations=[dict(x) for x in c.fetchall()]
            _audit(c,account["student_id"],new_id,"receipt_corrected",actor,
                   {"receipt_id":receipt_id,"amount":int(old["amount"]),
                    "received_on":str(old["received_on"]),"payer":old["payer"],
                    "allocations":original_allocations},
                   {"receipt_id":new_id,"amount":new_amount,
                    "received_on":str(correct_date),"payer":correct_payer,
                    "corrects_id":receipt_id,"allocations":new_allocations},reason)
        connection.commit()
        return new_id,True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_started(student, as_of=None):
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            account=_lock(c,student)
            _due_started(c,student,account,as_of)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def projection(conn, student, as_of=None, *, materialize=True):
    """Source of truth for child and cash reports, never infer paid from receipt existence."""
    with conn.cursor() as c:
        c.execute("SELECT * FROM monthly_accounts WHERE student_id=%s",(student,))
        account=c.fetchone()
    if not account:
        return None
    if account["status"]=="regular" and materialize:
        ensure_started(student,as_of=as_of)
    day=as_of or today()
    if isinstance(day,str):
        day=date.fromisoformat(day)
    with conn.cursor() as c:
        # Corrected ledger: cancelled/superseded receipts NEVER count, even
        # for a historical payment-date range. This is NOT an audit replay.
        # A valid payment with received_on after the cutoff cannot settle old debt.
        c.execute("""SELECT f.kind,f.price,
            COALESCE(SUM(a.amount) FILTER (WHERE r.received_on<=%s
               AND a.active AND r.state='active'),0) AS paid,
            COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                      WHERE w.fee_id=f.fee_id AND w.effective_on<=%s),0) AS waived
            FROM monthly_fees f LEFT JOIN monthly_allocations a ON a.fee_id=f.fee_id
            LEFT JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
            WHERE f.student_id=%s GROUP BY f.fee_id ORDER BY f.kind""",
            (day,day,student))
        fees={r["kind"]:{**{"price":int(r["price"]),"paid":int(r["paid"])},
                         **({"waived":int(r.get("waived",0))} if int(r.get("waived",0)) else {})} for r in c.fetchall()}
        c.execute("""SELECT p.period_no,p.starts,p.ends,p.price,
            COALESCE(SUM(a.amount) FILTER (WHERE r.received_on<=%s
               AND a.active AND r.state='active'),0) AS paid,
            COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                      WHERE w.period_id=p.period_id AND w.effective_on<=%s),0) AS waived
            FROM monthly_periods p LEFT JOIN monthly_allocations a ON a.period_id=p.period_id
            LEFT JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
            WHERE p.student_id=%s GROUP BY p.period_id ORDER BY p.period_no""",
            (day,day,student))
        periods=[{"no":r["period_no"],"start":r["starts"],"end":r["ends"],
                  "price":int(r["price"]),"paid":int(r["paid"]),
                  **({"waived":int(r.get("waived",0))} if int(r.get("waived",0)) else {})} for r in c.fetchall()]
        c.execute("""SELECT receipt_id,amount,received_on,payer,created_by,state
                FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id DESC""",(student,))
        receipts=[dict(row) for row in c.fetchall()]
    paid_count=sum(1 for x in periods if x["price"]>0 and x["paid"]==x["price"])
    contiguous=0
    for p in periods:
        if p["no"]!=contiguous or p["paid"]<p["price"]:
            break
        contiguous+=1
    charge_active = day >= account["start_date"]
    cutoff = min(day, account["departure_on"]) if account.get("departure_on") else day
    currently_due=sum(max(0,p["price"]-p["paid"]-p.get("waived",0)) for p in periods
                      if p["start"]<=cutoff and charge_active)
    if charge_active:
        currently_due+=sum(max(0,r["price"]-r["paid"]-r.get("waived",0)) for r in fees.values())
    not_yet_due=sum(max(0,p["price"]-p["paid"]-p.get("waived",0)) for p in periods if p["start"]>cutoff)
    unpaid=next((p for p in periods if p["paid"]+p.get("waived",0)<p["price"]),None)
    next_start=(unpaid["start"] if unpaid else anniversary(account["start_date"],contiguous))
    return {"account":dict(account),"fees":fees,"periods":periods,"receipts":receipts,
            "paid_periods":paid_count,"paid_through":(anniversary(account["start_date"],contiguous)-timedelta(days=1)
                 if contiguous else None),"due_now":currently_due,
            "future_partial":not_yet_due,"next_unpaid":next_start,
            "exempt":account["status"]=="exempt",
             "cash_paid":sum(int(r["amount"]) for r in receipts
                             if r["state"]=="active" and r["received_on"]<=day),
             "prepaid_paid":sum(p["paid"] for p in periods if p["start"]>day)}


def _assert_date_range(start, end):
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError("الفترة المالية غير صالحة.")


def account_setup_suggestion(conn, student):
    """Only real enrollment/creation dates: never infer a registration from birth."""
    with conn.cursor() as c:
        c.execute("""
            SELECT s.created_at::date AS created_on,
                (SELECT MIN(r.registration_date) FROM registrations r
                 WHERE r.student_id=s.student_id) AS registered_on,
                EXISTS(SELECT 1 FROM monthly_accounts a
                       WHERE a.student_id=s.student_id) AS already_set,
                EXISTS(SELECT 1 FROM registrations r JOIN payments p
                       ON p.registration_id=r.registration_id
                       WHERE r.student_id=s.student_id) AS legacy_funded
            FROM students s WHERE s.student_id=%s
        """,(student,))
        row=c.fetchone()
    if not row:
        raise ValueError("الطفل غير موجود.")
    return dict(row)


def initialize_existing_account(student, start_date, mode, confirmed, *, actor="مديرة الروضة"):
    """Explicit, idempotent no-cash setup for an already enrolled/unfunded child."""
    if not confirmed:
        raise ValueError("يجب تأكيد تهيئة حساب الطفل.")
    if mode not in ("regular", "exempt"):
        raise ValueError("نوع الحساب غير صحيح.")
    if isinstance(start_date,str):
        start_date=date.fromisoformat(start_date)
    if not isinstance(start_date,date) or start_date>today():
        raise ValueError("اختر تاريخ تسجيل صحيحاً غير مستقبلي.")
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            # Serialize competing attempts per child and guard historical funds.
            c.execute("SELECT student_id FROM students WHERE student_id=%s FOR UPDATE",(student,))
            if not c.fetchone():
                raise ValueError("الطفل غير موجود.")
            c.execute("SELECT status,start_date FROM monthly_accounts WHERE student_id=%s",(student,))
            previous=c.fetchone()
            if previous:
                if previous["status"]!=mode or previous["start_date"]!=start_date:
                    raise ValueError("حساب الطفل مُهيأ من قبل بخيارات مختلفة؛ لا يمكن استبداله.")
                return False
            c.execute("""SELECT COUNT(*) AS n FROM registrations r JOIN payments p
                ON r.registration_id=p.registration_id WHERE r.student_id=%s""",(student,))
            if c.fetchone()["n"]:
                raise ValueError("لهذا الطفل وصولات تاريخية؛ أوقف التهيئة واطلب مراجعة مالية.")
            options={"mode":mode,"start_date":start_date,"cash":0,
                     "registration":False,"gilet":False}
            initialize_in_transaction(c,student,options,actor,str(uuid.uuid4()))
            _audit(c,student,None,"existing_account_setup",actor,{},
                   {"mode":mode,"start_date":start_date,"cash":0},
                   "تهيئة مع تأكيد من الإدارة؛ لا إيصال سابق")
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def financial_report(conn, start, end):
    """ONE old-ouguiya cash projection; allocations partition receipts, not extra cash.

    Expenses use actual cash events; teacher payments and advances represent
    distinct disbursements. Only explicitly linked expenses are excluded to
    avoid double counting payroll events; equal amounts/names are not identity.
    Student debt is a stock at the selected end date, not a cash expense.
    """
    _assert_date_range(start,end)
    with conn.cursor() as c:
        c.execute("SELECT student_id FROM monthly_accounts WHERE status='regular'")
        students=[r["student_id"] for r in c.fetchall()]
    for student in students:
        ensure_started(student,as_of=end)
    with conn.cursor() as c:
        c.execute("""SELECT COALESCE(SUM(amount),0) AS n FROM monthly_receipts
                     WHERE state='active' AND received_on BETWEEN %s AND %s""",(start,end))
        cash=int(c.fetchone()["n"])
        c.execute("""SELECT f.kind,COALESCE(SUM(a.amount),0) AS n
             FROM monthly_allocations a JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             JOIN monthly_fees f ON f.fee_id=a.fee_id
             WHERE a.active
               AND r.state='active'
               AND r.received_on BETWEEN %s AND %s
             GROUP BY f.kind""",(start,end))
        fees={r["kind"]:int(r["n"]) for r in c.fetchall()}
        c.execute("""SELECT COALESCE(SUM(a.amount),0) AS n FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             JOIN monthly_periods p ON p.period_id=a.period_id
             WHERE a.active
             AND r.state='active'
             AND r.received_on BETWEEN %s AND %s""",(start,end))
        monthly=int(c.fetchone()["n"])
        c.execute("""SELECT COALESCE(SUM(a.amount),0) AS n FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             JOIN monthly_periods p ON p.period_id=a.period_id
             WHERE a.active
             AND r.state='active'
             AND r.received_on BETWEEN %s AND %s AND p.starts>r.received_on""",
             (start,end))
        prepaid=int(c.fetchone()["n"])
        c.execute("""SELECT fully.kind,COUNT(DISTINCT fully.student_id) AS n FROM (
            SELECT f.student_id,f.kind,f.price,MAX(r.received_on) AS completed_on,
                   SUM(a.amount) AS paid
            FROM monthly_fees f JOIN monthly_allocations a ON a.fee_id=f.fee_id
            JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
            WHERE f.price>0 AND a.active
              AND r.state='active'
              AND r.received_on<=%s
            GROUP BY f.fee_id
            HAVING SUM(a.amount)=MAX(f.price)
        ) fully WHERE fully.completed_on BETWEEN %s AND %s GROUP BY fully.kind""",
                  (end,start,end))
        counts={r["kind"]:int(r["n"]) for r in c.fetchall()}
        c.execute("""SELECT COALESCE(SUM(x.amount+
                 COALESCE((SELECT SUM(am.delta) FROM expense_cash_amendments am
                           WHERE am.event_id=x.event_id),0)),0) AS n
            FROM expense_cash_events x JOIN expenses e ON e.expense_id=x.expense_id
            WHERE x.event_date BETWEEN %s AND %s
              AND e.teacher_payment_id IS NULL AND e.teacher_advance_id IS NULL""",(start,end))
        operational=c.fetchone()["n"]
        c.execute("""SELECT COALESCE(SUM(COALESCE(cash_amount,amount)),0) AS n FROM teacher_payments
                     WHERE payment_date BETWEEN %s AND %s""",(start,end))
        salaries=c.fetchone()["n"]
        c.execute("""SELECT COALESCE(SUM(COALESCE(cash_amount,amount)),0) AS n FROM teacher_advances
                     WHERE advance_date BETWEEN %s AND %s""",(start,end))
        advances=c.fetchone()["n"]
    outstanding=sum(projection(conn,s,end,materialize=False)["due_now"] for s in students)
    outflow=operational+salaries+advances
    # An advance deducted later from salary is not another disbursement.
    return {"registration_children":counts.get("registration",0),
            "registration_cash":fees.get("registration",0),
            "gilet_count":counts.get("gilet",0),"gilet_cash":fees.get("gilet",0),
            "monthly_cash":monthly,"prepaid_cash":prepaid,
            "new_cash":cash,"total_cash":cash,
            "operational_cash":operational,"salary_cash":salaries,"advance_cash":advances,
            "expenses":outflow,"remaining_cash":cash-outflow,"due_now":outstanding}
