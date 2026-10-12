"""Transactional cash-preserving payroll operations for salary slips and advances.

Cancellation retires a document but NEVER means cash was refunded. Actual
original outflow stays in cash_amount and remains in every cash report.
"""
import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
import db
from monthly_finance import today as business_today


def _cash(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("أدخل مبلغاً نقدياً صحيحاً.")
    if not value.is_finite() or value <= 0 or value > Decimal("99999999.99") or value.as_tuple().exponent < -2:
        raise ValueError("المبلغ خارج النطاق المسموح.")
    return value.quantize(Decimal(".01"))


def _fingerprint(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def _audit(c, table, ident, action, actor, reason, before, after):
    column = "payment_id" if table == "teacher_payments" else "advance_id"
    c.execute(f"""INSERT INTO payroll_audit
       ({column},action,actor,reason,before_state,after_state)
       VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
       (ident,action,actor,reason,
        json.dumps(dict(before or {}),ensure_ascii=False,default=str),
        json.dumps(dict(after or {}),ensure_ascii=False,default=str)))


def _actor(actor):
    if not str(actor or "").strip():
        raise ValueError("يجب تحديد المستخدم المسؤول.")
    return str(actor).strip()[:100]


def _month(text):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",str(text)):
        raise ValueError("شهر الصرف يجب أن يكون YYYY-MM.")
    return str(text)


def _insert(table, national_id, args, *, token=None, actor):
    who = _actor(actor)
    token = str(token or uuid.uuid4())
    try:
        token = str(uuid.UUID(token))
    except ValueError:
        raise ValueError("رمز طلب الحفظ غير صحيح.")
    payload = {"table":table,"national_id":national_id,**args}
    fp = _fingerprint(payload)
    conn = db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            # Transactional advisory lock serializes retries with identical IDs.
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (token,))
            c.execute(f"SELECT * FROM {table} WHERE request_token=%s", (token,))
            previous = c.fetchone()
            if previous:
                if previous["request_hash"] != fp:
                    raise ValueError("تعارض رمز الحفظ: نفس الطلب يحتوي على بيانات مختلفة.")
                conn.commit()
                return previous["payment_id" if table=="teacher_payments" else "advance_id"],False
            c.execute("SELECT national_id FROM teachers WHERE national_id=%s AND archived_at IS NULL FOR UPDATE",
                      (national_id,))
            if not c.fetchone():
                raise ValueError("لا يمكن صرف مبالغ لمعلمة مؤرشفة أو غير موجودة.")
            if table=="teacher_payments":
                c.execute("""INSERT INTO teacher_payments
                    (national_id,amount,cash_amount,payment_date,salary_month,
                     base_salary,bonus,deductions,notes,request_token,request_hash)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING payment_id""",
                    (national_id,args["amount"],args["amount"],args["date"],args["month"],
                     args["base"],args["bonus"],args["deductions"],args["notes"],token,fp))
                ident=c.fetchone()["payment_id"]
            else:
                c.execute("""INSERT INTO teacher_advances
                    (national_id,amount,cash_amount,advance_date,salary_month,
                     notes,request_token,request_hash)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING advance_id""",
                    (national_id,args["amount"],args["amount"],args["date"],args["month"],
                     args["notes"],token,fp))
                ident=c.fetchone()["advance_id"]
            c.execute(f"SELECT * FROM {table} WHERE "+("payment_id" if table=="teacher_payments" else "advance_id")+"=%s",(ident,))
            _audit(c,table,ident,"cash_disbursed",who,"صرف نقدي فعلي",{},c.fetchone())
        conn.commit()
        return ident,True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_salary(national_id, month, base, bonus=0, deductions=0,
                notes="", *, actor, token=None, on_date=None):
    base,bonus,deductions=(Decimal(str(v)) for v in (base,bonus,deductions))
    if any(v<0 or not v.is_finite() or v.as_tuple().exponent < -2 for v in (base,bonus,deductions)):
        raise ValueError("قيمة الراتب أو الخصم غير صحيحة.")
    total=_cash(base+bonus-deductions)
    return _insert("teacher_payments",str(national_id),
        {"amount":total,"date":str(on_date or business_today()),"month":_month(month),
         "base":base,"bonus":bonus,"deductions":deductions,"notes":str(notes or "")},
        actor=actor,token=token)


def save_advance(national_id, month, cash, notes="", *, actor, token=None,on_date=None):
    return _insert("teacher_advances",str(national_id),
        {"amount":_cash(cash),"date":str(on_date or business_today()),"month":_month(month),
         "notes":str(notes or "")},actor=actor,token=token)


def amend(table, ident, *, actor, reason, cancel=False, month=None, notes=None):
    """Document correction/void, not a refund: cash_amount never changes."""
    if table not in ("teacher_payments","teacher_advances"):
        raise ValueError("نوع القسيمة غير صالح.")
    actor=_actor(actor)
    reason=str(reason or "").strip()
    if not reason:
        raise ValueError("اذكر سبب التصحيح أو الإلغاء.")
    column="payment_id" if table=="teacher_payments" else "advance_id"
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute(f"SELECT * FROM {table} WHERE {column}=%s FOR UPDATE",(ident,))
            old=c.fetchone()
            if not old: raise ValueError("القسيمة غير موجودة.")
            if old["record_state"]!="active":
                raise ValueError("القسيمة ملغاة بالفعل.")
            if cancel:
                c.execute(f"UPDATE {table} SET record_state='cancelled' WHERE {column}=%s RETURNING *",(ident,))
                action="document_cancelled_cash_retained"
            else:
                c.execute(f"""UPDATE {table} SET salary_month=%s,notes=%s
                    WHERE {column}=%s RETURNING *""",
                    (_month(month),str(notes or ""),ident))
                action="document_corrected"
            new=c.fetchone()
            _audit(c,table,ident,action,actor,reason,old,new)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def archive_teacher(national_id, *, actor):
    actor=_actor(actor)
    connection=db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            c.execute("""UPDATE teachers SET archived_at=now(),archived_by=%s
                      WHERE national_id=%s AND archived_at IS NULL RETURNING national_id""",
                      (actor,national_id))
            if not c.fetchone():
                raise ValueError("ملف المعلمة مؤرشف أو غير موجود.")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
