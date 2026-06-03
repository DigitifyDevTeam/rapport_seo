"""Render the chart images embedded into the report.

Charts are stored as PNG files in ``<output_dir>/charts/<name>.png``. The
report builder reuses these paths to populate the picture placeholders in
the PowerPoint template.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

PRIMARY = "#0F172A"
ACCENT = "#14B8A6"
GA4_BLUE = "#1A73E8"
WARN = "#E53935"
GRID = "#E0E5EC"
LEGEND_LOC = "upper left"

plt.rcParams.update({
    "axes.edgecolor": GRID,
    "axes.labelcolor": "#1A1F36",
    "axes.titlecolor": PRIMARY,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
    "grid.color": GRID,
    "xtick.color": "#555B6E",
    "ytick.color": "#555B6E",
})


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# Larger composite for readable KPIs + country table on the slide.
_GA4_OVERVIEW_FIGSIZE = (12.5, 7.0)
_GA4_OVERVIEW_DPI = 160


def _save(fig, output: Path, *, pad: float = 0.06) -> Path:
    fig.savefig(
        output,
        dpi=_GA4_OVERVIEW_DPI,
        facecolor="white",
        bbox_inches="tight",
        pad_inches=pad,
    )
    plt.close(fig)
    return output


def _format_date_axis(
    ax,
    dates: pd.Series,
    *,
    max_ticks: int = 7,
    rotation: int = 0,
    xlim_start: date | None = None,
    xlim_end: date | None = None,
) -> None:
    """Readable daily ticks without overlap (25→25 reporting windows)."""
    if dates.empty and xlim_start is None:
        return
    series = pd.to_datetime(dates).dropna()
    if series.empty and xlim_start is None:
        return
    start = pd.Timestamp(xlim_start) if xlim_start else series.min()
    end = pd.Timestamp(xlim_end) if xlim_end else series.max()
    span_days = max((end - start).days, 1)
    interval = max(1, (span_days + max_ticks - 1) // max_ticks)
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m"))
    ax.tick_params(axis="x", labelsize=7, rotation=rotation)
    if rotation:
        for label in ax.get_xticklabels():
            label.set_ha("right")


def _placeholder(output: Path, message: str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14,
            color="#555B6E")
    ax.set_axis_off()
    return _save(fig, output)


def ga4_traffic(df: pd.DataFrame, output_dir: Path) -> Path:
    output = _ensure_dir(output_dir) / "ga4_traffic.png"
    fig = plt.figure(figsize=_GA4_OVERVIEW_FIGSIZE)
    gs = fig.add_gridspec(
        2, 2, height_ratios=[1.2, 1.0],
        hspace=0.55, wspace=0.42,
        left=0.06, right=0.99, top=0.96, bottom=0.07,
    )
    ax_visits = fig.add_subplot(gs[0, 0])
    ax_country = fig.add_subplot(gs[0, 1])
    ax_channels = fig.add_subplot(gs[1, :])
    _draw_visits(ax_visits, df)
    _draw_country_placeholder(ax_country)
    _draw_channel_placeholder(ax_channels)
    return _save(fig, output)


def ga4_traffic_overview(
    active_users_daily: pd.DataFrame,
    countries_df: pd.DataFrame,
    channel_daily_df: pd.DataFrame,
    output_dir: Path,
    *,
    current_overview: dict[str, float] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    visits_image: Path | str | None = None,
    country_image: Path | str | None = None,
) -> Path:
    """Build the GA4 traffic slide image.

    Top row: « Vue d'ensemble » (25/(M-1)→25/M, one line) and « Utilisateurs actifs
    par Pays » (country table from GA4 Data API).
    Bottom: sessions by channel.
    """
    output = _ensure_dir(output_dir) / "ga4_traffic.png"
    visits = _resolve_existing_path(visits_image)
    country = _resolve_existing_path(country_image)

    fig = plt.figure(figsize=_GA4_OVERVIEW_FIGSIZE)
    gs = fig.add_gridspec(
        2, 2, height_ratios=[1.2, 1.0],
        hspace=0.55, wspace=0.42,
        left=0.06, right=0.99, top=0.96, bottom=0.07,
    )
    ax_channels = fig.add_subplot(gs[1, :])
    ax_visits = fig.add_subplot(gs[0, 0])
    ax_country = fig.add_subplot(gs[0, 1])

    if visits is not None:
        _draw_ga4_screenshot(ax_visits, visits)
    else:
        if period_start is None or period_end is None:
            raise ValueError("period_start and period_end required for Vue d'ensemble")
        _draw_vue_ensemble(
            ax_visits,
            active_users_daily,
            current_overview or {},
            period_start=period_start,
            period_end=period_end,
        )

    if country is not None:
        _draw_ga4_screenshot(ax_country, country)
    else:
        _draw_identifiant_pays(ax_country, countries_df)

    _draw_channels(
        ax_channels,
        channel_daily_df,
        period_start=period_start,
        period_end=period_end,
    )
    return _save(fig, output)


def ga4_pages_screens(pages_daily_df: pd.DataFrame, output_dir: Path) -> Path:
    """Engagement > Pages et écrans — vues quotidiennes (comme dans GA4)."""
    output = _ensure_dir(output_dir) / "ga4_pages_screens.png"
    if pages_daily_df.empty or "views" not in pages_daily_df.columns:
        return _placeholder(output, "Données Pages et écrans GA4 indisponibles")
    plot_df = pages_daily_df.sort_values("date").copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    fig, ax = plt.subplots(figsize=_GA4_OVERVIEW_FIGSIZE)
    ax.plot(plot_df["date"], plot_df["views"], color=PRIMARY, linewidth=2.2,
            label="Vues")
    ax.set_title("Pages et écrans — Vues sur la période", fontsize=13, pad=8)
    ax.set_ylabel("Vues")
    _format_date_axis(ax, plot_df["date"], max_ticks=8, rotation=35)
    ax.grid(True, axis="y", linewidth=0.6)
    ax.legend(frameon=False, loc=LEGEND_LOC)
    ax.margins(x=0.02)
    return _save(fig, output)


def ga4_conversions(df: pd.DataFrame, output_dir: Path) -> Path:
    output = _ensure_dir(output_dir) / "ga4_conversions.png"
    if df.empty:
        return _placeholder(output, "Données de conversions GA4 indisponibles")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(df["date"], df["conversions"], color=ACCENT, width=0.8)
    ax.set_title("Conversions quotidiennes")
    ax.set_ylabel("Conversions")
    ax.grid(True, axis="y", linewidth=0.6)
    fig.autofmt_xdate()
    return _save(fig, output)


def gsc_clicks_impressions(df: pd.DataFrame, output_dir: Path) -> Path:
    output = _ensure_dir(output_dir) / "gsc_clicks_impressions.png"
    if df.empty:
        return _placeholder(output, "Données de performance GSC indisponibles")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["date"], df["clicks"], color=PRIMARY, linewidth=2.2,
            label="Clics")
    ax2 = ax.twinx()
    ax2.plot(df["date"], df["impressions"], color=ACCENT, linewidth=2.2,
             linestyle="--", label="Impressions")
    ax.set_title("Clics et impressions (Search)")
    ax.set_ylabel("Clics", color=PRIMARY)
    ax2.set_ylabel("Impressions", color=ACCENT)
    ax2.spines["top"].set_visible(False)
    ax.grid(True, axis="y", linewidth=0.6)
    fig.autofmt_xdate()
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, loc=LEGEND_LOC)
    return _save(fig, output)

def gmb_actions(df: pd.DataFrame, output_dir: Path) -> Path:
    output = _ensure_dir(output_dir) / "gmb_actions.png"
    if df.empty:
        return _placeholder(output, "Données Google Business Profile indisponibles")
    fig, ax = plt.subplots(figsize=(10, 5))
    metrics = [c for c in ("calls", "directions", "website_clicks")
                if c in df.columns]
    if not metrics:
        return _placeholder(output, "Métriques GBP indisponibles")
    bottom = [0] * len(df)
    colors = [PRIMARY, ACCENT, "#43A047"]
    for idx, metric in enumerate(metrics):
        ax.bar(df["date"], df[metric], bottom=bottom,
               label=metric.replace("_", " ").title(),
               color=colors[idx % len(colors)])
        bottom = [b + v for b, v in zip(bottom, df[metric].fillna(0))]
    ax.set_title("Actions clients sur Google Business Profile")
    ax.set_ylabel("Actions")
    ax.grid(True, axis="y", linewidth=0.6)
    ax.legend(frameon=False, loc=LEGEND_LOC)
    fig.autofmt_xdate()
    return _save(fig, output)


def _resolve_existing_path(path: Path | str | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    return candidate if candidate.is_file() else None


def _draw_ga4_screenshot(ax, path: Path) -> None:
    """Embed a GA4 UI card screenshot (titles are already in the image)."""
    import matplotlib.image as mpimg

    ax.imshow(mpimg.imread(path))
    ax.set_axis_off()


def _draw_vue_ensemble(
    ax,
    current_daily: pd.DataFrame,
    current_overview: dict[str, float],
    *,
    period_start: date,
    period_end: date,
) -> None:
    from src.charts.ga4_vue_ensemble import draw_vue_ensemble

    draw_vue_ensemble(
        ax,
        current_daily,
        current_overview,
        period_start=period_start,
        period_end=period_end,
    )


def _draw_visites_mensuelles(ax, df: pd.DataFrame) -> None:
    """GA4 home card: active users over time (metric ``activeUsers``, dim ``date``)."""
    ax.set_title("Visites mensuelles", fontsize=12, fontweight="bold", pad=8)
    if df.empty or "activeUsers" not in df.columns:
        ax.text(0.5, 0.5, "Données indisponibles", ha="center", va="center",
                transform=ax.transAxes, color="#555B6E")
        ax.set_axis_off()
        return
    plot_df = df.sort_values("date").copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    ax.plot(
        plot_df["date"], plot_df["activeUsers"],
        color=GA4_BLUE, linewidth=2.2, label="Utilisateurs actifs",
    )
    ax.set_ylabel("Utilisateurs actifs", fontsize=9)
    _format_date_axis(ax, plot_df["date"], max_ticks=6, rotation=35)
    ax.grid(True, axis="y", linewidth=0.6)
    ax.legend(frameon=False, fontsize=8, loc=LEGEND_LOC)
    ax.margins(x=0.02)


def _draw_identifiant_pays(ax, countries_df: pd.DataFrame) -> None:
    """GA4 home card: active users by country (map + Pays / Utilisateurs table)."""
    from src.charts.ga4_country_widget import draw_utilisateurs_actifs_par_pays

    if countries_df.empty or "country" not in countries_df.columns:
        _draw_country_placeholder(ax)
        return
    draw_utilisateurs_actifs_par_pays(ax, countries_df)


def _draw_visits(ax, df: pd.DataFrame) -> None:
    """Legacy helper — maps organic daily to active-users style when needed."""
    if "activeUsers" in df.columns:
        _draw_visites_mensuelles(ax, df)
        return
    if df.empty or "sessions" not in df.columns:
        _draw_visites_mensuelles(ax, pd.DataFrame())
        return
    mapped = df.sort_values("date").copy()
    mapped["date"] = pd.to_datetime(mapped["date"])
    mapped["activeUsers"] = pd.to_numeric(
        mapped.get("users", mapped["sessions"]), errors="coerce",
    ).fillna(0)
    _draw_visites_mensuelles(ax, mapped[["date", "activeUsers"]])


def _draw_country(ax, countries_df: pd.DataFrame) -> None:
    _draw_identifiant_pays(ax, countries_df)


def _draw_channels(
    ax,
    channel_daily_df: pd.DataFrame,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> None:
    ax.set_title("Acquisition de trafic: Groupe de canaux", fontsize=11, pad=6)
    required = {"date", "channel", "sessions"}
    if channel_daily_df.empty or not required.issubset(channel_daily_df.columns):
        _draw_channel_placeholder(ax)
        return
    totals = (channel_daily_df.groupby("channel", as_index=False)["sessions"]
              .sum().sort_values("sessions", ascending=False))
    top_channels = totals.head(5)["channel"].tolist()
    filtered = channel_daily_df[channel_daily_df["channel"].isin(top_channels)].copy()
    filtered["date"] = pd.to_datetime(filtered["date"])
    if period_start is not None and period_end is not None:
        start = pd.Timestamp(period_start)
        end = pd.Timestamp(period_end)
        filtered = filtered[(filtered["date"] >= start) & (filtered["date"] <= end)]
    for channel in top_channels:
        series = filtered[filtered["channel"] == channel].sort_values("date")
        ax.plot(series["date"], series["sessions"], linewidth=1.8, label=channel)
    _format_date_axis(
        ax,
        filtered["date"],
        max_ticks=8,
        rotation=0,
        xlim_start=period_start,
        xlim_end=period_end,
    )
    ax.grid(True, axis="y", linewidth=0.6)
    ax.legend(frameon=False, fontsize=7, ncol=3, loc=LEGEND_LOC)
    ax.margins(x=0.02)


def _draw_country_placeholder(ax) -> None:
    ax.text(0.5, 0.5, "Pays indisponibles", ha="center", va="center",
            transform=ax.transAxes, color="#555B6E")
    ax.set_axis_off()


def _draw_channel_placeholder(ax) -> None:
    ax.text(0.5, 0.5, "Canaux indisponibles", ha="center", va="center",
            transform=ax.transAxes, color="#555B6E")
    ax.set_axis_off()
