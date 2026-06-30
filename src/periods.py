"""Reporting period helpers.

A reporting period is identified by ``YYYY-MM`` (the report month *M*).
Data windows always use anchor day **25** (not configurable):

- **Current period:** 25/(M-1) → 25/M  (e.g. May report → 25 avril – 25 mai)
- **Previous period:** 25/(M-2) → 25/(M-1)

Use ``SEO_REPORT_SCHEDULE_DAY`` in ``.env`` only for when the VPS cron runs.
``REPORT_CYCLE_DAY`` is legacy alias for the schedule day and does **not** change
the 25→25 analysis window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime


# Fixed business rule: every report month M covers 25/(M-1) → 25/M.
REPORTING_ANCHOR_DAY = 25


def report_cycle_day() -> int:
    """Day-of-month anchor for 25→25 reporting windows (always 25)."""
    return REPORTING_ANCHOR_DAY


def schedule_day_of_month() -> int:
    """Calendar day when the VPS/cron job should fire (default: same as cycle day)."""
    raw = (os.environ.get("SEO_REPORT_SCHEDULE_DAY") or "").strip()
    if raw:
        try:
            return max(1, min(28, int(raw)))
        except ValueError:
            pass
    return report_cycle_day()

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


def cycle_start_date(year: int, month: int,
                       *, anchor_day: int | None = None) -> date:
    """First day of the reporting window (anchor day of month *M-1*)."""
    anchor = report_cycle_day() if anchor_day is None else anchor_day
    prev_year, prev_month = _shift_month(year, month, -1)
    return date(prev_year, prev_month, anchor)


def cycle_end_date(year: int, month: int,
                     *, anchor_day: int | None = None) -> date:
    """Last day of the reporting window (anchor day of report month *M*)."""
    anchor = report_cycle_day() if anchor_day is None else anchor_day
    return date(year, month, anchor)


def format_date_fr(value: date) -> str:
    """e.g. ``25 avril 2026``."""
    return f"{value.day} {_MONTHS_FR[value.month - 1]} {value.year}"


def format_date_range_fr(start: date, end: date) -> str:
    """e.g. ``25 mars 2026 – 25 avril 2026``."""
    return f"{format_date_fr(start)} – {format_date_fr(end)}"


def month_title_fr(year: int, month: int) -> str:
    """e.g. ``avril 2026``."""
    return f"{_MONTHS_FR[month - 1]} {year}"


def month_of_label_fr(year: int, month: int) -> str:
    """e.g. ``Mois de mai 2026`` (slide subtitles)."""
    return f"Mois de {month_title_fr(year, month)}"


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

    @classmethod
    def for_scheduled_run(cls, today: date | None = None) -> "Period":
        """Report month used when the monthly job runs on the schedule day.

        On or after ``SEO_REPORT_SCHEDULE_DAY`` (or legacy ``REPORT_CYCLE_DAY``),
        the job reports on the **current** calendar month (*M*).
        Before that day, it uses the previous calendar month.
        """
        today = today or date.today()
        trigger = schedule_day_of_month()
        if today.day >= trigger:
            return cls(today.year, today.month)
        return cls.previous_complete(today)

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
