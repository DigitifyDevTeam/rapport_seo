"""Origine CBD — save GMB session (Google Search → Performance → ENTER).

Usage::

    python scripts/clients/origincbd/gmb_ui_prepare.py

If Playwright Chrome stays stuck on sign-in, use real Chrome instead::

    .\\scripts\\gmb_login_real_chrome.ps1
"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "outputs" / "_sessions" / "gmb-origincbd.json"
PROFILE = ROOT / "outputs" / "_sessions" / "chrome-profile-gmb-origincbd"
SCRIPT = ROOT / "scripts" / "gmb_ui_login.py"
SEARCH_QUERY = "Origine CBD Paris"


def main() -> int:
    start_url = (
        "https://www.google.com/search?hl=fr&q="
        + urllib.parse.quote_plus(SEARCH_QUERY)
    )
    print("Origine CBD — GMB session capture")
    print("1) Browser opens Google Search (not business.google.com — fewer blocks).")
    print("2) Sign in + Authenticator in THAT window only.")
    print("3) Click « XXX interactions avec les clients » on the owner panel.")
    print("4) Wait for Performances / Vue d'ensemble.")
    print("5) Press ENTER in this terminal.")
    print("")
    print("If sign-in never finishes, close this and run:")
    print("  .\\scripts\\gmb_login_real_chrome.ps1")
    print("")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(SESSION),
        "--profile", str(PROFILE),
        "--start-url", start_url,
        "--client-hint", "origincbd",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
