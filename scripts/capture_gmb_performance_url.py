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
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import Page, sync_playwright

from scripts.gmb_ui_extract import (  # noqa: E402
    GMB_LOCATIONS_URL,
    _apply_google_compat,
    _discover_performance_url,
    _open_gmb_performance_direct,
    _persist_session,
    _save_client_performance_url,
)
from scripts.gmb_ui_login import (  # noqa: E402
    _find_performance_target,
    _page_shows_performance_ui,
    _print_tab_status,
    _url_looks_like_performance,
    launch_gmb_persistent_context,
    unlock_chrome_profile,
)
from scripts.playwright_browser import docker_chromium_args, gmb_profile_dir
from src.config import ClientConfig, get_client, gmb_ui_session_path


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


def _wait_for_manual_performance(
    context,
    page: Page,
    project: str,
    *,
    via_search: bool = False,
) -> Page | None:
    """Keep the browser open until the user signs in and opens Performance in noVNC."""
    if not via_search:
        try:
            if "accounts.google.com" not in (page.url or ""):
                page.goto(GMB_LOCATIONS_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            pass
    print("")
    if via_search:
        print("Google Search opened (same flow as deepcleaning prepare).")
        print("1) Sign in in noVNC if asked.")
        print(f"2) Click « interactions avec les clients » for {project!r}.")
    else:
        print("Auto-navigation stopped (sign-in required — normal after a VPS IP change).")
        print("1) Sign in in the Chrome window in noVNC.")
        print(f"2) Open Performances for {project!r} on business.google.com.")
    print("3) Press ENTER here when the Performance page is visible.")
    print("")
    while True:
        input("Press ENTER when Performance is visible: ")
        perf_page, perf_url, reason = _find_performance_target(context)
        _print_tab_status(context)
        if perf_page and (
            _url_looks_like_performance(perf_url)
            or _page_shows_performance_ui(perf_page)
        ):
            print(f"\n  OK — {reason}")
            return perf_page
        print(
            "\n  Performance not detected yet.\n"
            "  Finish sign-in, open Performances, then press ENTER again.",
        )


def _maybe_persist_shared_session(
    client: ClientConfig,
    session_path: Path,
    context,
    page: Page,
) -> None:
    """Save cookies after a manual VPS login (shared Google account)."""
    shared = str((client.gmb or {}).get("ui_session_client") or "").strip()
    sessions = ROOT / "outputs" / "_sessions"
    if shared:
        master = sessions / f"gmb-{shared}.json"
        if not master.is_file():
            _persist_session(master, context, page)
            print(f"Saved shared session → {master.name}")
            return
    if not session_path.is_file():
        _persist_session(session_path, context, page)
        print(f"Saved session → {session_path.name}")


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
            print(f"Using Chrome profile: {profile}")
            launch_kw = dict(
                headless=False,
                channel=_browser_channel(),
                ignore_default_args=["--enable-automation"],
                args=browser_args,
            )
            context = launch_gmb_persistent_context(p, profile, launch_kw)
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
        search_query = (gmb.get("ui_search_query") or "").strip()
        if args.show and search_query:
            start_url = (
                "https://www.google.com/search?hl=fr&q="
                + urllib.parse.quote_plus(search_query)
            )
            print(f"Opening Google Search for {project!r} …")
            page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            perf_page = _wait_for_manual_performance(
                context, page, project, via_search=True,
            )
        else:
            perf_page = _open_gmb_performance_direct(page, project, aliases)
            if perf_page is None and args.show:
                perf_page = _wait_for_manual_performance(context, page, project)
        if perf_page is None:
            print("Could not open Performance.")
            if not args.show:
                print("Run with --show to sign in manually in the browser.")
            context.close()
            return 1

        time.sleep(3.0)
        url = perf_page.url or _discover_performance_url(perf_page)
        if not url:
            url = perf_page.url or page.url or ""
        print(f"Performance URL: {url[:120]}…")
        _save_client_performance_url(args.client_id, session_path, url)
        out = session_path.parent / f"gmb-performance-{args.client_id}.txt"
        print(f"Saved → {out}")
        if args.show:
            _maybe_persist_shared_session(client, session_path, context, perf_page)
            input("Press ENTER to close the browser…")
        context.close()

    return 0 if out and out.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
