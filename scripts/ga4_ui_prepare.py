"""One-time GA4 login (persistent Chrome profile for automated captures).

Opens a browser so you can sign in to Google Analytics. The profile is reused
on every monthly report (same pattern as GMB).

Usage::

    python scripts/ga4_ui_prepare.py
    python scripts/ga4_ui_prepare.py --client cchabitat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from scripts.ga4_ui_capture import _apply_google_compat, _docker_browser_args, _profile_dir
from src.config import PROJECT_ROOT, get_client


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client",
        default="origincbd",
        help="Client id (determines Chrome profile path)",
    )
    args = parser.parse_args(argv)
    client = get_client(args.client)
    profile = _profile_dir(client)
    profile.mkdir(parents=True, exist_ok=True)

    print(f"Profile: {profile}")
    print("Log in to Google Analytics in the browser, open any property home report,")
    print("then press ENTER here.")

    import os

    channel = (os.environ.get("SEO_REPORT_BROWSER_CHANNEL") or "chromium").strip()
    if channel.lower() in ("", "chromium", "bundled"):
        channel = None

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            channel=channel,
            viewport={"width": 1600, "height": 900},
            locale="fr-FR",
            ignore_default_args=["--enable-automation"],
            args=_docker_browser_args(),
        )
        _apply_google_compat(context)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://analytics.google.com/", wait_until="domcontentloaded",
                  timeout=120_000)
        input()
        context.close()

    print(f"Saved profile at {profile}")
    print("Monthly reports will capture GA4 cards automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
