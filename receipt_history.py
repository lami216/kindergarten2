"""Read-only, bounded receipt/child audit queries over durable PostgreSQL evidence.

No UI state, mutation, or assumed legacy actors. Every receipt ID is the
actual monthly_receipts primary key; a month is never an invented receipt.
"""
from datetime import date
from monthly_finance import today

ACTION_LABELS = {
    "receipt_issued":"قبض موثق",
    "receipt_cancelled":"إلغاء وصل",
    "receipt_corrected":"تصحيح وصل",
    "debt_waived_non_cash":"إلغاء دين — دون قبض",
    "student_archived":"أرشفة طفل",
    "existing_account_setup":"تهيئة حساب دون قبض",
    "exemption":"إعفاء كامل",
    "tariff_change":"تعديل الأسعار",
}


def receipt_detail(conn, receipt_id, *, student_id=None):
    """Actual immutable source receipt plus all original allocation records."""
    with conn.cursor() as c:
        c.execute("""SELECT r.*,s.full_name AS student_name,s.archived_at AS child_archived
          FROM monthly_receipts r JOIN students s ON s.student_id=r.student_id
          WHERE r.receipt_id=%s""",(int(receipt_id),))
        row=c.fetchone()
        if row is None or (student_id is not None and row["student_id"]!=student_id):
            raise ValueError("الوصل غير موجود في ملف الطفل.")
        receipt=dict(row)
        c.execute("""SELECT a.allocation_id,a.amount,a.active,f.kind AS fee_kind,
             p.period_no,p.starts,p.ends,
             COALESCE(f.price,p.price) AS stored_fee_price
          FROM monthly_allocations a
          LEFT JOIN monthly_fees f ON f.fee_id=a.fee_id
          LEFT JOIN monthly_periods p ON p.period_id=a.period_id
          WHERE a.receipt_id=%s ORDER BY a.allocation_id""",(int(receipt_id),))
        items=[dict(r) for r in c.fetchall()]
        c.execute("""SELECT receipt_id,amount,received_on,state
                     FROM monthly_receipts WHERE corrects_id=%s
                     ORDER BY receipt_id""",(int(receipt_id),))
        replacements=[dict(r) for r in c.fetchall()]
    if sum(int(i["amount"]) for i in items)!=int(receipt["amount"]):
        raise ValueError("أصل الوصل وتفصيل تخصيصاته غير متطابقين؛ يلزم تدقيق مالي.")
    return {"receipt":receipt,"items":items,"replacements":replacements}


def receipt_line(item):
    if item["fee_kind"]=="registration":
        return "رسوم التسجيل"
    if item["fee_kind"]=="gilet":
        return "الجيليه"
    if item["period_no"] is not None:
        from datetime import timedelta
        last=item["ends"]-timedelta(days=1)
        return f"الشهر {int(item['period_no'])+1}: {item['starts']} — {last}"
    return "تخصيص غير معروف"


def history(conn, *, student_id=None, receipt_id=None, action=None, query="",
            start=None, end=None, page=1, page_size=15):
    """A single permission-scoped UI caller uses this stable paginated ledger."""
    if page_size<1 or page_size>50 or page<1 or page>1_000_000:
        raise ValueError("إعدادات التصفح غير صالحة.")
    if start and isinstance(start,str): start=date.fromisoformat(start)
    if end and isinstance(end,str): end=date.fromisoformat(end)
    if start and end and start>end:
        raise ValueError("الفترة الزمنية غير صالحة.")
    terms=[]
    params=[]
    if student_id is not None:
        terms.append("h.student_id=%s")
        params.append(student_id)
    if receipt_id is not None:
        terms.append("""(h.receipt_id=%s OR
            EXISTS(SELECT 1 FROM monthly_receipts r
                   WHERE r.receipt_id=h.receipt_id AND r.corrects_id=%s) OR
            EXISTS(SELECT 1 FROM monthly_receipts r
                   WHERE r.receipt_id=%s AND r.corrects_id=h.receipt_id))""")
        params.extend([int(receipt_id)]*3)
    if action and action!="all":
        terms.append("h.action=%s")
        params.append(action)
    if start:
        terms.append("(h.happened_at AT TIME ZONE 'Africa/Nouakchott')::date >= %s")
        params.append(start)
    if end:
        terms.append("(h.happened_at AT TIME ZONE 'Africa/Nouakchott')::date <= %s")
        params.append(end)
    q=str(query or "").strip()[:120]
    if q:
        terms.append("""(s.full_name ILIKE %s OR h.actor ILIKE %s OR
          COALESCE(h.reason,'') ILIKE %s OR
          CAST(h.receipt_id AS TEXT) = %s OR CAST(h.student_id AS TEXT) ILIKE %s)""")
        params.extend([f"%{q}%",f"%{q}%",f"%{q}%",q,f"%{q}%"])
    where="WHERE "+" AND ".join(terms) if terms else ""
    base=""" FROM monthly_audit h LEFT JOIN students s ON s.student_id=h.student_id """
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n"+base+where,tuple(params))
        total=int(c.fetchone()["n"])
        c.execute("""SELECT h.audit_id,h.student_id,h.receipt_id,h.action,h.actor,
             h.happened_at,h.reason,h.before_state,h.after_state,
             s.full_name AS student_name,
             (h.happened_at AT TIME ZONE 'Africa/Nouakchott') AS business_time
             """+base+where+""" ORDER BY h.happened_at DESC,h.audit_id DESC
             LIMIT %s OFFSET %s""",(*params,page_size,(page-1)*page_size))
        rows=[dict(x) for x in c.fetchall()]
    return {"total":total,"page":page,"page_size":page_size,
            "pages":(total+page_size-1)//page_size,"rows":rows}


def receipt_impact(conn, receipt_id, *, new_amount=None,
                   new_date=None, new_payer=None):
    """Non-mutating preview. Confirmation MUST compare its revision under lock.

    Exact real allocations are read from receipt_detail; prospective affected
    periods are identified and the post-save authoritative read is shown after
    commit. No claim is made that this preview reserves prices or periods.
    """
    from monthly_finance import receipt_revision, projection
    data=receipt_detail(conn,receipt_id)
    row=data["receipt"]
    if row["state"]!="active":
        raise ValueError("هذا الوصل ملغى؛ لا يمكن تغيير أثره.")
    if new_amount is not None and (isinstance(new_amount,bool) or
                                  not isinstance(new_amount,int) or new_amount<=0):
        raise ValueError("المبلغ الجديد غير صالح.")
    desired=row["amount"] if new_amount is None else new_amount
    day=row["received_on"] if new_date is None else new_date
    payer=row["payer"] if new_payer is None else str(new_payer).strip()
    if isinstance(day,str): day=date.fromisoformat(day)
    if not isinstance(day,date) or day>today() or day<date(1990,1,1):
        raise ValueError("التاريخ المصحح غير صالح.")
    if not payer or len(payer)>150: raise ValueError("اسم الدافع غير صالح.")
    current=projection(conn,row["student_id"],materialize=False)
    return {"revision":receipt_revision(conn,row["student_id"]),
            "receipt":data,"new_amount":int(desired),
            "new_date":day,"new_payer":payer,
            "cash_delta":int(desired)-int(row["amount"]),
            "currently_due":current["due_now"] if current else None,
            "affected_periods":[receipt_line(i) for i in data["items"]],
            "requires_refresh":True}
