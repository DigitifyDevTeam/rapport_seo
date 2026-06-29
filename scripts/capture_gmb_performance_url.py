"""Optional: save per-client Performance URL if prepare did not store ``#mpd=``.

Normally ``gmb_ui_prepare.py`` already saves the URL inside ``gmb-<client>.json``.
Use this only when KPIs stay empty after a successful prepare:

    python scripts/capture_gmb_performance_url.py deepcleaning --show

Writes ``outputs/_sessions/gmb-performance-<client>.txt`` used by ``run_monthly``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from scripts.gmb_ui_extract import (  # noqa: E402
    _discover_performance_url,
    _open_gmb_performance_direct,
    _save_client_performance_url,
)
from src.config import get_client, gmb_ui_session_path


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
    if not session_path.is_file():
        print(f"Missing session: {session_path}")
        print(f"Run: python scripts/clients/{args.client_id}/gmb_ui_prepare.py")
        return 1

    state = json.loads(session_path.read_text(encoding="utf-8"))
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.show,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            storage_state=str(session_path),
            locale="fr-FR",
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        print(f"Opening business.google.com for {project!r} …")
        perf_page = _open_gmb_performance_direct(page, project, aliases)
        if perf_page is None:
            print("Could not open Performance. Try --show and sign in again.")
            browser.close()
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
        browser.close()
    return 0 if out.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
