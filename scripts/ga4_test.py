"""Minimal GA4 access test (low quota usage).

This script makes 1 GA4 Data API call (runReport) for a single client.

Usage:
  python scripts/ga4_test.py --client origincbd
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import get_client  # noqa: E402
from src.connectors.ga4 import _ga4_property_id_override  # noqa: E402
from src.connectors.google_auth import GA4_SCOPES, get_google_credentials  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    args = parser.parse_args()

    client = get_client(args.client)
    pid = (client.ga4 or {}).get("property_id")
    override = _ga4_property_id_override(client.id)
    if override:
        pid = override

    if not pid or not str(pid).strip().isdigit():
        print(
            "Invalid or missing GA4 property_id. Set ga4.property_id in config/clients.yaml "
            "or GA4_PROPERTY_ID_<CLIENT> in .env (numeric)."
        )
        return 2

    creds = get_google_credentials(tuple(GA4_SCOPES), oauth_token_suffix="ga4")
    if creds is None:
        print("No Google credentials available for GA4.")
        return 3

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest
    except ImportError:
        print("google-analytics-data not installed.")
        return 4

    api = BetaAnalyticsDataClient(credentials=creds)
    end = date.today()
    start = end - timedelta(days=7)

    request = RunReportRequest(
        property=f"properties/{str(pid).strip()}",
        metrics=[Metric(name="sessions")],
        date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
    )

    try:
        resp = api.run_report(request)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR calling GA4 runReport: {exc}")
        print("If you see scope/auth errors, re-run:")
        print("  python scripts/google_oauth_login.py")
        return 5

    rows = len(resp.rows or [])
    value = None
    if rows:
        value = resp.rows[0].metric_values[0].value
    print(f"OK: GA4 runReport succeeded. rows={rows} sessions={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

