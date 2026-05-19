"""Minimal Google Search Console access test (low quota usage).

This script makes 1 API call: sites().list()

Usage:
  python scripts/gsc_test.py --client origincbd
  python scripts/gsc_test.py --client origincbd --show-all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import get_client  # noqa: E402
from src.connectors.google_auth import GSC_SCOPES, get_google_credentials  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--show-all", action="store_true", help="Print all accessible properties")
    args = parser.parse_args()

    client = get_client(args.client)
    configured = ((client.gsc or {}).get("site_url") or "").strip()
    if not configured:
        print("Client has no gsc.site_url configured in config/clients.yaml")
        return 2

    creds = get_google_credentials(tuple(GSC_SCOPES), oauth_token_suffix="gsc")
    if creds is None:
        print("No Google credentials available for GSC.")
        return 3

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client not installed.")
        return 4

    service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    try:
        resp = service.sites().list().execute()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR calling sites().list(): {exc}")
        print("If you see 'insufficient authentication scopes', re-run:")
        print("  python scripts/google_oauth_login.py")
        return 5

    entries = resp.get("siteEntry", []) or []
    urls = [e.get("siteUrl", "") for e in entries if e.get("siteUrl")]

    print(f"Configured site_url: {configured!r}")
    print(f"Accessible properties: {len(urls)}")
    if configured in urls:
        print("OK: configured site_url is accessible.")
        return 0

    # Show helpful near-matches without doing extra API calls.
    configured_norm = (
        configured.lower()
        .replace("sc-domain:", "")
        .replace("https://", "")
        .replace("http://", "")
        .strip("/")
    )
    matches = []
    for u in urls:
        ul = (
            u.lower()
            .replace("sc-domain:", "")
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
        )
        if configured_norm and configured_norm in ul:
            matches.append(u)

    if matches:
        print("Likely matches (pick one and set gsc.site_url exactly):")
        for u in matches[:10]:
            print(f"  - {u}")
    else:
        print("No obvious match found. Either access is missing or property string differs.")

    if args.show_all and urls:
        print("\nAll accessible properties:")
        for u in urls:
            print(f"  - {u}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

