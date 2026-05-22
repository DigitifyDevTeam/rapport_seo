"""List GBP accounts/locations for the CC Habitat OAuth token.

Usage::

    python scripts/clients/cchabitat/discover_gmb_location.py

Copy ``gmb.account_id`` and ``gmb.location_id`` into config/clients.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, get_client
from src.connectors.google_auth import GMB_SCOPES, get_google_credentials


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    client = get_client("cchabitat")
    account = (client.google_oauth_account or "").strip() or None
    creds = get_google_credentials(
        tuple(GMB_SCOPES),
        oauth_token_suffix="gmb",
        oauth_account=account,
    )
    if creds is None:
        print("Run: python scripts/clients/cchabitat/google_oauth_login.py")
        return 1

    from google.auth.transport.requests import Request
    import requests

    creds.refresh(Request())
    headers = {"Authorization": f"Bearer {creds.token}"}
    r = requests.get(
        "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
        headers=headers,
        timeout=30,
    )
    print("accounts HTTP", r.status_code)
    if not r.ok:
        print(r.text[:500])
        return 1
    for acc in r.json().get("accounts", []):
        name = acc.get("name", "")
        label = acc.get("accountName", "")
        print(f"\n{label}\n  account_id: {name}")
        r2 = requests.get(
            f"https://mybusinessbusinessinformation.googleapis.com/v1/{name}/locations",
            headers=headers,
            timeout=30,
            params={"readMask": "name,title,websiteUri"},
        )
        print("  locations HTTP", r2.status_code)
        if r2.ok:
            for loc in r2.json().get("locations", []):
                print(f"    location_id: {loc.get('name')}")
                print(f"    title: {loc.get('title')}")
                print(f"    website: {loc.get('websiteUri')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
