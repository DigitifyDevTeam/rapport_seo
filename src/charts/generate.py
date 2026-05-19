"""Render the chart images embedded into the report.

Charts are stored as PNG files in ``<output_dir>/charts/<name>.png``. The
report builder reuses these paths to populate the picture placeholders in
the PowerPoint template.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

PRIMARY = "#0F172A"
ACCENT = "#14B8A6"
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


# Matches the GA4 traffic chart placeholder (~8.4" x 5.2" on the slide).
_GA4_OVERVIEW_FIGSIZE = (10.0, 6.0)


def _save(fig, output: Path, *, pad: float = 0.06) -> Path:
    fig.savefig(
        output,
        dpi=150,
        facecolor="white",
        bbox_inches="tight",
        pad_inches=pad,
    )
    plt.close(fig)
    return output


def _format_date_axis(ax, dates: pd.Series, *, max_ticks: int = 7,
                      rotation: int = 0) -> None:
    """Readable daily ticks without overlap (25→25 reporting windows)."""
    if dates.empty:
        return
    series = pd.to_datetime(dates).dropna()
    if series.empty:
        return
    start = series.min()
    end = series.max()
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
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.15],
                          hspace=0.48, wspace=0.32,
                          left=0.07, right=0.98, top=0.94, bottom=0.08)
    ax_visits = fig.add_subplot(gs[0, 0])
    ax_country = fig.add_subplot(gs[0, 1])
    ax_channels = fig.add_subplot(gs[1, :])
    _draw_visits(ax_visits, df)
    _draw_country_placeholder(ax_country)
    _draw_channel_placeholder(ax_channels)
    return _save(fig, output)


def ga4_traffic_overview(organic_df: pd.DataFrame, countries_df: pd.DataFrame,
                         channel_daily_df: pd.DataFrame, output_dir: Path) -> Path:
    output = _ensure_dir(output_dir) / "ga4_traffic.png"
    fig = plt.figure(figsize=_GA4_OVERVIEW_FIGSIZE)
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.15],
                          hspace=0.48, wspace=0.32,
                          left=0.07, right=0.98, top=0.94, bottom=0.08)
    ax_visits = fig.add_subplot(gs[0, 0])
    ax_country = fig.add_subplot(gs[0, 1])
    ax_channels = fig.add_subplot(gs[1, :])

    _draw_visits(ax_visits, organic_df)
    _draw_country(ax_country, countries_df)
    _draw_channels(ax_channels, channel_daily_df)
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


def _draw_visits(ax, df: pd.DataFrame) -> None:
    ax.set_title("Visites mensuelles", fontsize=11, pad=6)
    if df.empty:
        ax.text(0.5, 0.5, "Données indisponibles", ha="center", va="center",
                transform=ax.transAxes, color="#555B6E")
        ax.set_axis_off()
        return
    plot_df = df.sort_values("date").copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    ax.plot(plot_df["date"], plot_df["sessions"], color=PRIMARY,
            label="Sessions", linewidth=2.0)
    ax.plot(plot_df["date"], plot_df["users"], color=ACCENT,
            label="Utilisateurs", linewidth=1.8, linestyle="--")
    _format_date_axis(ax, plot_df["date"], max_ticks=6, rotation=35)
    ax.grid(True, axis="y", linewidth=0.6)
    ax.legend(frameon=False, fontsize=8, loc=LEGEND_LOC)
    ax.margins(x=0.02)


def _draw_country(ax, countries_df: pd.DataFrame) -> None:
    ax.set_title("Identifiant du pays")
    if countries_df.empty or "country" not in countries_df.columns:
        _draw_country_placeholder(ax)
        return
    top = countries_df.head(6).iloc[::-1]
    ax.barh(top["country"], top["activeUsers"], color=ACCENT)
    ax.grid(True, axis="x", linewidth=0.6)
    ax.tick_params(axis="y", labelsize=8)


def _draw_channels(ax, channel_daily_df: pd.DataFrame) -> None:
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
    for channel in top_channels:
        series = filtered[filtered["channel"] == channel].sort_values("date")
        ax.plot(series["date"], series["sessions"], linewidth=1.8, label=channel)
    _format_date_axis(ax, filtered["date"], max_ticks=8, rotation=0)
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
