#!/usr/bin/env python3
"""List missing GMB/Clarity UI files per client (for VPS without browsers)."""

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
CLARITY_CARDS = ("overview", "devices", "referrers", "popular_pages")
GMB_CARDS = (
    "business_card", "overview", "calls", "bookings", "directions",
    "website_clicks",
)


def main() -> int:
    print("UI assets check\n")
    for client in load_production_clients():
        print(f"=== {client.id} ({client.name}) ===")
        gmb_sess = SESSIONS / f"gmb-{client.id}.json"
        clr_sess = SESSIONS / f"clarity-{client.id}.json"
        print(f"  session gmb:    {'OK' if gmb_sess.is_file() else 'MISSING'} {gmb_sess}")
        print(f"  session clarity: {'OK' if clr_sess.is_file() else 'MISSING'} {clr_sess}")
        for month_dir in sorted((OUTPUTS_DIR / client.id).glob("20*-*")):
            if not month_dir.is_dir():
                continue
            missing_gmb = [
                f"gmb_card_{k}.png" for k in GMB_CARDS
                if not (month_dir / f"gmb_card_{k}.png").is_file()
                and k != "business_card"
            ]
            if not (month_dir / "gmb_business_card.png").is_file():
                missing_gmb.insert(0, "gmb_business_card.png")
            missing_clr = [
                f"clarity_card_{k}.png" for k in CLARITY_CARDS
                if not (month_dir / f"clarity_card_{k}.png").is_file()
            ]
            label = month_dir.name
            if missing_gmb and missing_clr:
                print(f"  {label}: missing GMB {missing_gmb[:3]}... Clarity {missing_clr[:2]}...")
            elif missing_gmb:
                print(f"  {label}: missing GMB PNGs (API KPIs may still work)")
            elif missing_clr:
                print(f"  {label}: missing Clarity PNGs (API text may still work)")
            else:
                print(f"  {label}: OK (synced UI assets)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
