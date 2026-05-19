"""Build the organic performance slide payload from GA4 summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.periods import Period, month_title_fr


@dataclass(frozen=True)
class OrganicPerformanceSlide:
    """Structured data for the styled organic performance table slide."""

    title: str
    kpis: list[tuple[str, str]]
    current_range: str
    previous_range: str
    rows: list[tuple[str, str, str]]


def _metric_float(summary: dict[str, Any], key: str) -> float | None:
    raw = summary.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _format_count(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}".replace(",", " ")


def _format_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    pct = value * 100.0 if value <= 1.0 else value
    text = f"{pct:.2f}".replace(".", ",")
    return f"{text} %"


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    total = max(int(round(seconds)), 0)
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}".replace(".", ",")


def _engaged_per_user(summary: dict[str, Any]) -> float | None:
    engaged = _metric_float(summary, "engagedSessions")
    users = _metric_float(summary, "totalUsers")
    if engaged is None or users is None or users <= 0:
        return None
    return engaged / users


def _row_values(summary: dict[str, Any]) -> dict[str, str]:
    return {
        "sessions": _format_count(_metric_float(summary, "sessions")),
        "users": _format_count(_metric_float(summary, "totalUsers")),
        "new_users": _format_count(_metric_float(summary, "newUsers")),
        "engaged_sessions": _format_count(_metric_float(summary, "engagedSessions")),
        "avg_engagement_duration": _format_duration(
            _metric_float(summary, "averageSessionDuration")),
        "engaged_per_user": _format_ratio(_engaged_per_user(summary)),
        "engagement_rate": _format_rate(_metric_float(summary, "engagementRate")),
    }


def build_organic_performance_slide(
        current_ga4: dict[str, Any],
        previous_ga4: dict[str, Any],
        period: Period) -> OrganicPerformanceSlide:
    """Compose slide content from GA4 organic channel summaries."""
    cur = current_ga4.get("organic_summary") or {}
    prev = previous_ga4.get("organic_summary") or {}
    cur_vals = _row_values(cur)
    prev_vals = _row_values(prev)

    month = month_title_fr(period.year, period.month)
    title = f"PERFORMANCE ORGANIQUE (Mois de {month})"

    kpis = [
        ("Utilisateurs*", cur_vals["users"]),
        ("Nouveaux utilisateurs*", cur_vals["new_users"]),
        ("Sessions*", cur_vals["sessions"]),
        ("Taux d'engagement*", cur_vals["engagement_rate"]),
    ]

    rows = [
        ("Sessions", cur_vals["sessions"], prev_vals["sessions"]),
        ("Utilisateurs", cur_vals["users"], prev_vals["users"]),
        ("Nouveaux utilisateurs", cur_vals["new_users"], prev_vals["new_users"]),
        ("Sessions avec engagement", cur_vals["engaged_sessions"],
         prev_vals["engaged_sessions"]),
        ("Durée d'engagement moyenne /session",
         cur_vals["avg_engagement_duration"], prev_vals["avg_engagement_duration"]),
        ("Sessions avec engagement /utilisateur",
         cur_vals["engaged_per_user"], prev_vals["engaged_per_user"]),
        ("Taux d'engagement", cur_vals["engagement_rate"],
         prev_vals["engagement_rate"]),
    ]

    return OrganicPerformanceSlide(
        title=title,
        kpis=kpis,
        current_range=period.date_range_label_fr(),
        previous_range=period.previous.date_range_label_fr(),
        rows=rows,
    )
