"""Read-only, bounded receipt/child audit queries over durable PostgreSQL evidence.

No UI state, mutation, or assumed legacy actors. Every receipt ID is the
actual monthly_receipts primary key; a month is never an invented receipt.
"""
from datetime import date
from monthly_finance import today

ACTION_LABELS = {
    'gilet_sold':'بيع جيليه وتسليمها',
    'gilet_sale_corrected':'تصحيح وصل جيليه',
    'gilet_delivered':'تسليم جيليه — دون قبض',
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
        c.execute("""SELECT a.allocation_id,a.amount,a.active,s.fee_kind,
             s.period_no,s.starts,s.ends,s.stored_fee_price,s.source AS snapshot_source
          FROM monthly_allocations a
          LEFT JOIN monthly_allocation_snapshots s ON s.allocation_id=a.allocation_id
          WHERE a.receipt_id=%s ORDER BY a.allocation_id""",(int(receipt_id),))
        items=[dict(r) for r in c.fetchall()]
        c.execute("""SELECT receipt_id,amount,received_on,state
                     FROM monthly_receipts WHERE corrects_id=%s
                     ORDER BY receipt_id""",(int(receipt_id),))
        replacements=[dict(r) for r in c.fetchall()]
    if any(i['snapshot_source'] is None for i in items):
        raise ValueError('تفصيل الوصل الثابت غير مكتمل؛ يلزم تدقيقه قبل التصدير.')
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


def history(conn, *, student_id=None, receipt_id=None, action=None, state=None, query="",
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
    if state and state!="all":
        if state not in ("active","cancelled","corrected"):
            raise ValueError("حالة الوصل غير معروفة.")
        status=("EXISTS(SELECT 1 FROM monthly_receipts v "
                "WHERE v.corrects_id=r.receipt_id)" if state=="corrected"
                else "r.state=%s")
        terms.append(status)
        if state!="corrected": params.append(state)
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
    base=""" FROM monthly_audit h LEFT JOIN students s ON s.student_id=h.student_id
             LEFT JOIN monthly_receipts r ON r.receipt_id=h.receipt_id """
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n"+base+where,tuple(params))
        total=int(c.fetchone()["n"])
        c.execute("""SELECT h.audit_id,h.student_id,h.receipt_id,h.action,h.actor,
             h.happened_at,h.reason,h.before_state,h.after_state,
             s.full_name AS student_name,r.received_on AS payment_date,
             r.state AS receipt_state,
             (h.happened_at AT TIME ZONE 'Africa/Nouakchott') AS business_time
             """+base+where+""" ORDER BY h.happened_at DESC,h.audit_id DESC
             LIMIT %s OFFSET %s""",(*params,page_size,(page-1)*page_size))
        rows=[dict(x) for x in c.fetchall()]
    return {"total":total,"page":page,"page_size":page_size,
            "pages":(total+page_size-1)//page_size,"rows":rows}


def receipt_impact(conn, receipt_id, *, new_amount=None,
                   new_date=None, new_payer=None):
    """Read-only, exact next-allocation simulation on the stored fee snapshots.

    Confirmation uses the returned audit revision under an account row lock,
    reruns the canonical allocation service, and refuses stale states. This is
    a preview, NOT a reservation or an accounting event.
    """
    from monthly_finance import (anniversary, receipt_revision, projection,
                                 amount, CURRENCY)
    data=receipt_detail(conn,receipt_id)
    row=data["receipt"]
    if row["state"]!="active":
        raise ValueError("الوصل غير ساري؛ افتح آخر نسخة صحيحة.")
    desired=int(row["amount"]) if new_amount is None else amount(new_amount)
    day=row["received_on"] if new_date is None else new_date
    payer=row["payer"] if new_payer is None else str(new_payer).strip()
    if isinstance(day,str): day=date.fromisoformat(day)
    if not isinstance(day,date) or not date(1990,1,1)<=day<=today():
        raise ValueError("التاريخ المصحح غير صالح.")
    if not payer or len(payer)>150:
        raise ValueError("اسم الدافع غير صالح.")
    student=row["student_id"]
    with conn.cursor() as c:
        c.execute('SELECT gilet_sale_id FROM monthly_allocations WHERE receipt_id=%s AND gilet_sale_id IS NOT NULL',(receipt_id,))
        garment=c.fetchone()
    if garment:
        if desired!=int(row['amount']):raise ValueError('لتغيير ثمن بيع الجيليه، ألغِ البيع ثم سجّل بيعًا صحيحًا.')
        current=projection(conn,student,materialize=False)
        return dict(revision=receipt_revision(conn,student),receipt=data,new_amount=desired,new_date=day,new_payer=payer,
            cash_delta=0,currently_due=current['due_now'],projected_due=current['due_now'],
            affected_periods=[receipt_line(i) for i in data['items']],
            new_items=[dict(kind='gilet',label='الجيليه',start=None,price=desired,previously_paid=0,waived=0,amount=desired)])
    with conn.cursor() as c:
        c.execute("""SELECT status,start_date,departure_on,due_at_period_end FROM monthly_accounts
                     WHERE student_id=%s""",(student,))
        account=c.fetchone()
        if not account or account["status"]!="regular":
            raise ValueError("لا يقبل حساب معفى تغيير قبض.")
        c.execute("""SELECT f.fee_id,f.kind,f.price,
                   COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
                      WHERE a.fee_id=f.fee_id AND a.active
                        AND a.receipt_id<>%s),0) AS paid,
                   COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                      WHERE w.fee_id=f.fee_id),0) AS waived
                   FROM monthly_fees f WHERE f.student_id=%s""",
                  (receipt_id,student))
        fees={r["kind"]:dict(r) for r in c.fetchall()}
        c.execute("""SELECT p.period_id,p.period_no,p.starts,p.ends,p.price,
                   COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
                      WHERE a.period_id=p.period_id AND a.active
                        AND a.receipt_id<>%s),0) AS paid,
                   COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w
                      WHERE w.period_id=p.period_id),0) AS waived
                   FROM monthly_periods p WHERE p.student_id=%s
                   ORDER BY p.period_no""",(receipt_id,student))
        periods={r["period_no"]:dict(r) for r in c.fetchall()}
        c.execute("SELECT tuition FROM monthly_tariffs WHERE id=1")
        tariff=c.fetchone()
    selected={x["fee_kind"] for x in data["items"] if x["fee_kind"]}
    cash_left=desired
    prospective=[]
    for kind in ("registration","gilet"):
        if kind not in selected: continue
        fee=fees.get(kind)
        if not fee: raise ValueError("الرسم الأصلي لم يعد موجوداً؛ يلزم مراجعة.")
        owed=int(fee["price"])-int(fee["paid"])-int(fee["waived"])
        if owed<0: raise ValueError("تجاوز رصيد رسم محفوظ؛ توقف للمراجعة.")
        if owed>cash_left: raise ValueError("المبلغ المصحح لا يغطي الرسم المحدد.")
        if owed:
            prospective.append({"kind":kind,"label":"رسوم التسجيل" if kind=="registration"
                else "الجيليه","start":None,"price":int(fee["price"]),
                "previously_paid":int(fee["paid"]),"waived":int(fee["waived"]),
                "amount":owed})
            cash_left-=owed
    index=0
    while cash_left:
        if index>=1200: raise ValueError("التخصيص يتجاوز الحد المسموح.")
        p=periods.get(index)
        if p is None:
            if account["departure_on"]:
                raise ValueError("لا يمكن إضافة أشهر بعد مغادرة الطفل.")
            if not tariff: raise ValueError("رسوم الشهور غير مضبوطة.")
            starts=anniversary(account["start_date"],index)
            p={"starts":starts,"ends":anniversary(account["start_date"],index+1),
               "price":int(tariff["tuition"]),"paid":0,"waived":0}
        owed=int(p["price"])-int(p["paid"])-int(p["waived"])
        if owed<0: raise ValueError("رصيد شهر محفوظ غير متسق.")
        allocated=min(cash_left,owed)
        if allocated:
            label=f"الشهر {index+1}: {p['starts']} — {p['ends']}"
            prospective.append({"kind":"month","label":label,"start":p["starts"],"end":p["ends"],
                "price":int(p["price"]),"previously_paid":int(p["paid"]),
                "waived":int(p["waived"]),"amount":allocated})
            cash_left-=allocated
        index+=1
    if sum(x["amount"] for x in prospective)!=desired:
        raise ValueError("التخصيص المصحح لا يطابق المبلغ.")
    current=projection(conn,student,materialize=False)
    cutoff=min(today(),account["departure_on"]) if account["departure_on"] else today()
    # The original receipt was valid and recognized before replacement.
    original_due_coverage=sum(int(x["amount"]) for x in data["items"]
        if x["fee_kind"] or ((x["ends"] if account.get("due_at_period_end") else x["starts"]) and (x["ends"] if account.get("due_at_period_end") else x["starts"])<=cutoff))
    corrected_due_coverage=sum(x["amount"] for x in prospective
        if x["kind"]!="month" or (x["end"] if account.get("due_at_period_end") else x["start"])<=cutoff)
    projected_due=(int(current["due_now"])+original_due_coverage-
                   corrected_due_coverage) if current else None
    return {"revision":receipt_revision(conn,student),"receipt":data,
            "new_amount":desired,"new_date":day,"new_payer":payer,
            "cash_delta":desired-int(row["amount"]),
            "currently_due":current["due_now"] if current else None,
            "projected_due":max(0,projected_due) if projected_due is not None else None,
            "affected_periods":[receipt_line(i) for i in data["items"]],
            "new_items":prospective}
