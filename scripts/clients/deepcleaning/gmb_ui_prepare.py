"""DeepCleaning — save GMB session (Google Search → Performance → ENTER).

Usage::

    python scripts/clients/deepcleaning/gmb_ui_prepare.py

On the VPS, copy ``outputs/_sessions/gmb-deepcleaning.json`` after a good local run
(URL must contain ``#mpd=``, same as Origincbd).
"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.playwright_browser import gmb_profile_dir

SESSION = ROOT / "outputs" / "_sessions" / "gmb-deepcleaning.json"
PROFILE = Path(gmb_profile_dir(
    ROOT / "outputs" / "_sessions",
    fallback=str(ROOT / "outputs" / "_sessions" / "chrome-profile-gmb"),
))
SCRIPT = ROOT / "scripts" / "gmb_ui_login.py"
SEARCH_QUERY = "Deep Cleaning Lavage et nettoyage professionnel Colombes"


def main() -> int:
    start_url = (
        "https://www.google.com/search?hl=fr&q="
        + urllib.parse.quote_plus(SEARCH_QUERY)
    )
    print("DeepCleaning — GMB session capture")
    print("1) Browser opens Google Search for your fiche.")
    print("2) Sign in once in THAT window (same Google account as other clients is OK).")
    print("3) Click « XXX interactions avec les clients » on the Deep Cleaning panel.")
    print("4) Wait for Performances / Vue d'ensemble.")
    print("5) Press ENTER in this terminal.")
    print("")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(SESSION),
        "--profile", str(PROFILE),
        "--start-url", start_url,
        "--client-hint", "deepcleaning",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
