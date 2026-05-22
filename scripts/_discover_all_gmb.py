"""Discover GMB location IDs for all clients (run on Windows)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.connectors.google_auth import GMB_SCOPES, get_google_credentials
from google.auth.transport.requests import Request
import requests

def discover(label, oauth_account=None):
    creds = get_google_credentials(
        tuple(GMB_SCOPES), oauth_token_suffix="gmb", oauth_account=oauth_account,
    )
    if not creds:
        print(f"[{label}] no credentials")
        return
    creds.refresh(Request())
    h = {"Authorization": f"Bearer {creds.token}"}
    r = requests.get(
        "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
        headers=h, timeout=30,
    )
    print(f"\n[{label}] accounts HTTP {r.status_code}")
    if not r.ok:
        print(f"  {r.text[:300]}")
        return
    for acc in r.json().get("accounts", []):
        name = acc.get("name", "")
        print(f"  account: {acc.get('accountName', '')} -> {name}")
        r2 = requests.get(
            f"https://mybusinessbusinessinformation.googleapis.com/v1/{name}/locations",
            headers=h, params={"readMask": "name,title,websiteUri"}, timeout=30,
        )
        if r2.ok:
            for loc in r2.json().get("locations", []):
                title = loc.get("title", "")
                loc_id = loc.get("name", "")
                site = loc.get("websiteUri", "")
                print(f"    {title} -> {loc_id}  ({site})")
                print(f"    .env: GMB_LOCATION_ID_???={loc_id}")

print("=== Main token (digitify, origincbd, deepcleaning) ===")
discover("main")

print("\n=== CC Habitat token ===")
discover("cchabitat", oauth_account="cchabitat")
