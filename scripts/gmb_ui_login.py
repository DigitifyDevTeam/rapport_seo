"""Interactive login to Google Business Profile (Playwright).

This opens a real Chromium window so you can:
- Log in with your Google account (SSO + MFA supported).
- Navigate to the Business Profile Performance page for the right location.
- Set the date range to the month you want to report.

When the dashboard shows the correct numbers, return to the terminal and press
ENTER. The script saves a Playwright storage state + the current URL into a
session file used by ``gmb_ui_extract.py``.

Usage:
  python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-origincbd.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def _apply_google_compat(context) -> None:
    # Best-effort hardening to avoid Google blocking automated Chromium.
    # Not perfect, but improves reliability significantly.
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Session JSON output path")
    parser.add_argument(
        "--profile",
        default="",
        help=(
            "Optional persistent Chromium user data dir. Using a profile lets you "
            "stay logged in between runs (recommended)."
        ),
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help="Browser channel to use (recommended: chrome).",
    )
    parser.add_argument(
        "--start-url",
        default="https://business.google.com/",
        help="Initial URL to open (default: business.google.com)",
    )
    parser.add_argument(
        "--location-name",
        default="",
        help="Optional location / project name to click (e.g. origincbd.fr).",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        if args.profile:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(Path(args.profile).resolve()),
                headless=False,
                viewport={"width": 1600, "height": 900},
                channel=args.channel or None,
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            _apply_google_compat(context)
        else:
            browser = pw.chromium.launch(
                headless=False,
                channel=args.channel or None,
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            _apply_google_compat(context)
            page = context.new_page()

        page.goto(args.start_url, wait_until="domcontentloaded")

        if args.location_name:
            try:
                # Best-effort: click the location by visible text.
                page.get_by_text(args.location_name, exact=False).first.click(timeout=5000)
            except Exception:
                pass

        print("")
        print("In the opened browser:")
        print("  1) Sign in to Google.")
        print("  2) Open the correct location (e.g. Origincbd).")
        print("  3) Optional: open Performance to verify access.")
        print("  4) Stay signed in — gmb_ui_extract.py will automate the rest.")
        print("Then come back here and press ENTER.")
        input()

        url = page.url
        storage_state = context.storage_state()

        payload = {"url": url, "storage_state": storage_state}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved session to {out_path}")
        print(f"Captured dashboard URL: {url}")

        context.close()
        if "browser" in locals():
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

