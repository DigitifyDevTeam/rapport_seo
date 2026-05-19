"""KPI computation and month-over-month comparison."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class KpiValue:
    """A single KPI with its previous month value and delta."""

    label: str
    value: float
    previous: float
    unit: str = ""

    @property
    def delta_abs(self) -> float:
        return self.value - self.previous

    @property
    def delta_pct(self) -> float | None:
        if self.previous == 0:
            return None
        return (self.value - self.previous) / self.previous * 100.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["delta_abs"] = self.delta_abs
        data["delta_pct"] = self.delta_pct
        return data


@dataclass
class KpiBundle:
    """Every KPI displayed on the report cover and overview slide."""

    sessions: KpiValue
    users: KpiValue
    conversions: KpiValue
    clicks: KpiValue
    impressions: KpiValue
    ctr: KpiValue
    avg_position: KpiValue
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": self.sessions.to_dict(),
            "users": self.users.to_dict(),
            "conversions": self.conversions.to_dict(),
            "clicks": self.clicks.to_dict(),
            "impressions": self.impressions.to_dict(),
            "ctr": self.ctr.to_dict(),
            "avg_position": self.avg_position.to_dict(),
            "extras": self.extras,
        }


def _sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _weighted_mean(df: pd.DataFrame, value_col: str,
                    weight_col: str) -> float:
    if df.empty or value_col not in df.columns or weight_col not in df.columns:
        return 0.0
    values = pd.to_numeric(df[value_col], errors="coerce").fillna(0)
    weights = pd.to_numeric(df[weight_col], errors="coerce").fillna(0)
    total = weights.sum()
    if total <= 0:
        return float(values.mean()) if len(values) else 0.0
    return float((values * weights).sum() / total)


def compute_kpis(current: dict[str, dict[str, pd.DataFrame]],
                  previous: dict[str, dict[str, pd.DataFrame]]) -> KpiBundle:
    """Build the canonical KPI bundle for the report."""
    cur_ga4 = current.get("ga4", {}).get("organic_daily", pd.DataFrame())
    prev_ga4 = previous.get("ga4", {}).get("organic_daily", pd.DataFrame())
    cur_gsc = current.get("gsc", {}).get("daily", pd.DataFrame())
    prev_gsc = previous.get("gsc", {}).get("daily", pd.DataFrame())

    sessions = KpiValue("Sessions",
                          _sum(cur_ga4, "sessions"),
                          _sum(prev_ga4, "sessions"))
    users = KpiValue("Users", _sum(cur_ga4, "users"), _sum(prev_ga4, "users"))
    conversions = KpiValue("Conversions",
                              _sum(cur_ga4, "conversions"),
                              _sum(prev_ga4, "conversions"))

    clicks = KpiValue("Clicks", _sum(cur_gsc, "clicks"),
                        _sum(prev_gsc, "clicks"))
    impressions = KpiValue("Impressions", _sum(cur_gsc, "impressions"),
                              _sum(prev_gsc, "impressions"))

    cur_ctr = (clicks.value / impressions.value * 100.0
                if impressions.value else 0.0)
    prev_ctr = (clicks.previous / impressions.previous * 100.0
                 if impressions.previous else 0.0)
    ctr = KpiValue("CTR", cur_ctr, prev_ctr, unit="%")

    avg_position = KpiValue(
        "Avg Position",
        _weighted_mean(cur_gsc, "position", "impressions"),
        _weighted_mean(prev_gsc, "position", "impressions"),
    )

    return KpiBundle(sessions=sessions, users=users, conversions=conversions,
                      clicks=clicks, impressions=impressions, ctr=ctr,
                      avg_position=avg_position)


def keyword_movements(current: pd.DataFrame, previous: pd.DataFrame,
                        key: str = "query",
                        position_col: str = "position",
                        top_n: int = 10) -> dict[str, pd.DataFrame]:
    """Compare keyword positions between two periods.

    Lower position numbers are better. ``wins`` lists keywords whose
    position improved the most, ``losses`` lists the worst regressions.
    """
    if current.empty:
        return {"wins": pd.DataFrame(), "losses": pd.DataFrame()}
    if previous.empty:
        merged = current.copy()
        merged["previous_position"] = None
        merged["delta"] = None
        return {"wins": merged.head(top_n), "losses": pd.DataFrame()}

    cur = current[[key, position_col, "clicks", "impressions"]].copy()
    prev = previous[[key, position_col]].copy()
    prev = prev.rename(columns={position_col: "previous_position"})

    merged = cur.merge(prev, on=key, how="inner")
    merged["delta"] = merged["previous_position"] - merged[position_col]

    wins = (merged.sort_values("delta", ascending=False)
              .head(top_n)
              .reset_index(drop=True))
    losses = (merged.sort_values("delta", ascending=True)
                .head(top_n)
                .reset_index(drop=True))
    return {"wins": wins, "losses": losses}
