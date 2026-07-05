"""
Jalali (Shamsi) calendar helpers.

The whole platform reports in the Persian calendar — "this month" means the
current Jalali month (Farvardin, Ordibehesht, ...), and every month-over-month
delta compares Jalali months, not Gregorian ones. This module is the single
place that converts a Gregorian date/datetime to its Jalali period so the
dashboard aggregations never re-implement it.
"""

from datetime import date, datetime, timezone

import jdatetime

MONTHS_EN = [
    "Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
    "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand",
]


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    return value


def jalali_period(value) -> str | None:
    """Gregorian date/datetime -> 'YYYY-MM' in the Jalali calendar (e.g.
    '1403-02'). None passes through."""
    d = _to_date(value)
    if d is None:
        return None
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year:04d}-{j.month:02d}"


def jalali_day(value) -> int | None:
    d = _to_date(value)
    if d is None:
        return None
    return jdatetime.date.fromgregorian(date=d).day


def period_label(period: str) -> str:
    """'1403-02' -> 'Ordibehesht 1403'."""
    y, m = period.split("-")
    return f"{MONTHS_EN[int(m) - 1]} {y}"


def current_period() -> str:
    j = jdatetime.date.today()
    return f"{j.year:04d}-{j.month:02d}"


def previous_period(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}"


def days_in_period(period: str) -> int:
    y, m = (int(x) for x in period.split("-"))
    # Jalali month lengths: months 1-6 have 31 days, 7-11 have 30, 12 has 29
    # (30 in a leap year).
    if m <= 6:
        return 31
    if m <= 11:
        return 30
    return 30 if jdatetime.date(y, 1, 1).isleap() else 29
