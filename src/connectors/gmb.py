"""Google Business Profile connector.

Uses the Performance API
(``businessprofileperformance.googleapis.com``). The connector returns a
daily dataframe with calls, directions and website clicks aggregated from
the per-metric endpoints.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import pandas as pd
import requests
from google.auth.transport.requests import Request

from src.config import ClientConfig
from src.connectors.google_auth import GMB_SCOPES, get_google_credentials

logger = logging.getLogger(__name__)
_GMB_ACCOUNT_403_WARNED = False

PERFORMANCE_BASE = (
    "https://businessprofileperformance.googleapis.com/v1/"
    "{location}:fetchMultiDailyMetricsTimeSeries"
)
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL = (
    "https://mybusinessbusinessinformation.googleapis.com/v1/"
    "{account}/locations"
)
DAILY_METRICS = [
    ("CALL_CLICKS", "calls"),
    ("BUSINESS_DIRECTION_REQUESTS", "directions"),
    ("WEBSITE_CLICKS", "website_clicks"),
]
TIMEOUT = 30

# Avoid listing accounts twice per report (current + previous month).
_LOCATION_CACHE: dict[str, str | None] = {}


def fetch(client: ClientConfig, start: date, end: date) -> dict[str, pd.DataFrame]:
    oauth_account = (client.google_oauth_account or "").strip() or None
    creds = get_google_credentials(
        tuple(GMB_SCOPES),
        oauth_token_suffix="gmb",
        oauth_account=oauth_account,
    )
    if creds is None:
        logger.info("[gmb] no Google credentials available, skipping")
        return {}
    creds.refresh(Request())

    location = _resolve_location(client, creds.token)
    if not location:
        logger.info(
            "[gmb] no location for %s, skipping (set gmb.location_id in clients.yaml "
            "or GMB_LOCATION_ID_%s in .env)",
            client.id,
            client.id.upper(),
        )
        return {}

    headers = {"Authorization": f"Bearer {creds.token}"}
    url = PERFORMANCE_BASE.format(location=location)
    params: list[tuple[str, str]] = [
        ("dailyRange.startDate.year", str(start.year)),
        ("dailyRange.startDate.month", str(start.month)),
        ("dailyRange.startDate.day", str(start.day)),
        ("dailyRange.endDate.year", str(end.year)),
        ("dailyRange.endDate.month", str(end.month)),
        ("dailyRange.endDate.day", str(end.day)),
    ]
    for metric, _ in DAILY_METRICS:
        params.append(("dailyMetrics", metric))

    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        details = _response_details(getattr(exc, "response", None))
        retry_after = None
        if getattr(exc, "response", None) is not None:
            retry_after = exc.response.headers.get("Retry-After")
        suffix = f" (retry-after={retry_after})" if retry_after else ""
        logger.error("[gmb] request failed: %s. Google response: %s%s", exc, details, suffix)
        return {}

    payload = response.json()
    df = _parse_performance(payload)
    return {"daily": df}


def _resolve_location(client: ClientConfig, token: str) -> str | None:
    cached = _LOCATION_CACHE.get(client.id)
    if cached is not None or client.id in _LOCATION_CACHE:
        return cached

    gmb = client.gmb or {}
    location = _normalize_location_id((gmb.get("location_id") or "").strip())
    if location:
        _LOCATION_CACHE[client.id] = location
        return location
    raw_loc = (gmb.get("location_id") or "").strip()
    if raw_loc:
        logger.warning(
            "[gmb] ignoring invalid gmb.location_id for %s (%r); "
            "use locations/123... or a numeric id, or "
            "GMB_LOCATION_ID_%s in .env",
            client.id,
            raw_loc,
            client.id.upper(),
        )

    account = (gmb.get("account_id") or "").strip()
    if account:
        locations = _list_locations(token, account)
        if len(locations) == 1:
            picked = locations[0]
            logger.info("[gmb] auto-selected location for %s from account %s: %s",
                        client.id, account, picked)
            _LOCATION_CACHE[client.id] = picked
            return picked
        if len(locations) > 1:
            logger.warning(
                "[gmb] multiple locations found for %s on %s; set explicit "
                "gmb.location_id. Found: %s",
                client.id,
                account,
                ", ".join(locations[:5]),
            )
        _LOCATION_CACHE[client.id] = None
        return None

    accounts = _list_accounts(token)
    if len(accounts) == 1:
        discovered_account = accounts[0]
        locations = _list_locations(token, discovered_account)
        if len(locations) == 1:
            picked = locations[0]
            logger.info(
                "[gmb] auto-discovered account and location for %s: %s -> %s",
                client.id,
                discovered_account,
                picked,
            )
            _LOCATION_CACHE[client.id] = picked
            return picked
        if len(locations) > 1:
            logger.warning(
                "[gmb] account %s has %d locations; set gmb.location_id explicitly "
                "for %s",
                discovered_account,
                len(locations),
                client.id,
            )
            _LOCATION_CACHE[client.id] = None
            return None
    elif len(accounts) > 1:
        logger.warning(
            "[gmb] %d accounts accessible; set gmb.account_id and gmb.location_id "
            "for %s",
            len(accounts),
            client.id,
        )
    _LOCATION_CACHE[client.id] = None
    return None


def _get_json(url: str, token: str, *, params: dict[str, Any] | None = None,
              label: str = "request") -> dict[str, Any] | None:
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(4):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("[gmb] %s failed: %s", label, exc)
            return None
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", min(60, 2 ** attempt)))
            logger.warning(
                "[gmb] %s rate limited (429); retry in %ss (attempt %s/4)",
                label, wait, attempt + 1,
            )
            time.sleep(wait)
            continue
        if not response.ok:
            logger.warning("[gmb] %s HTTP %s: %s", label, response.status_code,
                           _response_details(response)[:200])
            return None
        return response.json()
    logger.warning("[gmb] %s still rate limited after retries", label)
    return None


def _list_accounts(token: str) -> list[str]:
    global _GMB_ACCOUNT_403_WARNED
    payload = _get_json(ACCOUNTS_URL, token, label="list accounts")
    if payload is None:
        return []
    entries = payload.get("accounts") or []
    return [str(e.get("name", "")).strip() for e in entries if e.get("name")]


def _list_locations(token: str, account: str) -> list[str]:
    payload = _get_json(
        LOCATIONS_URL.format(account=account),
        token,
        params={"readMask": "name", "pageSize": 100},
        label=f"list locations ({account})",
    )
    if payload is None:
        return []
    entries = payload.get("locations") or []
    return [str(e.get("name", "")).strip() for e in entries if e.get("name")]


def _response_details(response: requests.Response | None) -> str:
    if response is None:
        return "no response body"
    try:
        payload = response.json()
        return str(payload)
    except ValueError:
        text = (response.text or "").strip()
        return text[:500] if text else "empty response body"

def _normalize_location_id(raw: str) -> str | None:
    loc = (raw or "").strip()
    if not loc or "<" in loc or ">" in loc:
        return None
    if loc.startswith("locations/") and len(loc) > len("locations/"):
        return loc
    if loc.isdigit():
        return f"locations/{loc}"
    return None


def _parse_performance(payload: dict[str, Any]) -> pd.DataFrame:
    series = payload.get("multiDailyMetricTimeSeries") or []
    metric_lookup = dict(DAILY_METRICS)

    rows: dict[date, dict[str, Any]] = {}
    for metric, datapoints in _iter_metric_datapoints(series):
        column = metric_lookup.get(metric)
        if not column:
            continue
        _apply_datapoints(rows, column, datapoints)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows.values()).sort_values("date").reset_index(drop=True)
    for _, column in DAILY_METRICS:
        if column not in df.columns:
            df[column] = 0
    return df


def _iter_metric_datapoints(series: list[dict[str, Any]]):
    for entry in series:
        for ts in entry.get("dailyMetricTimeSeries") or []:
            metric = ts.get("dailyMetric")
            datapoints = (ts.get("timeSeries") or {}).get("datedValues") or []
            yield metric, datapoints


def _apply_datapoints(rows: dict[date, dict[str, Any]], column: str,
                      datapoints: list[dict[str, Any]]) -> None:
    for dp in datapoints:
        key = _parse_date(dp.get("date") or {})
        if key is None:
            continue
        row = rows.setdefault(key, {"date": key})
        row[column] = float(dp.get("value", 0))


def _parse_date(d: dict[str, Any]) -> date | None:
    try:
        return date(int(d["year"]), int(d["month"]), int(d["day"]))
    except Exception:  # noqa: BLE001
        return None
