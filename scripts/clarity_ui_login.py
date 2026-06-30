"""Interactive login to Microsoft Clarity (Playwright — works in Docker/noVNC).

Saves cookies + storage for ``clarity_ui_extract.js``.

Usage:
  python scripts/clarity_ui_login.py \\
      --out outputs/_sessions/clarity-origincbd.json \\
      --profile outputs/_sessions/chrome-profile-clarity \\
      --project-id iqfjm1ewdj
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from scripts.gmb_ui_login import launch_gmb_persistent_context, unlock_chrome_profile
from scripts.playwright_browser import docker_chromium_args


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Session JSON output path")
    parser.add_argument(
        "--profile",
        default="outputs/_sessions/chrome-profile-clarity",
        help="Persistent Chromium profile directory",
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="Clarity project id (opens dashboard URL)",
    )
    return parser.parse_args()


def _storage_snapshot(page) -> dict[str, dict[str, str]]:
    return page.evaluate(
        """() => {
        const local = {};
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          local[k] = localStorage.getItem(k);
        }
        const session = {};
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          session[k] = sessionStorage.getItem(k);
        }
        return { localStorage: local, sessionStorage: session };
      }""",
    )


def main() -> int:
    args = _parse_args()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = Path(args.profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    unlock_chrome_profile(profile)

    project_id = (args.project_id or "").strip()
    start_url = (
        f"https://clarity.microsoft.com/projects/view/{project_id}/dashboard"
        if project_id
        else "https://clarity.microsoft.com/"
    )

    launch_kw = dict(
        headless=False,
        channel=None,
        ignore_default_args=["--enable-automation"],
        args=docker_chromium_args(),
    )

    with sync_playwright() as pw:
        try:
            context = launch_gmb_persistent_context(pw, profile, launch_kw)
        except PlaywrightError as exc:
            print(f"Chromium failed to start: {exc}", file=sys.stderr)
            print(
                "Ensure seo-vnc is running and you use:\n"
                "  bash scripts/clarity_ui_prepare_vnc_client.sh <client>",
                file=sys.stderr,
            )
            return 1

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=120_000)
        except PlaywrightError as exc:
            print(f"Navigation failed: {exc}", file=sys.stderr)

        print("")
        print("In the noVNC browser window:")
        print("  1) Sign in to Microsoft Clarity if asked.")
        if project_id:
            print(f"  2) Open the project dashboard (id: {project_id}).")
        else:
            print("  2) Open your project dashboard.")
        print("  3) Wait until KPI cards (Sessions, etc.) are visible.")
        print("Then press ENTER in this terminal.")
        input()

        cookies = context.cookies()
        url = page.url
        storage = _storage_snapshot(page)
        payload = {"cookies": cookies, "storage": storage, "url": url}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved session to {out_path}")
        print(f"Captured dashboard URL: {url}")
        context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
