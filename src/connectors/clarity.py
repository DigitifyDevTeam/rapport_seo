"""Microsoft Clarity Data Export API connector.

The Data Export API returns aggregate metrics for the last 1, 2 or 3 days.
For monthly reporting we therefore pull the latest available window and
report it as a snapshot. When the project is unconfigured we return an
empty payload.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import requests

from src.config import ClientConfig, env

logger = logging.getLogger(__name__)

DEFAULT_API_URL = ("https://www.clarity.ms/export-data/api/v1/"
                   "project-live-insights")
TIMEOUT = 30


def fetch(client: ClientConfig, _start: date, _end: date) -> dict[str, pd.DataFrame]:
    project_id = (client.clarity or {}).get("project_id")
    if not project_id:
        logger.info("[clarity] no project for %s, skipping", client.id)
        return {}

    token = env("CLARITY_API_TOKEN")
    if not token:
        logger.info("[clarity] CLARITY_API_TOKEN missing, skipping")
        return {}

    headers = {"Authorization": f"Bearer {token}"}
    params = {"numOfDays": 3, "projectId": project_id}
    api_url = env("CLARITY_API_URL", DEFAULT_API_URL) or DEFAULT_API_URL
    try:
        response = requests.get(api_url, headers=headers, params=params,
                                timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        resp = getattr(exc, "response", None)
        details = _response_details(resp)
        retry_after = resp.headers.get("Retry-After") if resp is not None else None
        suffix = f" (retry-after={retry_after})" if retry_after else ""
        logger.error("[clarity] request failed: %s. Response: %s%s", exc, details, suffix)
        return {}

    payload = response.json()
    return {"insights": _parse(payload)}


def _parse(payload: Any) -> pd.DataFrame:
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("metrics") or [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _response_details(response: requests.Response | None) -> str:
    if response is None:
        return "no response body"
    try:
        return str(response.json())
    except ValueError:
        text = (response.text or "").strip()
        return text[:500] if text else "empty response body"
