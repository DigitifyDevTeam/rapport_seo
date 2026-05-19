"""Reporting period helpers.

A reporting period is identified by ``YYYY-MM`` (the report month *M*).
Data windows use a fixed day-of-month anchor (default **25**):

- **Current period:** 25/(M-1) → 25/M  (e.g. April report → 25 mars – 25 avril)
- **Previous period:** 25/(M-2) → 25/(M-1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

REPORT_CYCLE_DAY = 25

_MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, (index % 12) + 1


def cycle_end_date(year: int, month: int, *, anchor_day: int = REPORT_CYCLE_DAY) -> date:
    """Last day of the reporting window for calendar month ``YYYY-MM``."""
    return date(year, month, anchor_day)


def cycle_start_date(year: int, month: int, *, anchor_day: int = REPORT_CYCLE_DAY) -> date:
    """First day of the reporting window (25th of the month before *M*)."""
    prev_year, prev_month = _shift_month(year, month, -1)
    return date(prev_year, prev_month, anchor_day)


def format_date_fr(value: date) -> str:
    """e.g. ``25 avril 2026``."""
    return f"{value.day} {_MONTHS_FR[value.month - 1]} {value.year}"


def format_date_range_fr(start: date, end: date) -> str:
    """e.g. ``25 mars 2026 – 25 avril 2026``."""
    return f"{format_date_fr(start)} – {format_date_fr(end)}"


def month_title_fr(year: int, month: int) -> str:
    """e.g. ``avril 2026``."""
    return f"{_MONTHS_FR[month - 1]} {year}"


@dataclass(frozen=True)
class Period:
    """Report month *M* with 25→25 comparison windows."""

    year: int
    month: int

    @classmethod
    def parse(cls, value: str) -> "Period":
        dt = datetime.strptime(value, "%Y-%m")
        return cls(dt.year, dt.month)

    @classmethod
    def previous_complete(cls, today: date | None = None) -> "Period":
        today = today or date.today()
        if today.month == 1:
            return cls(today.year - 1, 12)
        return cls(today.year, today.month - 1)

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def start(self) -> date:
        return cycle_start_date(self.year, self.month)

    @property
    def end(self) -> date:
        return cycle_end_date(self.year, self.month)

    @property
    def previous(self) -> "Period":
        prev_year, prev_month = _shift_month(self.year, self.month, -1)
        return Period(prev_year, prev_month)

    def human_label(self) -> str:
        return month_title_fr(self.year, self.month)

    def human_label_fr(self) -> str:
        return month_title_fr(self.year, self.month)

    def date_range_label_fr(self) -> str:
        return format_date_range_fr(self.start, self.end)
