"""CC Habitat — save GMB session (open Performance, press ENTER).

Usage::

    python scripts/clients/cchabitat/gmb_ui_prepare.py
"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "outputs" / "_sessions" / "gmb-cchabitat.json"
PROFILE = ROOT / "outputs" / "_sessions" / "chrome-profile-gmb-cchabitat"
SCRIPT = ROOT / "scripts" / "gmb_ui_login.py"
SEARCH_QUERY = "Concept Confort Habitat couvreur Val-de-Marne"


def main() -> int:
    start_url = (
        "https://www.google.com/search?hl=fr&q="
        + urllib.parse.quote_plus(SEARCH_QUERY)
    )
    print("Sign in with cchabitat.seo@gmail.com if asked.")
    print("1) Browser opens Google Search for Concept Confort Habitat.")
    print("2) Click « XXX interactions avec les clients » under « Votre établissement sur Google ».")
    print("3) Wait for Performance (Vue d'ensemble, Appels, …).")
    print("4) Press ENTER — URL must contain #mpd=")
    print("")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(SESSION),
        "--profile", str(PROFILE),
        "--start-url", start_url,
        "--client-hint", "cchabitat",
        "--location-name", "Concept Confort Habitat",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
