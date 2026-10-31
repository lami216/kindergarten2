"""Cancel one legacy garment obligation while carrying the mixed receipt intact."""
import uuid
import db
import monthly_finance as F
import record_history as H


def migrate(c):
    c.execute('''ALTER TABLE monthly_allocations ADD COLUMN IF NOT EXISTS copied_from_id BIGINT
            REFERENCES monthly_allocations(allocation_id) ON DELETE RESTRICT;
        CREATE TABLE IF NOT EXISTS monthly_gilet_cancellations (
            request_token UUID PRIMARY KEY,request_hash VARCHAR(64) NOT NULL,
            receipt_id BIGINT NOT NULL UNIQUE REFERENCES monthly_receipts(receipt_id) ON DELETE RESTRICT,
            replacement_id BIGINT NOT NULL UNIQUE REFERENCES monthly_receipts(receipt_id) ON DELETE RESTRICT,
            fee_id BIGINT NOT NULL UNIQUE REFERENCES monthly_fees(fee_id) ON DELETE RESTRICT,
            amount BIGINT NOT NULL CHECK(amount>0 AND amount<=1000000000),
            actor TEXT NOT NULL,reason TEXT NOT NULL,
            cancelled_at TIMESTAMPTZ NOT NULL DEFAULT now());''')


def _plan(c,rid):
    c.execute('SELECT r.*,s.full_name AS student_name FROM monthly_receipts r JOIN students s USING(student_id) WHERE receipt_id=%s',(rid,))
    row=c.fetchone()
    if not row:raise ValueError('الوصل غير موجود.')
    row=dict(row)
    if row['state']!='active':raise ValueError('الوصل ملغى أو مصحح؛ افتح آخر نسخة سارية.')
    c.execute('''SELECT a.*,s.fee_kind,s.period_no,s.starts,s.ends,s.stored_fee_price,s.source
        FROM monthly_allocations a LEFT JOIN monthly_allocation_snapshots s USING(allocation_id)
        WHERE a.receipt_id=%s AND a.active ORDER BY a.allocation_id''',(rid,))
    items=[dict(x) for x in c.fetchall()]
    garment=[x for x in items if x['fee_kind']=='gilet']
    if not garment:raise ValueError('لا يوجد بند جيليه قابل للإلغاء في هذا الوصل.')
    if any(x['gilet_sale_id'] is not None for x in items):raise ValueError('بيع الجيليه المستقل يُلغى من إجراء إلغاء الوصل المعتاد.')
    if any(x['source'] is None for x in items) or sum(int(x['amount']) for x in items)!=int(row['amount']):
        raise ValueError('تفصيل الوصل غير مكتمل؛ يلزم تدقيقه قبل التصحيح.')
    targets={x['fee_id'] for x in garment}
    if len(targets)!=1 or None in targets:raise ValueError('بند الجيليه موزع على استحقاقات متعددة؛ يلزم تدقيقه أولًا.')
    fee=next(iter(targets));amount=sum(int(x['amount']) for x in garment)
    if amount>=int(row['amount']):raise ValueError('الوصل خاص بالجيليه وحدها؛ استخدم إجراء إلغاء الوصل المعتاد.')
    c.execute('''SELECT f.*,COALESCE((SELECT SUM(a.amount) FROM monthly_allocations a
            JOIN monthly_receipts r USING(receipt_id) WHERE a.fee_id=f.fee_id AND a.active AND r.state='active'),0) AS paid,
            COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w WHERE w.fee_id=f.fee_id),0) AS waived,
            EXISTS(SELECT 1 FROM monthly_gilet_cancellations x WHERE x.fee_id=f.fee_id) AS cancelled
            FROM monthly_fees f WHERE f.fee_id=%s''',(fee,))
    charge=c.fetchone()
    if not charge or charge['student_id']!=row['student_id'] or charge['kind']!='gilet':raise ValueError('استحقاق الجيليه غير مطابق للطالب.')
    if charge['cancelled']:raise ValueError('بند الجيليه ملغى بالفعل.')
    if amount!=int(charge['price']) or int(charge['paid'])!=amount or int(charge['waived']):
        raise ValueError('رسم الجيليه جزئي أو موزع على وصولات أو إسقاطات؛ لا يمكن إلغاء جزء منه تلقائيًا.')
    return row,items,fee,amount


def preview(conn,rid):
    import access_control as A
    with conn.cursor() as c:
        A.require(c,'payments.view',lock=False)
        try:row,items,fee,amount=_plan(c,rid)
        except ValueError as error:
            return dict(eligible=False,reason=str(error),revision=0)
        return dict(eligible=True,id=rid,student=row['student_id'],name=row['student_name'],
            revision=F.receipt_revision(conn,row['student_id']),gilet=amount,
            registration=sum(int(x['amount']) for x in items if x['fee_kind']=='registration'),
            monthly=sum(int(x['amount']) for x in items if x['period_id'] is not None),
            original=int(row['amount']),remaining=int(row['amount'])-amount,date=row['received_on'],
            can_cancel=A.can('payments.delete') and A.can('accounts.delete'))


