"""Helpers for Google Performance URLs (``#mpd=`` / promote/performance)."""

from __future__ import annotations

import calendar
import re


def report_calendar_month_bounds(period_end: str) -> tuple[str, str]:
    """First/last day of the report calendar month (YYYY-MM-DD).

    GMB picker is month-based: ``--month 2026-06`` → juin 2026 only.
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


def rewrite_performance_url_month(url: str, ym: str) -> str:
    """Align ``from`` / ``to`` query params in a saved Performance URL to ``ym``.

    When the URL has no ``from``/``to`` yet (common for ``#mpd=`` Search links),
    inject them so the Performance overlay opens on the report month.
    """
    if not url or not ym or len(ym) < 7:
        return url
    if "#mpd=" not in url and "promote/performance" not in url:
        return url
    out = url
    had_from_to = bool(
        re.search(r"(?:from|to)(?:%3D|=)\d{4}-\d{2}", out, re.I),
    )
    for prefix in ("from%3D", "to%3D", "from=", "to="):
        out = re.sub(
            rf"({re.escape(prefix)})(\d{{4}}-\d{{2}})(?=[^0-9%]|%|$)",
            rf"\g<1>{ym}",
            out,
        )
    if had_from_to:
        return out

    # Inject from/to when missing (picker often fails headless without this).
    encoded = f"from%3D{ym}%26to%3D{ym}"
    plain = f"from={ym}&to={ym}"
    if "#mpd=" in out and "promote/performance" in out:
        if re.search(r"promote/performance\?", out):
            out = re.sub(
                r"(promote/performance\?)",
                rf"\1{encoded}%26",
                out,
                count=1,
            )
        else:
            out = re.sub(
                r"(promote/performance)",
                rf"\1?{encoded}",
                out,
                count=1,
            )
        return out
    if "promote/performance" in out:
        if "?" in out:
            out = re.sub(r"\?", f"?{plain}&", out, count=1)
        else:
            out = f"{out}?{plain}"
    return out


def rewrite_performance_url_period(
    url: str,
    period_start: str,
    period_end: str,
) -> str:
    """Align URL to the report calendar month (month of ``period_end``)."""
    ym = report_year_month(period_end or period_start)
    return rewrite_performance_url_month(url, ym)


def dashboard_url_has_report_month(url: str, period_end: str) -> bool:
    """True when the Performance URL already targets the report calendar month."""
    if not url or not period_end:
        return False
    ym = report_year_month(period_end)
    if not ym:
        return False
    return (
        f"from={ym}" in url
        or f"from%3D{ym}" in url
        or f"to={ym}" in url
        or f"to%3D{ym}" in url
    )


def dashboard_url_has_report_period(
    url: str,
    period_start: str,
    period_end: str,
) -> bool:
    """True when URL targets the report month (month of ``period_end``)."""
    return dashboard_url_has_report_month(url, period_end or period_start)
