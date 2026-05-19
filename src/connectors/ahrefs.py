"""Ahrefs connector.

Ahrefs offers several endpoints depending on your subscription tier
(``site-explorer``, ``rank-tracker``...). This connector targets two
generic v3 endpoints and falls back to an empty response when the API
token is not configured. Endpoint paths are kept as constants so they can
be adapted to your specific plan without touching the rest of the
pipeline.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import requests

from src.config import ClientConfig, env

logger = logging.getLogger(__name__)

API_ROOT = "https://api.ahrefs.com/v3"
OVERVIEW_ENDPOINT = f"{API_ROOT}/site-explorer/overview"
ORGANIC_KEYWORDS_ENDPOINT = f"{API_ROOT}/site-explorer/organic-keywords"
TIMEOUT = 30


def fetch(client: ClientConfig, start: date, end: date) -> dict[str, pd.DataFrame]:
    target = (client.ahrefs or {}).get("target")
    if not target:
        logger.info("[ahrefs] no target configured for %s, skipping", client.id)
        return {}

    token = env("AHREFS_API_TOKEN")
    if not token:
        logger.info("[ahrefs] AHREFS_API_TOKEN missing, skipping")
        return {}

    headers = {"Authorization": f"Bearer {token}",
                "Accept": "application/json"}
    mode = (client.ahrefs or {}).get("mode", "domain")

    overview = _safe_get(OVERVIEW_ENDPOINT, headers, params={
        "target": target, "mode": mode, "date": str(end),
    })
    keywords = _safe_get(ORGANIC_KEYWORDS_ENDPOINT, headers, params={
        "target": target, "mode": mode, "date": str(end),
        "limit": 1000, "order_by": "traffic:desc",
    })

    return {
        "overview": _to_dataframe(overview),
        "keywords": _to_dataframe(keywords, key="keywords"),
    }


def _safe_get(url: str, headers: dict[str, str],
                params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=headers, params=params,
                                  timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[ahrefs] request to %s failed: %s", url, exc)
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _to_dataframe(payload: dict[str, Any],
                   key: str | None = None) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame()
    if key and key in payload:
        rows = payload[key]
    elif "data" in payload:
        rows = payload["data"]
    else:
        rows = payload
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return pd.DataFrame()
    return pd.DataFrame(rows)
