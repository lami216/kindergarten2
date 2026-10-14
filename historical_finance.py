"""Audited preservation of legacy annual receipts (original currency unchanged).

Historical monetary figures are not converted to the new monthly currency.
Cancellation is a state transition, never DELETE; original values and every
correction are retained for review. All mutations use isolated transactions.
"""
import json
from decimal import Decimal, InvalidOperation

import db


def _snapshot(row):
    return {key: (str(value) if isinstance(value, Decimal) else value)
            for key, value in dict(row).items()}


def _positive_legacy_amount(value):
    try:
        total = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError("أدخل مبلغًا نقديًا صحيحًا.")
    if not total.is_finite() or total <= 0 or total > Decimal("99999999.99"):
        raise ValueError("المبلغ خارج النطاق المسموح.")
    if total.as_tuple().exponent < -2:
        raise ValueError("الدفعات التاريخية تقبل منزلتين عشريتين فقط.")
    return total


def _audit(cur, receipt, action, actor, reason, before, after):
    cur.execute("""INSERT INTO historical_payment_audit
       (receipt_number,action,actor,reason,before_state,after_state)
       VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
       (receipt,action,actor.strip()[:100],reason,
        json.dumps(before,ensure_ascii=False,default=str),
        json.dumps(after,ensure_ascii=False,default=str)))


def change_receipt(receipt_number, *, actor, reason, cancel=False,
                   new_amount=None, payer=None, payment_for=None, details=None, on_date=None, expected=None):
    """Safely edit or void a legacy receipt, keeping the row and audit evidence.

    Returns its historical registration ID so the existing annual registration
    status can be refreshed after committing; never alters monthly accounts.
    """
    if not actor or not actor.strip():
        raise ValueError("يجب معرفة المستخدم المسؤول عن العملية.")
    if not reason or not reason.strip():
        raise ValueError("اذكر سبب الإلغاء أو التصحيح.")
    if not cancel:
        money = _positive_legacy_amount(new_amount)
        if not payer or not payer.strip() or len(payer.strip()) > 100:
            raise ValueError("اسم الدافع مطلوب.")
        if not payment_for or len(payment_for) > 50:
            raise ValueError("اختر نوع الدفعة.")
        if details is not None and len(details) > 2000:
            raise ValueError("تفاصيل الدفعة أطول من المسموح.")
    conn = db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import record_history
            record_history.context(c,actor,reason)
            c.execute("SELECT * FROM payments WHERE receipt_number=%s FOR UPDATE",
                      (receipt_number,))
            original=c.fetchone()
            if not original:
                raise ValueError("الوصل غير موجود.")
            if expected is not None:
                import records
                if records.revision(original)!=expected: raise ValueError('تغيّر الوصل؛ حدّث بياناته قبل الحفظ.')
            if original["receipt_state"] != "active":
                raise ValueError("الوصل ملغى بالفعل، ولا يمكن تعديله.")
            previous=_snapshot(original)
            if cancel:
                c.execute("""UPDATE payments SET receipt_state='cancelled',
                       cancelled_at=now(),cancelled_by=%s,cancel_reason=%s
                       WHERE receipt_number=%s RETURNING *""",
                       (actor.strip()[:100],reason.strip(),receipt_number))
                action="legacy_receipt_cancelled"
            else:
                from datetime import date
                from monthly_finance import today
                day=date.fromisoformat(str(on_date or original['payment_date']))
                if day>today(): raise ValueError('تاريخ القبض لا يكون مستقبليًا.')
                c.execute("""UPDATE payments SET amount=%s,payer_name=%s,
                       payment_for=%s,payment_for_other=%s,payment_date=%s
                       WHERE receipt_number=%s RETURNING *""",
                       (money,payer.strip(),payment_for,details or None,day,receipt_number))
                action="legacy_receipt_corrected"
            after=_snapshot(c.fetchone())
            _audit(c,receipt_number,action,actor,reason.strip(),previous,after)
            registration_id=original["registration_id"]
        conn.commit()
        return registration_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
