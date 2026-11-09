"""Calendar scheduling for student fee follow-up, independent of the ledger."""
import calendar
from datetime import date, datetime, timezone


def reminder_date(due_date, reminder_day=10, early_days=7):
    """Schedule within the due date's month without moving its debt due date.

    An expiry on/before the chosen day is followed up on that chosen day.
    Expiries up to ``early_days`` after it are included in the same reminder;
    later expiries are followed up on their own date. The previous month's
    reminder also applies when its early window reaches this due date. Short
    months clamp the chosen day, never carry it into another month.
    """
    if type(due_date) is not date:
        raise ValueError('A calendar due date is required')
    if type(reminder_day) is not int or not 1 <= reminder_day <= 31:
        raise ValueError('Reminder day must be an integer from 1 to 31')
    if type(early_days) is not int or early_days < 0:
        raise ValueError('Early reminder days must be a non-negative integer')
    chosen = date(due_date.year, due_date.month,
                  min(reminder_day, calendar.monthrange(due_date.year, due_date.month)[1]))
    if due_date.year > 1 or due_date.month > 1:
        previous_year = due_date.year - int(due_date.month == 1)
        previous_month = 12 if due_date.month == 1 else due_date.month - 1
        previous = date(previous_year, previous_month,
                        min(reminder_day, calendar.monthrange(previous_year, previous_month)[1]))
        if (due_date - previous).days <= early_days:
            return previous
    # Difference comparison avoids overflowing at the end of date.max's year.
    return chosen if (due_date - chosen).days <= early_days else due_date


def _remaining(row):
    return max(0, int(row['price']) - int(row['paid']) - int(row.get('waived', 0)) - int(row.get('cancelled', 0)))


