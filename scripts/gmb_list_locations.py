"""List Google Business Profile accounts and locations accessible to OAuth user.

Usage:
  python scripts/gmb_list_locations.py
  python scripts/gmb_list_locations.py --account accounts/123456789
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests
from google.auth.transport.requests import Request

# Running as `python scripts/...` does not put the repo root on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.connectors.google_auth import GMB_SCOPES, get_google_credentials

TIMEOUT = 30
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL = (
    "https://mybusinessbusinessinformation.googleapis.com/v1/"
    "{account}/locations"
)


def _json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"_raw": (response.text or "").strip()}


def list_accounts(token: str) -> list[str]:
    resp = requests.get(ACCOUNTS_URL, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = _json(resp)
    entries = payload.get("accounts") or []
    return [str(e.get("name", "")).strip() for e in entries if e.get("name")]


def list_locations(token: str, account: str) -> list[str]:
    resp = requests.get(
        LOCATIONS_URL.format(account=account),
        headers={"Authorization": f"Bearer {token}"},
        params={"readMask": "name,title", "pageSize": 100},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    payload = _json(resp)
    entries = payload.get("locations") or []
    out: list[str] = []
    for e in entries:
        name = str(e.get("name", "")).strip()
        title = str(e.get("title", "")).strip()
        if name:
            out.append(f"{name}" + (f"  ({title})" if title else ""))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", help="Account resource name, e.g. accounts/123")
    args = parser.parse_args()

    creds = get_google_credentials(tuple(GMB_SCOPES), oauth_token_suffix="gmb")
    if creds is None:
        raise SystemExit(
            "No Google OAuth credentials found. Configure GOOGLE_OAUTH_* and run "
            "python scripts/google_oauth_login.py"
        )
    creds.refresh(Request())
    token = creds.token

    if args.account:
        accounts = [args.account]
    else:
        try:
            accounts = list_accounts(token)
        except requests.RequestException as exc:
            resp = getattr(exc, "response", None)
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            suffix = f" (retry-after={retry_after})" if retry_after else ""
            details = _json(resp) if resp is not None else "no response"
            print(f"ERROR listing accounts: {exc}{suffix}\nDetails: {details}")
            return
    if not accounts:
        print("No Business Profile accounts accessible to this OAuth user.")
        return

    for account in accounts:
        print(f"\n{account}")
        try:
            locations = list_locations(token, account)
        except requests.RequestException as exc:
            resp = getattr(exc, "response", None)
            details = _json(resp) if resp is not None else "no response"
            print(f"  ERROR listing locations: {exc}\n  Details: {details}")
            continue
        if not locations:
            print("  (no locations)")
            continue
        for loc in locations:
            print(f"  - {loc}")


if __name__ == "__main__":
    main()