def eligible_receipts(conn):
    """One batched availability query for the roster; execution still rechecks."""
    with conn.cursor() as c:
        c.execute('''WITH paid AS (
            SELECT a.fee_id,SUM(a.amount) AS amount FROM monthly_allocations a
            JOIN monthly_receipts r USING(receipt_id) WHERE a.active AND r.state='active' GROUP BY a.fee_id
        ), waived AS (SELECT fee_id,SUM(amount) AS amount FROM monthly_waivers GROUP BY fee_id)
        SELECT r.receipt_id FROM monthly_receipts r JOIN monthly_allocations a USING(receipt_id)
            LEFT JOIN monthly_fees f USING(fee_id) LEFT JOIN paid p USING(fee_id)
            LEFT JOIN waived w USING(fee_id) LEFT JOIN monthly_gilet_cancellations x USING(fee_id)
            LEFT JOIN monthly_allocation_snapshots s USING(allocation_id)
            WHERE r.state='active' AND a.active GROUP BY r.receipt_id
            HAVING COUNT(DISTINCT f.fee_id) FILTER(WHERE f.kind='gilet')=1
                AND COUNT(*) FILTER(WHERE a.gilet_sale_id IS NOT NULL)=0
                AND COUNT(*) FILTER(WHERE s.allocation_id IS NULL)=0
                AND SUM(a.amount)=MAX(r.amount)
                AND SUM(a.amount) FILTER(WHERE f.kind='gilet')<MAX(r.amount)
                AND SUM(a.amount) FILTER(WHERE f.kind='gilet')=MAX(f.price) FILTER(WHERE f.kind='gilet')
                AND BOOL_AND(p.amount=f.price AND COALESCE(w.amount,0)=0 AND x.fee_id IS NULL) FILTER(WHERE f.kind='gilet')''')
        return {r['receipt_id'] for r in c.fetchall()}


def carry_receipt(c,old,items,*,actor,token,fingerprint,day=None,payer=None):
    """New rows only. The trigger validates and copies each frozen description."""
    total=sum(int(x['amount']) for x in items)
    F.amount(total)
    c.execute('''INSERT INTO monthly_receipts(student_id,amount,received_on,payer,request_token,
        request_hash,created_by,corrects_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING receipt_id''',
        (old['student_id'],total,day or old['received_on'],payer or old['payer'],token,fingerprint,actor,old['receipt_id']))
    new=c.fetchone()['receipt_id']
    for item in items:
        c.execute('''INSERT INTO monthly_allocations(receipt_id,fee_id,period_id,gilet_sale_id,amount,copied_from_id)
            VALUES(%s,%s,%s,%s,%s,%s)''',
            (new,item['fee_id'],item['period_id'],item.get('gilet_sale_id'),item['amount'],item['allocation_id']))
    return new


def cancel(rid,*,actor,reason,confirmed,token,expected_revision):
    import access_control as A
    if not str(reason or '').strip() or confirmed is not True or type(expected_revision) is not int:
        raise ValueError('اكتب سبب إلغاء الجيليه وأكد المبلغ بعد المعاينة.')
    token=str(uuid.UUID(str(token)));reason=reason.strip()
    fingerprint=F._hash(dict(action='gilet_item_cancel',receipt=int(rid),reason=reason,revision=expected_revision,confirmed=True))
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            actor=A.actor(c,'payments.delete',actor);A.require(c,'accounts.delete')
            c.execute('SELECT student_id FROM monthly_receipts WHERE receipt_id=%s',(rid,))
            child=c.fetchone()
            if not child:raise ValueError('الوصل غير موجود.')
            F._lock(c,child['student_id'],for_payment=False)
            c.execute('SELECT * FROM monthly_gilet_cancellations WHERE request_token=%s',(token,))
            duplicate=c.fetchone()
            if duplicate:
                if duplicate['request_hash']!=fingerprint:raise ValueError('تغيّرت بيانات طلب إلغاء الجيليه؛ افتح معاينة جديدة.')
                conn.commit();return dict(id=duplicate['replacement_id'],created=False,removed=int(duplicate['amount']))
            F._assert_receipt_revision(c,child['student_id'],expected_revision)
            row,items,fee,amount=_plan(c,rid)
            A.require(c,'payments.delete');H.context(c,actor,reason)
            F._cancel_in_tx(c,row['student_id'],rid,reason,actor)
            kept=[x for x in items if x['fee_kind']!='gilet']
            new=carry_receipt(c,row,kept,actor=actor,token=token,fingerprint=fingerprint)
            A.require(c,'accounts.delete')
            c.execute('''INSERT INTO monthly_gilet_cancellations(request_token,request_hash,receipt_id,
                replacement_id,fee_id,amount,actor,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                (token,fingerprint,rid,new,fee,amount,actor,reason))
            F._audit(c,row['student_id'],new,'gilet_item_cancelled',actor,
                dict(receipt_id=rid,amount=int(row['amount']),allocations=items),
                dict(receipt_id=new,corrects_id=rid,removed_gilet=amount,amount=int(row['amount'])-amount,
                    fee_id=fee,fee_cancelled=True,kept_allocations=[x['allocation_id'] for x in kept],
                    refund_recorded=False,physical_return_recorded=False),reason)
        conn.commit();return dict(id=new,created=True,removed=amount)
    except Exception:conn.rollback();raise
    finally:conn.close()
