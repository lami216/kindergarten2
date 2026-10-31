"""One paid garment per sale, on the existing cash ledger; no tuition debt."""
import uuid
from datetime import date
import db
import monthly_finance as F
import record_history as H
import records as R


def migrate(c):
    c.execute('''CREATE TABLE IF NOT EXISTS account_status_requests (
        request_token UUID PRIMARY KEY,request_hash TEXT NOT NULL,
        student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id) ON DELETE RESTRICT,
        waived BIGINT NOT NULL CHECK(waived>=0),actor TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
        CREATE TABLE IF NOT EXISTS gilet_sales (
        sale_id BIGSERIAL PRIMARY KEY,
        student_id VARCHAR(20) NOT NULL REFERENCES monthly_accounts(student_id) ON DELETE RESTRICT,
        price BIGINT NOT NULL CHECK(price>0 AND price<=1000000000),
        actor TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
        ALTER TABLE monthly_allocations ADD COLUMN IF NOT EXISTS gilet_sale_id BIGINT
            REFERENCES gilet_sales(sale_id) ON DELETE RESTRICT;
        ALTER TABLE monthly_allocations DROP CONSTRAINT IF EXISTS monthly_allocations_check;
        ALTER TABLE monthly_allocations DROP CONSTRAINT IF EXISTS monthly_allocation_target;
        ALTER TABLE monthly_allocations ADD CONSTRAINT monthly_allocation_target
            CHECK(num_nonnulls(fee_id,period_id,gilet_sale_id)=1);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_gilet_allocation
            ON monthly_allocations(gilet_sale_id) WHERE active AND gilet_sale_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS gilet_deliveries (
            delivery_id BIGSERIAL PRIMARY KEY,
            fee_id BIGINT UNIQUE REFERENCES monthly_fees(fee_id) ON DELETE RESTRICT,
            sale_id BIGINT UNIQUE REFERENCES gilet_sales(sale_id) ON DELETE RESTRICT,
            request_token UUID NOT NULL UNIQUE, request_hash TEXT NOT NULL,
            actor TEXT NOT NULL, reason TEXT NOT NULL,
            delivered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK(num_nonnulls(fee_id,sale_id)=1));''')


def purchases(conn,student):
    with conn.cursor() as c:
        c.execute('''SELECT f.fee_id AS id,'legacy' AS kind,f.price,
            COALESCE(SUM(a.amount) FILTER(WHERE a.active AND r.state='active'),0) AS paid,
            EXISTS(SELECT 1 FROM gilet_deliveries d WHERE d.fee_id=f.fee_id) AS delivered,
            NULL::bigint AS receipt,
            (COALESCE(SUM(a.amount) FILTER(WHERE a.active AND r.state='active'),0)<f.price
                AND bool_or(r.state='cancelled')) OR EXISTS(SELECT 1 FROM monthly_gilet_cancellations x WHERE x.fee_id=f.fee_id) AS cancelled,
            COALESCE((SELECT SUM(w.amount) FROM monthly_waivers w WHERE w.fee_id=f.fee_id),0) AS waived,
            COALESCE((SELECT x.amount FROM monthly_gilet_cancellations x WHERE x.fee_id=f.fee_id),0) AS cancelled_amount
            FROM monthly_fees f LEFT JOIN monthly_allocations a USING(fee_id)
            LEFT JOIN monthly_receipts r USING(receipt_id)
            WHERE f.student_id=%s AND f.kind='gilet' GROUP BY f.fee_id
            UNION ALL
            SELECT s.sale_id,'sale',s.price,
                COALESCE(SUM(a.amount) FILTER(WHERE a.active AND r.state='active'),0),
                EXISTS(SELECT 1 FROM gilet_deliveries d WHERE d.sale_id=s.sale_id),
                MAX(r.receipt_id),NOT bool_or(a.active AND r.state='active'),0,0
            FROM gilet_sales s JOIN monthly_allocations a ON a.gilet_sale_id=s.sale_id
            JOIN monthly_receipts r USING(receipt_id)
            WHERE s.student_id=%s GROUP BY s.sale_id ORDER BY kind,id''',(student,student))
        return [dict(x,due=max(0,int(x['price'])-int(x['paid'])-int(x['waived'])-int(x['cancelled_amount'])) if x['kind']=='legacy' else 0,
                     delivery_unknown=x['kind']=='legacy' and not x['delivered']) for x in c.fetchall()]


def preview(conn,student):
    import access_control as A
    with conn.cursor() as c:
        A.require(c,'payments.view',lock=False)
        c.execute('SELECT full_name FROM students WHERE student_id=%s',(student,))
        child=c.fetchone()
        if not child:raise ValueError('الطالب غير موجود.')
        tariff=F._tariffs(c)
    return dict(student=student,name=child['full_name'],price=tariff['gilet'],tariff_revision=F._hash(tariff),
        ledger_revision=F.receipt_revision(conn,student),purchases=purchases(conn,student))


def _day(value):
    day=date.fromisoformat(str(value))
    if not date(1990,1,1)<=day<=F.today():raise ValueError('تاريخ القبض غير صالح أو مستقبلي.')
    return day


