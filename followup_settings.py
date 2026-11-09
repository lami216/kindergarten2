"""Audited school-wide reminder day; independent from subscription dates/prices."""
import access_control as A
import db
import record_history as H
import records as R


def migrate(conn):
    """Deployment migration only; never called while reading/saving settings."""
    with conn.cursor() as c:
        c.execute('''ALTER TABLE monthly_tariffs ADD COLUMN IF NOT EXISTS
            followup_day SMALLINT NOT NULL DEFAULT 10 CHECK(followup_day BETWEEN 1 AND 31)''')


def _revision(day):
    return R.revision({'followup_day': day})


def read(conn):
    with conn.cursor() as c:
        profile = A.current(c)
        c.execute('SELECT followup_day FROM monthly_tariffs WHERE id=1')
        row = c.fetchone()
    return {'day': int(row['followup_day']) if row else 10,
            'revision': _revision(int(row['followup_day']) if row else None),
            'editable': bool(profile['is_admin'])}


def _day(value):
    # JSON booleans/floats and partial numeric strings are not calendar days.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('اختر يوم تذكير بين 1 و31.')
    value = str(value).strip()
    if not 1 <= len(value) <= 2 or not value.isdecimal() or not 1 <= int(value) <= 31:
        raise ValueError('اختر يوم تذكير بين 1 و31.')
    return int(value)


def save(conn, data):
    """Write on an independent transaction, like the financial mutation APIs.

    The caller's connection is deliberately not committed or rolled back.
    Authentication is rechecked under a shared user/session lock in the write
    transaction, so stale browser grants cannot authorize this global policy.
    """
    day = _day(data.get('day'))
    reason = str(data.get('reason') or '').strip()
    if not reason or len(reason) > 500:
        raise ValueError('اكتب سبب تعديل يوم التذكير.')
    if data.get('confirmed') is not True:
        raise ValueError('أكّد تعديل يوم التذكير.')
    connection = db.new_transaction_connection()
    try:
        with connection.cursor() as c:
            profile = A.require(c, 'fees.edit')
            if not profile['is_admin']:
                raise A.AccessDenied('إعداد يوم التذكير متاح للمدير فقط.')
            c.execute('SELECT followup_day FROM monthly_tariffs WHERE id=1 FOR UPDATE')
            row = c.fetchone()
            if not row:
                raise ValueError('اضبط الرسوم أولًا قبل تعديل يوم التذكير.')
            if data.get('revision') != _revision(int(row['followup_day'])):
                raise ValueError('تغيّر يوم التذكير؛ حدّث الصفحة ثم أعد المحاولة.')
            if day != int(row['followup_day']):
                H.context(c, profile['username'], reason)
                # Do not touch fee prices, historical periods or tariff metadata.
                c.execute('UPDATE monthly_tariffs SET followup_day=%s WHERE id=1', (day,))
        connection.commit()
        return {'day': day, 'revision': _revision(day), 'editable': True}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
