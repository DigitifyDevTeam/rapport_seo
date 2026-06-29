"""Guivarche — save GMB session (Google Search → Performance → ENTER).

Prefer the shared-account flow (same Google login as DeepCleaning)::

    python scripts/gmb_ui_prepare_shared_account.py

That saves cookies in ``gmb-deepcleaning.json`` and ``gmb-performance-guivarche.txt``.
Only run this script if you need a dedicated ``gmb-guivarche.json``.

Usage::

    python scripts/clients/guivarche/gmb_ui_prepare.py
"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "outputs" / "_sessions" / "gmb-guivarche.json"
PROFILE = ROOT / "outputs" / "_sessions" / "chrome-profile-gmb"
SCRIPT = ROOT / "scripts" / "gmb_ui_login.py"
SEARCH_QUERY = "Guivarche déménagement"


def main() -> int:
    start_url = (
        "https://www.google.com/search?hl=fr&q="
        + urllib.parse.quote_plus(SEARCH_QUERY)
    )
    print("Guivarche — GMB session capture")
    print("1) Browser opens Google Search for your fiche.")
    print("2) Sign in once in THAT window.")
    print("3) Click « XXX interactions avec les clients » on the Guivarche panel.")
    print("4) Wait for Performances / Vue d'ensemble.")
    print("5) Press ENTER in this terminal.")
    print("")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(SESSION),
        "--profile", str(PROFILE),
        "--start-url", start_url,
        "--client-hint", "guivarche",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