def _child(c,student):
    # Match archive's child -> account lock order, including legacy mixed states.
    c.execute('SELECT archived_at FROM students WHERE student_id=%s FOR KEY SHARE',(student,))
    child=c.fetchone()
    if not child:raise ValueError('الطالب غير موجود.')
    return child


def issue(c,account,price,payer,actor,token,fingerprint,day,*,sale_id=None,corrects_id=None):
    """Caller owns account lock; only creates fully funded garment allocations."""
    H.context(c,actor,'تصحيح وصل جيليه' if corrects_id else 'بيع جيليه وتسليمها')
    if sale_id is None:
        c.execute('INSERT INTO gilet_sales(student_id,price,actor) VALUES(%s,%s,%s) RETURNING sale_id',
            (account['student_id'],price,actor))
        sale_id=c.fetchone()['sale_id']
    c.execute('''INSERT INTO monthly_receipts(student_id,amount,received_on,payer,request_token,request_hash,created_by,corrects_id)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING receipt_id''',
        (account['student_id'],price,day,payer,token,fingerprint,actor,corrects_id))
    rid=c.fetchone()['receipt_id']
    c.execute('INSERT INTO monthly_allocations(receipt_id,gilet_sale_id,amount) VALUES(%s,%s,%s)',(rid,sale_id,price))
    if corrects_id is None:
        c.execute('''INSERT INTO gilet_deliveries(sale_id,request_token,request_hash,actor,reason)
            VALUES(%s,%s,%s,%s,%s)''',(sale_id,token,fingerprint,actor,'قبض الثمن وتسليم جيليه واحدة'))
    F._audit(c,account['student_id'],rid,'gilet_sale_corrected' if corrects_id else 'gilet_sold',actor,{},
        dict(sale_id=sale_id,price=price,received_on=str(day),corrects_id=corrects_id,delivered=corrects_id is None))
    return rid


def sell(student,*,actor,price,tariff_revision,received_on,confirmed,token):
    if confirmed is not True:raise ValueError('أكد قبض الثمن وتسليم الجيليه.')
    price=F.amount(price);day=_day(received_on);token=str(uuid.UUID(str(token)))
    fingerprint=F._hash(dict(action='gilet.sell',student=student,price=price,tariff_revision=tariff_revision,
        day=str(day),confirmed=True))
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'payments.create',actor)
            child=_child(c,student)
            account=F._lock(c,student,for_payment=False)
            c.execute('SELECT receipt_id,request_hash FROM monthly_receipts WHERE request_token=%s',(token,))
            old=c.fetchone()
            if old:
                if old['request_hash']!=fingerprint:raise ValueError('تغيّرت بيانات طلب البيع؛ افتح نافذة جديدة.')
                conn.commit();return old['receipt_id'],False
            if child['archived_at'] or account['archived_at'] or account.get('departure_on'):raise ValueError('الملف مؤرشف أو متوقف؛ لا تقبل مبيعات جديدة.')
            tariff=F._tariffs(c)
            if price!=tariff['gilet'] or tariff_revision!=F._hash(tariff):raise ValueError('تغيّر سعر الجيليه؛ راجع السعر الجديد.')
            rid=issue(c,account,price,'ولي الأمر',actor,token,fingerprint,day)
        conn.commit();return rid,True
    except Exception:conn.rollback();raise
    finally:conn.close()


def deliver(student,fee,*,actor,reason,confirmed,token,expected_revision):
    if confirmed is not True or not str(reason or '').strip():raise ValueError('أكد التسليم واكتب السبب.')
    token=str(uuid.UUID(str(token)));reason=reason.strip()
    fingerprint=F._hash(dict(action='gilet.deliver',student=student,fee=fee,reason=reason,ledger=expected_revision))
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,'payments.edit',actor)
            child=_child(c,student)
            account=F._lock(c,student,for_payment=False)
            c.execute('SELECT request_hash FROM gilet_deliveries WHERE request_token=%s',(token,))
            old=c.fetchone()
            if old:
                if old['request_hash']!=fingerprint:raise ValueError('تغيّرت بيانات تأكيد التسليم.')
                conn.commit();return False
            if child['archived_at'] or account['archived_at']:raise ValueError('الملف مؤرشف؛ راجع الملف قبل التسليم.')
            F._assert_receipt_revision(c,student,expected_revision)
            c.execute('SELECT * FROM monthly_fees WHERE fee_id=%s AND student_id=%s AND kind=\'gilet\' FOR UPDATE',(fee,student))
            row=c.fetchone()
            items=purchases(conn,student)
            item=next((x for x in items if x['kind']=='legacy' and x['id']==fee),None)
            if not row or not item or item['paid']<item['price'] or item['price']<=0:raise ValueError('يلزم رسم جيليه مدفوع بالكامل بوصل ساري لتأكيد التسليم.')
            if item['delivered']:raise ValueError('سُجل تسليم هذه الجيليه بالفعل.')
            H.context(c,actor,reason)
            c.execute('INSERT INTO gilet_deliveries(fee_id,request_token,request_hash,actor,reason) VALUES(%s,%s,%s,%s,%s)',(fee,token,fingerprint,actor,reason))
            F._audit(c,student,None,'gilet_delivered',actor,dict(fee_id=fee,delivery='unknown'),dict(delivered=True,cash=0),reason)
        conn.commit();return True
    except Exception:conn.rollback();raise
    finally:conn.close()
