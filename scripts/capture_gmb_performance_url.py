"""Optional: save per-client Performance URL if prepare did not store ``#mpd=``.

Normally ``gmb_ui_prepare.py`` already saves the URL inside ``gmb-<client>.json``.
Use this only when KPIs stay empty after a successful prepare:

    python scripts/capture_gmb_performance_url.py deepcleaning --show

Writes ``outputs/_sessions/gmb-performance-<client>.txt`` used by ``run_monthly``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from scripts.gmb_ui_extract import (  # noqa: E402
    _apply_google_compat,
    _discover_performance_url,
    _open_gmb_performance_direct,
    _save_client_performance_url,
)
from scripts.gmb_ui_login import unlock_chrome_profile
from scripts.playwright_browser import docker_chromium_args, gmb_profile_dir
from src.config import get_client, gmb_ui_session_path


def _browser_channel() -> str | None:
    raw = (os.environ.get("SEO_REPORT_BROWSER_CHANNEL") or "chrome").strip().lower()
    if raw in ("", "chromium", "bundled"):
        return None
    return raw


def _profile_for_client(client_id: str) -> Path:
    sessions = ROOT / "outputs" / "_sessions"
    fallback = str(sessions / f"chrome-profile-gmb-{client_id}")
    if client_id == "deepcleaning":
        fallback = str(sessions / "chrome-profile-gmb")
    return Path(gmb_profile_dir(sessions, fallback=fallback))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_id", help="e.g. deepcleaning, digitify, cchabitat")
    parser.add_argument("--show", action="store_true", help="Visible browser")
    args = parser.parse_args()

    client = get_client(args.client_id)
    gmb = client.gmb or {}
    project = (gmb.get("ui_project_name") or client.name or client.id).strip()
    aliases = [str(a).strip() for a in (gmb.get("ui_project_aliases") or []) if str(a).strip()]
    session_path = gmb_ui_session_path(client, ROOT / "outputs" / "_sessions")
    if not session_path.is_file() and not args.show:
        print(f"Missing session: {session_path}")
        print(f"Run: python scripts/clients/{args.client_id}/gmb_ui_prepare.py")
        return 1

    if args.show:
        print(f"\n=== {args.client_id} — GMB Performance URL ===")
        print("1) Chrome opens in noVNC.")
        print("2) Sign in with your Google account if asked.")
        print(f"3) Open Performances for {project!r}.")
        print("4) Press ENTER in this terminal when the Performance page is visible.")
        print("")

    profile = _profile_for_client(args.client_id)
    browser_args = docker_chromium_args()
    out: Path | None = None

    with sync_playwright() as p:
        if args.show:
            profile.mkdir(parents=True, exist_ok=True)
            unlock_chrome_profile(profile)
            print(f"Using Chrome profile: {profile}")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
                channel=_browser_channel(),
                ignore_default_args=["--enable-automation"],
                args=browser_args,
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
            )
            _apply_google_compat(context)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(
                headless=True,
                channel=_browser_channel(),
                args=browser_args,
            )
            context = browser.new_context(
                storage_state=str(session_path),
                locale="fr-FR",
                viewport={"width": 1400, "height": 900},
            )
            _apply_google_compat(context)
            page = context.new_page()

        print(f"Opening business.google.com for {project!r} …")
        perf_page = _open_gmb_performance_direct(page, project, aliases)
        if perf_page is None:
            print("Could not open Performance. Sign in in the browser, then retry.")
            context.close()
            return 1
        time.sleep(3.0)
        url = perf_page.url or _discover_performance_url(perf_page)
        if not url:
            url = page.url or ""
        print(f"Performance URL: {url[:120]}…")
        _save_client_performance_url(args.client_id, session_path, url)
        out = session_path.parent / f"gmb-performance-{args.client_id}.txt"
        print(f"Saved → {out}")
        if args.show:
            input("Press ENTER to close the browser…")
        context.close()

    return 0 if out and out.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
