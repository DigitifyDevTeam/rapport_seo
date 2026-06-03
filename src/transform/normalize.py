"""Normalize raw connector outputs into stable shapes.

Each function takes the dictionary of dataframes returned by a connector
and returns either an empty dataframe (when the source is unconfigured) or
a dataframe with the canonical columns expected downstream.
"""

from __future__ import annotations

import pandas as pd

GA4_DAILY_COLUMNS = ["date", "sessions", "users", "conversions"]
GSC_DAILY_COLUMNS = ["date", "clicks", "impressions", "ctr", "position"]
GSC_QUERIES_COLUMNS = ["query", "clicks", "impressions", "ctr", "position"]
GSC_PAGES_COLUMNS = ["page", "clicks", "impressions", "ctr", "position"]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({col: pd.Series(dtype="float64") for col in columns})


def normalize_ga4(payload: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    organic = payload.get("organic_daily", pd.DataFrame())
    channels = payload.get("channels", pd.DataFrame())
    channel_daily = payload.get("channel_daily", pd.DataFrame())
    countries = payload.get("countries", pd.DataFrame())
    if organic.empty:
        organic = _empty(GA4_DAILY_COLUMNS)
    else:
        organic = organic.reindex(columns=GA4_DAILY_COLUMNS, fill_value=0)
    pages_daily = payload.get("pages_daily", pd.DataFrame())
    pages_top = payload.get("pages_top", pd.DataFrame())
    active_users_daily = payload.get("active_users_daily", pd.DataFrame())
    return {
        "organic_daily": organic,
        "active_users_daily": active_users_daily,
        "channels": channels,
        "channel_daily": channel_daily,
        "countries": countries,
        "organic_summary": payload.get("organic_summary") or {},
        "overview_summary": payload.get("overview_summary") or {},
        "pages_daily": pages_daily,
        "pages_top": pages_top,
    }


def normalize_gsc(payload: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    daily = payload.get("daily", pd.DataFrame())
    queries = payload.get("queries", pd.DataFrame())
    pages = payload.get("pages", pd.DataFrame())
    if daily.empty:
        daily = _empty(GSC_DAILY_COLUMNS)
    else:
        daily = daily.reindex(columns=GSC_DAILY_COLUMNS, fill_value=0)
    if queries.empty:
        queries = _empty(GSC_QUERIES_COLUMNS)
    else:
        queries = queries.reindex(columns=GSC_QUERIES_COLUMNS, fill_value=0)
    if pages.empty:
        pages = _empty(GSC_PAGES_COLUMNS)
    else:
        pages = pages.reindex(columns=GSC_PAGES_COLUMNS, fill_value=0)
    return {"daily": daily, "queries": queries, "pages": pages}
