"""GA4 « Vue d'ensemble » — KPI strip + single daily line (API, 25/(M-1) → 25/M)."""

from __future__ import annotations

from datetime import date

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from src.periods import format_date_fr

GA4_BLUE = "#1A73E8"
_GA4_TEXT = "#202124"
_GA4_MUTED = "#5F6368"

# Three equal columns (no overlapping labels).
_KPI_COLUMNS: tuple[tuple[float, str], ...] = (
    (0.03, "Utilisateurs actifs"),
    (0.36, "Nouveaux utilisateurs"),
    (0.69, "Durée d'engagement\nmoyenne"),
)


def _fmt_compact(value: float) -> str:
    n = float(value)
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f} M".replace(".0 M", " M").replace(".", ",")
    if n >= 10_000:
        return f"{int(round(n / 1000))} k"
    if n >= 1_000:
        v = n / 1000
        if abs(v - round(v)) < 0.05:
            return f"{int(round(v))} k"
        return f"{v:.1f} k".replace(".0 k", " k").replace(".", ",")
    return f"{int(round(n)):,}".replace(",", "\u202f")


def _fmt_duration(seconds: float) -> str:
    s = max(0, int(round(float(seconds))))
    if s >= 3600:
        h, rem = divmod(s, 3600)
        m = rem // 60
        return f"{h} h {m} min"
    minutes, secs = divmod(s, 60)
    if secs > 0:
        return f"{minutes} min {secs} s"
    return f"{minutes} min"


def _avg_engagement_seconds(overview: dict[str, float]) -> float:
    if "avgEngagementSeconds" in overview:
        return float(overview["avgEngagementSeconds"] or 0)
    au = float(overview.get("activeUsers") or 0)
    total = float(overview.get("userEngagementDuration") or 0)
    if au > 0 and total > 0:
        return total / au
    return float(overview.get("averageSessionDuration") or 0)


def _draw_metric_block(
    ax,
    x: float,
    title: str,
    value_text: str,
    *,
    active: bool = False,
) -> None:
    title_color = GA4_BLUE if active else _GA4_MUTED
    ax.text(
        x, 0.94, title, fontsize=10, color=title_color, ha="left", va="top",
        transform=ax.transAxes, clip_on=False, linespacing=1.2,
    )
    ax.text(
        x, 0.72, value_text, fontsize=22, color=_GA4_TEXT,
        fontweight="bold", ha="left", va="top", transform=ax.transAxes,
        clip_on=False,
    )
    if active:
        ax.plot(
            [x, x + 0.26], [0.60, 0.60], color=GA4_BLUE, linewidth=3,
            transform=ax.transAxes, clip_on=False,
        )


def _clip_daily_to_period(
    daily: pd.DataFrame,
    period_start: date,
    period_end: date,
) -> pd.DataFrame:
    if daily.empty or "activeUsers" not in daily.columns:
        return daily
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    start = pd.Timestamp(period_start)
    end = pd.Timestamp(period_end)
    return frame[(frame["date"] >= start) & (frame["date"] <= end)].sort_values(
        "date",
    )


def draw_vue_ensemble(
    ax,
    current_daily: pd.DataFrame,
    current_overview: dict[str, float],
    *,
    period_start: date,
    period_end: date,
) -> None:
    """GA4 overview card: 3 KPIs + one line (utilisateurs actifs / jour)."""
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    values = (
        _fmt_compact(float(current_overview.get("activeUsers") or 0)),
        _fmt_compact(float(current_overview.get("newUsers") or 0)),
        _fmt_duration(_avg_engagement_seconds(current_overview)),
    )
    for idx, (x, title) in enumerate(_KPI_COLUMNS):
        _draw_metric_block(
            ax, x, title, values[idx], active=(idx == 0),
        )

    range_label = f"{format_date_fr(period_start)} – {format_date_fr(period_end)}"
    ax.text(
        0.03, 0.52, range_label, fontsize=9, color=_GA4_MUTED, ha="left",
        va="top", transform=ax.transAxes,
    )

    ax_chart = ax.inset_axes([0.02, 0.02, 0.96, 0.46])
    ax_chart.set_facecolor("white")

    cur = _clip_daily_to_period(current_daily, period_start, period_end)
    if cur.empty:
        ax_chart.text(
            0.5, 0.5, "Données indisponibles", ha="center", va="center",
            fontsize=12, color=_GA4_MUTED,
        )
        ax_chart.set_axis_off()
        return

    cur["activeUsers"] = pd.to_numeric(cur["activeUsers"], errors="coerce").fillna(0)
    ax_chart.plot(cur["date"], cur["activeUsers"], color=GA4_BLUE, linewidth=2.6, zorder=3)

    ax_chart.yaxis.tick_right()
    ax_chart.tick_params(axis="y", labelsize=9, colors=_GA4_MUTED)
    ax_chart.tick_params(axis="x", labelsize=9, colors=_GA4_MUTED)
    span_days = max((cur["date"].max() - cur["date"].min()).days, 1)
    interval = max(3, span_days // 8)
    ax_chart.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
    ax_chart.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax_chart.set_xlim(cur["date"].min(), cur["date"].max())
    ax_chart.grid(True, axis="y", linewidth=0.5, color="#E8EAED")
    ax_chart.spines["top"].set_visible(False)
    ax_chart.spines["left"].set_visible(False)
    ax_chart.margins(x=0.02)
