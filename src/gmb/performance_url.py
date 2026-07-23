"""Helpers for Google Performance URLs (``#mpd=`` / promote/performance)."""

from __future__ import annotations

import calendar
import re


def report_calendar_month_bounds(period_end: str) -> tuple[str, str]:
    """First/last day of the report calendar month (YYYY-MM-DD).

    Kept for compatibility; prefer the 25→25 cycle dates from ``Period``.
    """
    if not period_end or len(period_end) < 7:
        return period_end, period_end
    try:
        year = int(period_end[:4])
        month = int(period_end[5:7])
    except ValueError:
        return period_end, period_end
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def report_year_month(period_end: str) -> str:
    """``YYYY-MM`` label for the report calendar month."""
    _start, cal_end = report_calendar_month_bounds(period_end)
    return (cal_end or period_end or "")[:7]


def _ym(iso_date: str) -> str:
    return (iso_date or "")[:7]


def rewrite_performance_url_month(url: str, ym: str) -> str:
    """Align both ``from`` and ``to`` query params to a single ``ym`` (legacy)."""
    if not url or not ym or len(ym) < 7:
        return url
    return rewrite_performance_url_period(url, f"{ym}-01", f"{ym}-28")


def rewrite_performance_url_period(
    url: str,
    period_start: str,
    period_end: str,
) -> str:
    """Set Performance URL ``from`` / ``to`` to the 25→25 cycle months.

    GBP URLs use month granularity (``YYYY-MM``). For cycle
    ``25/(M-1) → 25/M`` we set ``from=YYYY-(M-1)`` and ``to=YYYY-M``.
    """
    if not url or not period_start:
        return url
    if "#mpd=" not in url and "promote/performance" not in url:
        return url
    start_ym = _ym(period_start)
    end_ym = _ym(period_end) or start_ym
    if len(start_ym) < 7:
        return url
    out = url
    for prefix in ("from%3D", "from="):
        out = re.sub(
            rf"({re.escape(prefix)})(\d{{4}}-\d{{2}})(?=[^0-9%]|%|$)",
            rf"\g<1>{start_ym}",
            out,
        )
    for prefix in ("to%3D", "to="):
        out = re.sub(
            rf"({re.escape(prefix)})(\d{{4}}-\d{{2}})(?=[^0-9%]|%|$)",
            rf"\g<1>{end_ym}",
            out,
        )
    return out


def dashboard_url_has_report_month(url: str, period_end: str) -> bool:
    """True when the URL ``to`` month matches the report month (legacy check)."""
    if not url or not period_end:
        return False
    ym = report_year_month(period_end)
    if not ym:
        return False
    return (
        f"to={ym}" in url
        or f"to%3D{ym}" in url
        or f"from={ym}" in url
        or f"from%3D{ym}" in url
    )


def dashboard_url_has_report_period(
    url: str,
    period_start: str,
    period_end: str,
) -> bool:
    """True when URL ``from``/``to`` match the 25→25 cycle months."""
    if not url or not period_start:
        return False
    start_ym = _ym(period_start)
    end_ym = _ym(period_end) or start_ym
    if len(start_ym) < 7:
        return False
    has_from = f"from={start_ym}" in url or f"from%3D{start_ym}" in url
    has_to = f"to={end_ym}" in url or f"to%3D{end_ym}" in url
    if start_ym == end_ym:
        return has_from or has_to
    return has_from and has_to
