#!/usr/bin/env python3
"""Quick check: which clients have GMB/Clarity session JSONs?"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from src.config import OUTPUTS_DIR, load_production_clients

SESSIONS = OUTPUTS_DIR / "_sessions"


def main() -> int:
    print(f"Sessions dir: {SESSIONS}\n")
    if not SESSIONS.is_dir():
        print("MISSING — no outputs/_sessions/ folder on this machine.")
        print("Run login scripts on Windows, then sync with push_ui_assets.ps1")
        return 1
    found = sorted(p.name for p in SESSIONS.glob("*.json"))
    print(f"JSON files present ({len(found)}):")
    for name in found:
        print(f"  {name}")
    print()
    print("Per-client status:")
    for client in load_production_clients():
        gmb = SESSIONS / f"gmb-{client.id}.json"
        clr = SESSIONS / f"clarity-{client.id}.json"
        gmb_ok = "OK " if gmb.is_file() else "--- "
        clr_ok = "OK " if clr.is_file() else "--- "
        print(f"  {client.id:<14}  gmb {gmb_ok}  clarity {clr_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
