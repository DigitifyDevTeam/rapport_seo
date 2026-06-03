"""GA4-style « Utilisateurs actifs par Pays » — clean table (API data)."""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass

import pandas as pd
from matplotlib.patches import Rectangle

GA4_BLUE = "#1A73E8"

logger = logging.getLogger(__name__)

_GA4_TEXT = "#202124"
_GA4_HEADER = "#5F6368"
_GA4_ROW_LINE = "#E8EAED"
_GA4_ROW_ALT = "#F8F9FA"

_COUNTRY_PALETTE = (
    "#1A73E8",
    "#E8710A",
    "#34A853",
    "#9334E6",
    "#F9AB00",
    "#E52592",
    "#12B5CB",
    "#D50000",
)

_TABLE_TOP_N = 8
_ROW_STEP = 0.078
_HEADER_Y = 0.94
_FIRST_ROW_Y = 0.84

_GA4_TO_NE_ADMIN: dict[str, str] = {
    "United States": "United States of America",
    "United Kingdom": "United Kingdom",
    "Czechia": "Czech Republic",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Congo - Brazzaville": "Republic of the Congo",
    "Congo - Kinshasa": "Dem. Rep. Congo",
}

_FRANCE_OVERSEAS_GA4 = frozenset({
    "réunion", "reunion", "guadeloupe", "martinique", "french polynesia",
    "french guiana", "mayotte", "new caledonia", "st. pierre & miquelon",
})


@dataclass(frozen=True)
class CountryRank:
    ga4_label: str
    ne_admin: str
    active_users: float
    color: str


def _normalize_country_label(country: str) -> str:
    text = unicodedata.normalize("NFKD", str(country).strip())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _ne_admin_for_ga4(country: str) -> str:
    return _GA4_TO_NE_ADMIN.get(country, country)


def _format_ga4_users(value: float) -> str:
    n = int(round(float(value)))
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M".replace(".0 M", " M")
    if n >= 10_000:
        return f"{n // 1000} k"
    if n >= 1_000:
        whole = n / 1000
        if abs(whole - round(whole)) < 0.05:
            return f"{int(round(whole))} k"
        return f"{whole:.1f} k".replace(".0 k", " k")
    return f"{n:,}".replace(",", "\u202f")


def _prepare_country_ranks(
    countries_df: pd.DataFrame,
    *,
    top_n: int = _TABLE_TOP_N,
) -> list[CountryRank]:
    lookup: dict[str, float] = {}
    label_by_admin: dict[str, str] = {}

    frame = countries_df.copy()
    frame["activeUsers"] = pd.to_numeric(frame["activeUsers"], errors="coerce").fillna(0)

    for row in frame.itertuples(index=False):
        country = str(row.country).strip()
        users = float(row.activeUsers)
        if not country or country == "(not set)" or users <= 0:
            continue
        norm = _normalize_country_label(country)
        if norm in _FRANCE_OVERSEAS_GA4:
            admin = "France"
            display = "France"
        else:
            admin = _ne_admin_for_ga4(country)
            display = country
        lookup[admin] = lookup.get(admin, 0.0) + users
        if admin not in label_by_admin:
            label_by_admin[admin] = display
    if "France" in lookup:
        label_by_admin["France"] = "France"

    ranked = sorted(lookup.items(), key=lambda item: item[1], reverse=True)[:top_n]
    return [
        CountryRank(
            ga4_label=label_by_admin.get(admin, admin),
            ne_admin=admin,
            active_users=users,
            color=_COUNTRY_PALETTE[idx % len(_COUNTRY_PALETTE)],
        )
        for idx, (admin, users) in enumerate(ranked)
    ]


def _draw_country_table(ax, ranks: list[CountryRank]) -> None:
    """Pays | Utilisateurs actifs — spaced rows, no progress bars."""
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    if not ranks:
        ax.text(0.5, 0.5, "Pays indisponibles", ha="center", va="center",
                fontsize=14, color=_GA4_TEXT, transform=ax.transAxes)
        return

    ax.text(0.04, _HEADER_Y, "PAYS", fontsize=11, color=_GA4_HEADER,
            fontweight="bold", va="top", transform=ax.transAxes)
    ax.text(0.96, _HEADER_Y, "UTILISATEURS ACTIFS", fontsize=11,
            color=_GA4_HEADER, fontweight="bold", ha="right", va="top",
            transform=ax.transAxes)

    ax.plot([0.04, 0.96], [_HEADER_Y - 0.06, _HEADER_Y - 0.06],
            color=_GA4_ROW_LINE, linewidth=1.0, transform=ax.transAxes, clip_on=False)

    row_h = _ROW_STEP * 0.72
    for rank, entry in enumerate(ranks):
        y_center = _FIRST_ROW_Y - rank * _ROW_STEP

        if rank % 2 == 0:
            ax.add_patch(
                Rectangle(
                    (0.03, y_center - row_h / 2), 0.94, row_h,
                    transform=ax.transAxes,
                    facecolor=_GA4_ROW_ALT,
                    edgecolor="none",
                    zorder=0,
                ),
            )

        ax.add_patch(
            Rectangle(
                (0.04, y_center - 0.012), 0.028, 0.024,
                transform=ax.transAxes,
                facecolor=entry.color,
                edgecolor="none",
                clip_on=False,
                zorder=2,
            ),
        )
        ax.text(
            0.10, y_center, entry.ga4_label, fontsize=12, color=_GA4_TEXT,
            va="center", fontweight="bold" if rank == 0 else "normal",
            transform=ax.transAxes, zorder=3,
        )
        ax.text(
            0.96, y_center, _format_ga4_users(entry.active_users),
            fontsize=12, color=_GA4_TEXT, ha="right", va="center",
            fontweight="bold" if rank == 0 else "normal",
            transform=ax.transAxes, zorder=3,
        )


def draw_utilisateurs_actifs_par_pays(ax, countries_df: pd.DataFrame) -> None:
    """Utilisateurs actifs par Pays — readable table (GA4 Data API)."""
    ax.set_title(
        "Utilisateurs actifs par Pays",
        fontsize=15,
        fontweight="bold",
        color=_GA4_TEXT,
        loc="left",
        pad=14,
    )
    if countries_df.empty or "country" not in countries_df.columns:
        ax.text(0.5, 0.45, "Pays indisponibles", ha="center", va="center",
                fontsize=14, color=_GA4_TEXT, transform=ax.transAxes)
        ax.set_axis_off()
        return

    ranks = _prepare_country_ranks(countries_df)
    _draw_country_table(ax, ranks)
