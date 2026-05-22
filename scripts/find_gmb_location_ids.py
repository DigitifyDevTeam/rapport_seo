"""Print GMB location IDs by opening business.google.com locally.

This avoids the My Business Account Management API (rate-limited).
Uses your saved GMB session files in ``outputs/_sessions/``.

Run on Windows where the sessions are valid:

    python scripts/find_gmb_location_ids.py

It opens a headed browser, navigates to business.google.com/locations, and
prints the location IDs hidden in the page URLs / data attributes so you
can paste them into ``.env``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = PROJECT_ROOT / "outputs" / "_sessions"

LOC_ID_RE = re.compile(r"/locations/(\d{6,})")


def _extract_ids(text: str) -> set[str]:
    return set(LOC_ID_RE.findall(text or ""))


def discover(session_file: Path, *, headed: bool = True) -> list[str]:
    print(f"\n=== {session_file.name} ===", flush=True)
    raw = json.loads(session_file.read_text(encoding="utf-8"))
    storage_state = raw.get("storage_state")
    if not storage_state:
        print(f"  skip — no storage_state in {session_file}")
        return []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(
            storage_state=storage_state,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto("https://business.google.com/locations",
                      wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(6_000)
            html = page.content()
            url = page.url
        finally:
            context.close()
            browser.close()

    ids: set[str] = set()
    ids |= _extract_ids(url)
    ids |= _extract_ids(html)
    if not ids:
        print("  no location IDs found — session may be expired. Re-run "
              "your gmb_ui_login.py on Windows.")
        return []
    sorted_ids = sorted(ids)
    print("  IDs found:")
    for loc_id in sorted_ids:
        print(f"    locations/{loc_id}")
    return sorted_ids


def main() -> int:
    if not SESSIONS_DIR.is_dir():
        print(f"No sessions dir at {SESSIONS_DIR}", file=sys.stderr)
        return 1
    sessions = sorted(SESSIONS_DIR.glob("gmb-*.json"))
    if not sessions:
        print("No gmb-*.json sessions in outputs/_sessions/", file=sys.stderr)
        return 1
    for session in sessions:
        client = session.stem.removeprefix("gmb-")
        ids = discover(session)
        if ids:
            print(f"\n  -> .env line: "
                  f"GMB_LOCATION_ID_{client.upper()}=locations/{ids[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
