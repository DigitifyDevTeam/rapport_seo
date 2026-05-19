"""Google Analytics 4 connector."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from src.config import ClientConfig, env
from src.connectors.google_auth import GA4_SCOPES, get_google_credentials

logger = logging.getLogger(__name__)

_GA4_PID_WARNED: set[tuple[str, str]] = set()


def _ga4_property_id_override(client_id: str) -> str | None:
    specific = env(f"GA4_PROPERTY_ID_{client_id.strip().upper()}")
    if specific:
        return specific
    return env("GA4_PROPERTY_ID")


def fetch(client: ClientConfig, start: date, end: date) -> dict[str, pd.DataFrame]:
    """Return GA4 daily metrics and channel breakdown for the period."""
    property_id = (client.ga4 or {}).get("property_id")
    override = _ga4_property_id_override(client.id)
    if override:
        property_id = override

    if not property_id:
        logger.info("[ga4] no property configured for %s, skipping", client.id)
        return {}

    pid = str(property_id).strip()
    if not pid.isdigit():
        key = (client.id, pid)
        if key not in _GA4_PID_WARNED:
            logger.warning(
                "[ga4] invalid GA4 property_id for %s (%r): use the numeric Property ID "
                "from GA4 Admin (e.g. 123456789), not a name or placeholder. "
                "Update config/clients.yaml -> ga4.property_id, or set "
                "GA4_PROPERTY_ID_<CLIENT> / GA4_PROPERTY_ID in `.env`.",
                client.id,
                property_id,
            )
            _GA4_PID_WARNED.add(key)
        return {}

    creds = get_google_credentials(tuple(GA4_SCOPES), oauth_token_suffix="ga4")
    if creds is None:
        logger.info("[ga4] no Google credentials available, skipping")
        return {}

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (DateRange, Dimension,
                                                          Metric,
                                                          RunReportRequest)
    except ImportError:
        logger.warning("[ga4] google-analytics-data is not installed")
        return {}

    api = BetaAnalyticsDataClient(credentials=creds)
    property_path = f"properties/{pid}"

    organic_filter = (client.ga4 or {}).get("organic_channel", "Organic Search")

    daily = _run_report(
        api,
        RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name="date"),
                         Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions"), Metric(name="totalUsers"),
                      Metric(name="conversions")],
            date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
        ),
    )
    countries = _run_report(
        api,
        RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name="country")],
            metrics=[Metric(name="activeUsers")],
            date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
        ),
    )

    organic_summary = _fetch_organic_summary(
        api, property_path, start, end, organic_filter)
    pages_daily, pages_top = _fetch_pages_screens(
        api, property_path, start, end)

    if daily.empty:
        return {
            "daily": daily,
            "organic_daily": daily,
            "channels": daily,
            "organic_summary": organic_summary,
            "pages_daily": pages_daily,
            "pages_top": pages_top,
        }

    daily["date"] = pd.to_datetime(daily["date"], format="%Y%m%d")
    for col in ("sessions", "totalUsers", "conversions"):
        daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0)
    daily = daily.rename(columns={"totalUsers": "users",
                                    "sessionDefaultChannelGroup": "channel"})

    organic = (daily[daily["channel"] == organic_filter]
                .groupby("date", as_index=False)
                [["sessions", "users", "conversions"]].sum())

    channels = (daily.groupby("channel", as_index=False)
                  [["sessions", "users", "conversions"]].sum()
                  .sort_values("sessions", ascending=False))
    channel_daily = daily[["date", "channel", "sessions", "users"]].copy()

    if countries.empty:
        countries = pd.DataFrame(columns=["country", "activeUsers"])
    else:
        countries["activeUsers"] = pd.to_numeric(countries["activeUsers"],
                                                  errors="coerce").fillna(0)
        countries = countries.sort_values("activeUsers", ascending=False)

    return {
        "daily": daily,
        "organic_daily": organic,
        "channels": channels,
        "channel_daily": channel_daily,
        "countries": countries,
        "organic_summary": organic_summary,
        "pages_daily": pages_daily,
        "pages_top": pages_top,
    }


def _fetch_pages_screens(api, property_path: str, start: date, end: date
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Engagement > Pages et écrans: daily views + top pages for the period."""
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Metric,
                                                      OrderBy, RunReportRequest)

    daily = _run_report(
        api,
        RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name="screenPageViews")],
            date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
            order_bys=[
                OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date")),
            ],
        ),
    )
    top = _run_report(
        api,
        RunReportRequest(
            property=property_path,
            dimensions=[
                Dimension(name="pageTitle"),
                Dimension(name="pagePath"),
            ],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="sessions"),
                Metric(name="totalUsers"),
            ],
            date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
            order_bys=[
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                    desc=True,
                ),
            ],
            limit=10,
        ),
    )

    if daily.empty:
        pages_daily = pd.DataFrame(columns=["date", "views"])
    else:
        pages_daily = daily.rename(columns={"screenPageViews": "views"}).copy()
        pages_daily["date"] = pd.to_datetime(pages_daily["date"], format="%Y%m%d")
        pages_daily["views"] = pd.to_numeric(pages_daily["views"],
                                              errors="coerce").fillna(0)

    if top.empty:
        pages_top = pd.DataFrame(
            columns=["pageTitle", "pagePath", "views", "sessions", "users"])
    else:
        pages_top = top.rename(columns={
            "screenPageViews": "views",
            "totalUsers": "users",
        }).copy()
        for col in ("views", "sessions", "users"):
            if col in pages_top.columns:
                pages_top[col] = pd.to_numeric(pages_top[col],
                                                errors="coerce").fillna(0)
    return pages_daily, pages_top


def _organic_channel_filter(channel_name: str):
    from google.analytics.data_v1beta.types import Filter, FilterExpression

    return FilterExpression(
        filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=channel_name,
            ),
        )
    )


def _fetch_organic_summary(api, property_path: str, start: date, end: date,
                            organic_filter: str) -> dict[str, float]:
    """Aggregate organic-search metrics for one reporting period."""
    from google.analytics.data_v1beta.types import (DateRange, Metric,
                                                      RunReportRequest)

    metric_names = (
        "sessions",
        "totalUsers",
        "newUsers",
        "engagedSessions",
        "averageSessionDuration",
        "engagementRate",
    )
    request = RunReportRequest(
        property=property_path,
        metrics=[Metric(name=name) for name in metric_names],
        date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
        dimension_filter=_organic_channel_filter(organic_filter),
    )
    frame = _run_report(api, request)
    if frame.empty:
        return {}

    summary: dict[str, float] = {}
    for name in metric_names:
        if name not in frame.columns:
            continue
        summary[name] = float(pd.to_numeric(frame[name].iloc[0],
                                             errors="coerce") or 0)
    return summary


def _run_report(api, request) -> pd.DataFrame:
    try:
        response = api.run_report(request)
    except Exception as exc:  # noqa: BLE001 - bubble up as empty frame
        text = str(exc).lower()
        if "insufficient authentication scopes" in text:
            logger.error(
                "[ga4] OAuth token missing required scopes. Re-run "
                "`python scripts/google_oauth_login.py` and grant GA4 permissions "
                "(analytics). Error: %s",
                exc,
            )
        else:
            logger.error("[ga4] API error: %s", exc)
        return pd.DataFrame()

    headers = ([d.name for d in response.dimension_headers]
               + [m.name for m in response.metric_headers])
    rows = []
    for row in response.rows:
        rows.append([d.value for d in row.dimension_values]
                    + [m.value for m in row.metric_values])
    return pd.DataFrame(rows, columns=headers)
