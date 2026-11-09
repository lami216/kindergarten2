"""School reminder cutoffs without database writes or financial rescheduling."""
from datetime import date, datetime

import pytest

from student_followup import reminder_date


@pytest.mark.parametrize('day,expected', [
    (1, 10), (8, 10), (9, 10), (10, 10), (11, 10), (12, 10),
    (16, 10), (17, 10), (18, 18), (20, 20), (30, 30), (31, 31),
])
def test_default_month_cutoffs(day, expected):
    due = date(2026, 10, day)
    assert reminder_date(due) == date(2026, 10, expected)
    assert due == date(2026, 10, day)


@pytest.mark.parametrize('due,chosen,expected', [
    (date(2026, 2, 8), 31, date(2026, 2, 28)),
    (date(2026, 2, 28), 29, date(2026, 2, 28)),
    (date(2026, 2, 28), 30, date(2026, 2, 28)),
    (date(2026, 2, 28), 31, date(2026, 2, 28)),
    (date(2028, 2, 28), 29, date(2028, 2, 29)),
    (date(2028, 2, 29), 30, date(2028, 2, 29)),
    (date(2028, 2, 29), 31, date(2028, 2, 29)),
    (date(2026, 4, 30), 31, date(2026, 4, 30)),
    (date(2026, 3, 1), 31, date(2026, 2, 28)),
    (date(2026, 12, 17), 10, date(2026, 12, 10)),
    (date(2027, 1, 18), 10, date(2027, 1, 18)),
    (date(9999, 12, 31), 31, date(9999, 12, 31)),
])
def test_month_and_year_boundaries(due, chosen, expected):
    assert reminder_date(due, reminder_day=chosen) == expected


@pytest.mark.parametrize('due,chosen,expected', [
    (date(2026, 2, 2), 28, date(2026, 1, 28)),
    (date(2026, 2, 4), 28, date(2026, 1, 28)),
    (date(2026, 2, 5), 28, date(2026, 2, 28)),
    (date(2026, 2, 7), 31, date(2026, 1, 31)),
    (date(2028, 3, 7), 31, date(2028, 2, 29)),
    (date(2028, 3, 8), 31, date(2028, 3, 31)),
    (date(2027, 1, 1), 31, date(2026, 12, 31)),
    (date(1, 1, 1), 31, date(1, 1, 31)),
])
def test_previous_batch_can_reach_into_next_month(due, chosen, expected):
    assert reminder_date(due, reminder_day=chosen) == expected


@pytest.mark.parametrize('day,expected', [(8, 10), (10, 10), (11, 11)])
def test_early_reminders_can_be_disabled(day, expected):
    assert reminder_date(date(2026, 11, day), early_days=0) == date(2026, 11, expected)


def test_configured_reminder_day_and_inclusive_early_window():
    assert reminder_date(date(2026, 11, 22), reminder_day=15) == date(2026, 11, 15)
    assert reminder_date(date(2026, 11, 23), reminder_day=15) == date(2026, 11, 23)
    assert reminder_date(date(2026, 11, 17), early_days=6) == date(2026, 11, 17)


@pytest.mark.parametrize('value', [0, 32, -1, True, False, 10.0, '10', None])
def test_invalid_reminder_days_are_rejected(value):
    with pytest.raises(ValueError, match='Reminder day'):
        reminder_date(date(2026, 11, 10), reminder_day=value)


@pytest.mark.parametrize('value', [-1, True, 7.0, '7', None])
def test_invalid_early_windows_are_rejected(value):
    with pytest.raises(ValueError, match='Early reminder'):
        reminder_date(date(2026, 11, 10), early_days=value)


@pytest.mark.parametrize('value', ['2026-11-10', None, datetime(2026, 11, 10)])
def test_due_date_is_an_explicit_calendar_date(value):
    with pytest.raises(ValueError, match='calendar due date'):
        reminder_date(value)
