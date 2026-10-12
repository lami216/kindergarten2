"""Monthly tuition in old Mauritanian ouguiya. Separate from historical annual shekel records.

All writes use isolated psycopg2 transactions; receipts and their allocation rows
are never deleted. The *active* projection drives both UI and reports.
"""
import calendar
import hashlib
import json
import uuid
from datetime import date, datetime
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
    c.execute("SELECT student_id,status,start_date FROM monthly_accounts WHERE student_id=%s FOR UPDATE",
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
                  WHERE a.fee_id=f.fee_id AND a.active),0) AS paid
        FROM monthly_fees f WHERE f.student_id=%s AND f.kind=%s FOR UPDATE""",
        (student,kind))
    return c.fetchone()


def _fund_fee(c, receipt, student, kind, budget):
    row = _fee(c,student,kind)
    if not row:
        raise ValueError("الرسم غير متاح لهذا الطفل.")
    due = int(row["price"])-int(row["paid"])
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
        COALESCE(SUM(a.amount) FILTER(WHERE a.active),0) AS paid
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
        if row is None:
            c.execute("""INSERT INTO monthly_periods(student_id,period_no,starts,ends,price)
                VALUES(%s,%s,%s,%s,%s) RETURNING period_id""",
                (student,index,anniversary(anchor,index),
                 anniversary(anchor,index+1),settings["tuition"]))
            row = {"period_id":c.fetchone()["period_id"],"price":settings["tuition"],
                   "paid":0,"period_no":index}
        remaining = int(row["price"])-int(row["paid"])
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
    _audit(c,account["student_id"],receipt,"receipt_issued",actor,{},
           {"amount":cash,"registration":selected_registration,"gilet":selected_gilet})
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


def take_payment(student, cash, *, payer="", token=None, actor="مديرة الروضة", as_of=None):
    cash=amount(cash)
    token=str(token or uuid.uuid4())
    fp=_hash({"student":student,"amount":cash,"payer":payer.strip(),"kind":"monthly"})
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            # Lock account for all receipts/corrections and schedule generation.
            account=_lock(c,student)
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


def cancel_receipt(receipt_id, reason, *, actor="مديرة الروضة"):
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute("SELECT student_id FROM monthly_receipts WHERE receipt_id=%s",(receipt_id,))
            row=c.fetchone()
            if not row:
                raise ValueError("الوصل غير موجود.")
            account=_lock(c,row["student_id"])
            _cancel_in_tx(c,account["student_id"],receipt_id,reason,actor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def correct_receipt(receipt_id, new_amount, reason, *, actor="مديرة الروضة", token=None):
    new_amount=amount(new_amount)
    token=str(token or uuid.uuid4())
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute("SELECT * FROM monthly_receipts WHERE receipt_id=%s",(receipt_id,))
            old=c.fetchone()
            if not old:
                raise ValueError("الوصل غير موجود.")
            account=_lock(c,old["student_id"])
            fp=_hash({"correct":receipt_id,"new":new_amount,"reason":reason})
            c.execute("SELECT receipt_id,request_hash FROM monthly_receipts WHERE request_token=%s",
                      (token,))
            duplicate=c.fetchone()
            if duplicate:
                if duplicate["request_hash"]!=fp:
                    raise ValueError("تعارض رمز طلب التصحيح.")
                return duplicate["receipt_id"],False
            previous=_cancel_in_tx(c,account["student_id"],receipt_id,reason,actor)
            c.execute("""SELECT DISTINCT f.kind FROM monthly_allocations a
                 JOIN monthly_fees f ON f.fee_id=a.fee_id
                 WHERE a.receipt_id=%s""",(receipt_id,))
            kinds={x["kind"] for x in c.fetchall()}
            new_id,_=_issue(c,account,new_amount,previous["payer"],actor,
                          token,fp,selected_registration="registration" in kinds,
                          selected_gilet="gilet" in kinds,
                          as_of=previous["received_on"],corrects_id=receipt_id)
            _audit(c,account["student_id"],new_id,"receipt_corrected",actor,
                   {"old_receipt":receipt_id,"amount":int(old["amount"])},
                   {"new_receipt":new_id,"amount":new_amount},reason)
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
    with conn.cursor() as c:
        c.execute("""SELECT f.kind,f.price,COALESCE(SUM(a.amount) FILTER(WHERE a.active),0) AS paid
            FROM monthly_fees f LEFT JOIN monthly_allocations a ON a.fee_id=f.fee_id
            WHERE f.student_id=%s GROUP BY f.fee_id ORDER BY f.kind""",(student,))
        fees={r["kind"]:{"price":int(r["price"]),"paid":int(r["paid"])} for r in c.fetchall()}
        c.execute("""SELECT p.period_no,p.starts,p.ends,p.price,
                  COALESCE(SUM(a.amount) FILTER(WHERE a.active),0) AS paid
             FROM monthly_periods p LEFT JOIN monthly_allocations a ON a.period_id=p.period_id
             WHERE p.student_id=%s GROUP BY p.period_id ORDER BY p.period_no""",(student,))
        periods=[{"no":r["period_no"],"start":r["starts"],"end":r["ends"],
                  "price":int(r["price"]),"paid":int(r["paid"])} for r in c.fetchall()]
        c.execute("""SELECT receipt_id,amount,received_on,payer,created_by,state
                FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id DESC""",(student,))
        receipts=[dict(row) for row in c.fetchall()]
    paid_count=sum(1 for x in periods if x["paid"]==x["price"])
    contiguous=0
    for p in periods:
        if p["no"]!=contiguous or p["paid"]<p["price"]:
            break
        contiguous+=1
    currently_due=sum(max(0,p["price"]-p["paid"]) for p in periods
                      if p["start"]<=day)
    currently_due+=sum(max(0,r["price"]-r["paid"]) for r in fees.values()
                       if r is not None)
    not_yet_due=sum(max(0,p["price"]-p["paid"]) for p in periods if p["start"]>day)
    unpaid=next((p for p in periods if p["paid"]<p["price"]),None)
    next_start=(unpaid["start"] if unpaid else anniversary(account["start_date"],contiguous))
    return {"account":dict(account),"fees":fees,"periods":periods,"receipts":receipts,
            "paid_periods":paid_count,"paid_through":(anniversary(account["start_date"],contiguous)
                 if contiguous else None),"due_now":currently_due,
            "future_partial":not_yet_due,"next_unpaid":next_start,
            "exempt":account["status"]=="exempt"}


def financial_report(conn, start, end):
    """Receipts counted once. Historical unclassified cash remains separate."""
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
             WHERE a.active AND r.state='active' AND r.received_on BETWEEN %s AND %s
             GROUP BY f.kind""",(start,end))
        fee_cash={r["kind"]:int(r["n"]) for r in c.fetchall()}
        c.execute("""SELECT COALESCE(SUM(a.amount),0) AS n FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             JOIN monthly_periods p ON p.period_id=a.period_id
             WHERE a.active AND r.state='active' AND r.received_on BETWEEN %s AND %s""",(start,end))
        monthly_cash=int(c.fetchone()["n"])
        c.execute("""SELECT COALESCE(SUM(a.amount),0) AS n FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             JOIN monthly_periods p ON p.period_id=a.period_id
             WHERE a.active AND r.state='active' AND r.received_on BETWEEN %s AND %s
             AND p.starts > r.received_on""",(start,end))
        prepaid=int(c.fetchone()["n"])
        c.execute("""SELECT COUNT(*) AS n FROM monthly_fees f
             WHERE f.kind='registration' AND f.price>0 AND
              (SELECT COALESCE(SUM(a.amount),0) FROM monthly_allocations a
               WHERE a.fee_id=f.fee_id AND a.active)=f.price""")
        paid_regs=int(c.fetchone()["n"])
        c.execute("""SELECT COUNT(*) AS n FROM monthly_fees f
             WHERE f.kind='gilet' AND
              (SELECT COALESCE(SUM(a.amount),0) FROM monthly_allocations a
               WHERE a.fee_id=f.fee_id AND a.active)=f.price""")
        paid_gilets=int(c.fetchone()["n"])
        c.execute("SELECT COALESCE(SUM(amount),0) AS n FROM payments WHERE payment_date BETWEEN %s AND %s",(start,end))
        old_cash=c.fetchone()["n"]
        c.execute("SELECT COALESCE(SUM(amount_paid),0) AS n FROM expenses WHERE expense_date BETWEEN %s AND %s",(start,end))
        expenses=c.fetchone()["n"]
        c.execute("SELECT COALESCE(SUM(amount),0) AS n FROM teacher_payments WHERE payment_date BETWEEN %s AND %s",(start,end))
        salaries=c.fetchone()["n"]
    outstanding=sum(projection(conn,s,end,materialize=False)["due_now"] for s in students)
    # Legacy rows are denominated according to their original receipt currency
    # (the existing UI describes shekels). Never add or subtract them from MRU.
    total_cash=cash
    outflow=expenses+salaries
    return {"registration_children":paid_regs,"registration_cash":fee_cash.get("registration",0),
            "gilet_count":paid_gilets,"gilet_cash":fee_cash.get("gilet",0),
            "monthly_cash":monthly_cash,"prepaid_cash":prepaid,"new_cash":cash,
            "historical_cash":old_cash,"total_cash":total_cash,
            "expenses":outflow,"remaining_cash":None,"due_now":outstanding}
