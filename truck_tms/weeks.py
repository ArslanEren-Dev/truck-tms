"""Statement-week helpers.

A statement week is 7 days starting on a configurable weekday
(``week_start`` setting, Python numbering: 0 = Monday … 6 = Sunday).
A load belongs to the week of its delivery date (or pickup date when there
is no delivery date), unless a week was set on the load manually.
"""

from __future__ import annotations

from datetime import date, timedelta


def to_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def week_start(value: date | str, start_dow: int = 0) -> date:
    d = to_date(value)
    return d - timedelta(days=(d.weekday() - start_dow) % 7)


def week_end(start: date | str) -> date:
    return to_date(start) + timedelta(days=6)


def week_label(start: date | str | None) -> str:
    """'2026-11-16 → 11-22'"""
    if not start:
        return ""
    s = to_date(start)
    e = week_end(s)
    end = e.strftime("%m-%d") if e.year == s.year else e.isoformat()
    return f"{s.isoformat()} → {end}"


def sqlite_week_expr(date_expr: str, start_dow: int) -> str:
    """SQL expression giving the week start of ``date_expr`` (NULL stays NULL)."""
    sqlite_dow = (start_dow + 1) % 7  # SQLite: 0 = Sunday
    return f"date({date_expr}, '-6 days', 'weekday {sqlite_dow}')"