def _business_date(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    return value


def policy_windows(changes, as_of):
    """Ended policy intervals, reconstructed from append-only setting changes.

    Current policy remains authoritative for new/upcoming reminders. Only
    intervals that really existed by this business day may retain old debt.
    A missing history means no historical override, not a guessed old policy.
    """
    begin = date.min
    windows = []
    for row in changes:
        changed = _business_date(row['changed_on'])
        if changed > as_of:
            continue
        before, after = int(row['before_day']), int(row['after_day'])
        if not 1 <= before <= 31 or not 1 <= after <= 31 or before == after:
            continue
        windows.append(dict(day=before, starts=begin, ends=changed))
        begin = changed
    return windows


def _previous_policies(conn, day):
    # Internal scheduling metadata only: neither actors, reasons nor raw audit
    # rows are returned to payment viewers who cannot view change history.
    with conn.cursor() as c:
        c.execute('''SELECT before_state->>'followup_day' AS before_day,
            after_state->>'followup_day' AS after_day,
            (happened_at AT TIME ZONE 'Africa/Nouakchott')::date AS changed_on
            FROM record_changes WHERE table_name='monthly_tariffs' AND record_key='1'
                AND before_state ? 'followup_day' AND after_state ? 'followup_day'
                AND before_state->'followup_day' IS DISTINCT FROM after_state->'followup_day'
                AND happened_at < ((%s::date+1)::timestamp AT TIME ZONE 'Africa/Nouakchott')
            ORDER BY happened_at,change_id''', (day,))
        return policy_windows(c.fetchall(), day)


def account_item(projection, day, reminder_day, tuition, previous_policies=()):
    """Derive visibility from unpaid obligations; never change their due dates.

    Once an unpaid obligation has reached its reminder date it stays visible,
    including in later months before the batch day. Settled/waived periods do
    not create reminders, and an upcoming balance is never labelled debt.
    """
    import monthly_finance as F
    account = projection['account']
    if account.get('archived_at') or account['start_date'] > day:
        return None
    open_account = account['status'] == 'regular' and not account.get('departure_on')
    cutoff = min(day, account.get('departure_on') or day,
                 account.get('exempt_from') or day if account['status'] == 'exempt' else day)
    monthly_due = []
    future = []
    periods = projection['periods']
    for period in periods:
        remaining = _remaining(period)
        if not remaining:
            continue
        due = period['end'] if account.get('due_at_period_end') else period['start']
        item = dict(due_date=due, start=period['start'], end=period['end'], remaining=remaining)
        if due <= cutoff:
            monthly_due.append(item)
        elif open_account:
            future.append(item)
    # Paid-in-advance accounts may have no stored unpaid period. The next
    # missing period uses the current tariff, just as the official allocator.
    if open_account and not future and int(tuition) > 0:
        existing = {p['no']: p for p in periods}
        index = 0
        while index in existing:
            index += 1
        start, end = F.anniversary(account['start_date'], index), F.anniversary(account['start_date'], index + 1)
        due = end if account.get('due_at_period_end') else start
        if due > day:
            future.append(dict(due_date=due, start=start, end=end, remaining=int(tuition)))
    future.sort(key=lambda p: p['due_date'])
    upcoming = future[0] if future else None
    fees_due = sum(_remaining(fee) for fee in projection['fees'].values())
    due_dates = [p['due_date'] for p in monthly_due]
    if fees_due:
        due_dates.append(account['start_date'])
    reminders = [reminder_date(d, reminder_day) for d in due_dates]
    visible_dates = [d for d in reminders if d <= day]
    # Changing the batch day must not hide an existing unpaid debt that had
    # reached an earlier policy's window. Do not retain upcoming notices this
    # way, or claim visibility before the account existed or that policy began.
    if int(projection['due_now']) > 0:
        existed = max(account['start_date'], _business_date(account.get('created_at')) or date.min)
        for window in previous_policies:
            end = min(day, window['ends'])
            begin = max(existed, window['starts'])
            for due in due_dates:
                appeared = max(reminder_date(due, window['day']), begin)
                # An early notice alone is rescheduled by the new policy. It
                # retains visibility only after it was actual debt while that
                # previous policy was still active.
                if max(appeared, due) <= end:
                    visible_dates.append(appeared)
    if upcoming and reminder_date(upcoming['due_date'], reminder_day) <= day:
        visible_dates.append(reminder_date(upcoming['due_date'], reminder_day))
    else:
        upcoming = None
    if not visible_dates:
        return None
    due_total = int(projection['due_now'])
    return dict(due_total=due_total, due_monthly=sum(p['remaining'] for p in monthly_due),
                due_fees=fees_due, earliest_due=min(due_dates) if due_dates else None,
                overdue_count=len(monthly_due), upcoming=upcoming,
                reminder_on=min(visible_dates), status='due' if due_total else 'upcoming')


def read(conn):
    """Constant-query authenticated follow-up; no per-student connections."""
    import access_control as A
    import monthly_finance as F
    import followup_settings as S
    from urllib.parse import quote
    with conn.cursor() as c:
        A.require(c, 'payments.view', lock=False)
    day = F.today()
    # Same official period materialization as the roster. No reminder-specific
    # debt, allocation, cash entry or accounting date is ever written.
    F._ensure_all_started(day)
    try:
        with conn.cursor() as c:
            c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ')
            A.require(c, 'payments.view', lock=False)
        settings = S.read(conn)
        previous_policies = _previous_policies(conn, day)
        projections = F.projections(conn, day, materialize=False)
        with conn.cursor() as c:
            c.execute('SELECT tuition FROM monthly_tariffs WHERE id=1')
            row = c.fetchone()
            tuition = int(row['tuition']) if row else 0
            c.execute('''SELECT s.student_id,s.full_name,p.father_name,p.mother_name,p.father_mobile,p.mother_mobile,
                d.department_id,d.name AS department,ph.revision,ph.image_data IS NOT NULL AS photo
                FROM students s LEFT JOIN parents p USING(father_id)
                LEFT JOIN student_departments sd USING(student_id)
                LEFT JOIN school_departments d USING(department_id)
                LEFT JOIN student_photos ph USING(student_id)
                WHERE s.archived_at IS NULL ORDER BY s.full_name,s.student_id''')
            people = c.fetchall()
        can_students = A.can('students.view')
        can_pay = A.can('payments.create')
        items = []
        for child in people:
            p = projections.get(child['student_id'])
            if not p:
                continue
            item = account_item(p, day, settings['day'], tuition, previous_policies)
            if not item:
                continue
            ident = child['student_id']
            item.update(id=ident, name=child['full_name'], department_id=child['department_id'],
                        department=child['department'] or '', can_profile=can_students,
                        can_pay=can_pay and p['account']['status']=='regular',
                        father=(child['father_name'] or '') if can_students else '',
                        mother=(child['mother_name'] or '') if can_students else '',
                        father_phone=(child['father_mobile'] or '') if can_students else '',
                        mother_phone=(child['mother_mobile'] or '') if can_students else '',
                        photo=dict(data='/api/photo/'+quote(ident,safe='')+'?v='+str(child['revision']),revision=child['revision']) if can_students and child['photo'] else None)
            items.append(item)
        items.sort(key=lambda row: (row['status']!='due',
            row['earliest_due'] if row['status']=='due' else row['upcoming']['due_date'],
            row['name'],row['id']))
        return dict(today=day, settings=settings, early_days=7, items=items)
    finally:
        conn.rollback()
