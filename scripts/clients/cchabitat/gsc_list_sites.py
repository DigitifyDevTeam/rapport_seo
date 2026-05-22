"""List Search Console properties visible to the CC Habitat OAuth token.

Usage::

    python scripts/clients/cchabitat/gsc_list_sites.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from src.config import PROJECT_ROOT, get_client
from src.connectors.google_auth import GSC_SCOPES, get_google_credentials


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    client = get_client("cchabitat")
    account = (client.google_oauth_account or "").strip() or None
    creds = get_google_credentials(
        tuple(GSC_SCOPES),
        oauth_token_suffix="gsc",
        oauth_account=account,
    )
    if creds is None:
        print(
            "No OAuth token for cchabitat. Run:\n"
            "  python scripts/clients/cchabitat/google_oauth_login.py"
        )
        return 1

    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    resp = service.sites().list().execute()
    entries = resp.get("siteEntry") or []
    if not entries:
        print("No Search Console properties for this account.")
        return 0
    print("Copy the exact siteUrl into config/clients.yaml -> gsc.site_url:\n")
    for entry in entries:
        url = entry.get("siteUrl", "")
        level = entry.get("permissionLevel", "")
        print(f"  - {url}  ({level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
