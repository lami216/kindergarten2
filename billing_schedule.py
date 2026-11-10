"""Durable tuition due policy; service periods and cash dates stay independent.

An October subscription period is payable on the chosen day of November,
regardless of the anniversary day that ends that period.  Existing matured
debts and reports before adoption retain the legacy anniversary policy.
"""
import calendar
import re
from datetime import date


def period_due_date(account, start, end, as_of):
    """Resolve one deadline using persisted account policy, never UI settings."""
    legacy = end if account.get('due_at_period_end') else start
    effective = account.get('calendar_due_from')
    chosen = account.get('calendar_due_day')
    if chosen is None or effective is not None and (as_of < effective or legacy <= effective):
        return legacy
    year, month = start.year + int(start.month == 12), start.month % 12 + 1
    scheduled = date(year, month, min(int(chosen), calendar.monthrange(year, month)[1]))
    return max(effective, scheduled) if effective is not None else scheduled


def period_due(account, period, as_of):
    """Accept both projection (start/end) and database (starts/ends) rows."""
    return period_due_date(account, period.get('start', period.get('starts')),
                           period.get('end', period.get('ends')), as_of)


def due_sql(account='a', period='p', as_of='%(day)s'):
    """SQL equivalent of period_due for constant-query aggregate/debt reads.

    Only trusted identifier aliases and an internal SQL date expression belong
    here. User input continues to be supplied through bound query parameters.
    """
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', alias) for alias in (account, period)):
        raise ValueError('Invalid billing table alias')
    legacy = f'(CASE WHEN {account}.due_at_period_end THEN {period}.ends ELSE {period}.starts END)'
    following = f"(date_trunc('month',{period}.starts)::date+interval '1 month')::date"
    final_day = f"extract(day FROM date_trunc('month',{period}.starts)+interval '2 months'-interval '1 day')::int"
    scheduled = f'({following}+(LEAST({account}.calendar_due_day::int,{final_day})-1))'
    return f'''(CASE WHEN {account}.calendar_due_day IS NULL
        OR ({account}.calendar_due_from IS NOT NULL AND
            (({as_of})::date<{account}.calendar_due_from OR {legacy}<={account}.calendar_due_from)) THEN {legacy}
        ELSE GREATEST({account}.calendar_due_from,{scheduled}) END)'''


def migrate(conn):
    """Deployment-only additive adoption, under the schema migration lock.

    Run after record-history triggers exist. The metadata and per-account
    ledger markers are committed with the schema version, never on page reads.
    Closed/exempt accounts retain their former terms, including a closure on
    this same business day. Replays preserve any already configured policy.
    """
    import monthly_finance as F
    import record_history as H
    with conn.cursor() as c:
        c.execute('''ALTER TABLE monthly_accounts
            ADD COLUMN IF NOT EXISTS calendar_due_day SMALLINT,
            ADD COLUMN IF NOT EXISTS calendar_due_from DATE;
            DO $$ BEGIN
                IF NOT EXISTS(SELECT 1 FROM pg_constraint
                    WHERE conrelid='monthly_accounts'::regclass AND conname='monthly_calendar_due_policy') THEN
                    ALTER TABLE monthly_accounts ADD CONSTRAINT monthly_calendar_due_policy CHECK(
                        (calendar_due_from IS NULL OR calendar_due_day IS NOT NULL)
                        AND (calendar_due_day IS NULL OR calendar_due_day BETWEEN 1 AND 31));
                END IF;
            END $$;''')
        H.context(c, 'النظام', 'ترقية 21: اعتماد موعد استحقاق الشهرية')
        c.execute('''UPDATE monthly_accounts SET calendar_due_day=10,
                calendar_due_from=(CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nouakchott')::date
            WHERE calendar_due_day IS NULL
                AND status='regular' AND departure_on IS NULL AND archived_at IS NULL
                AND EXISTS(SELECT 1 FROM students s WHERE s.student_id=monthly_accounts.student_id
                    AND s.archived_at IS NULL)
            RETURNING student_id,calendar_due_day,calendar_due_from''')
        for row in c.fetchall():
            F._audit(c, row['student_id'], None, 'calendar_due_policy_adopted', 'النظام',
                     {'calendar_due_day': None, 'calendar_due_from': None},
                     {'calendar_due_day': int(row['calendar_due_day']),
                      'calendar_due_from': str(row['calendar_due_from']), 'cash_unchanged': True},
                     'ترقية 21: تثبيت الديون السابقة واعتماد استحقاق الشهرية')
