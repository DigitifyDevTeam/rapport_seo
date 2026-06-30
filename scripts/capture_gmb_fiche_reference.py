"""Capture a knowledge-panel screenshot for ``gmb_business_card.png``.

Use in noVNC when automated headless capture fails (e.g. Origincbd):

    bash scripts/capture_gmb_fiche_reference.sh origincbd

Saves to ``scripts/clients/<client>/gmb_business_card.png``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from scripts.gmb_ui_extract import (
    _default_query,
    _launch_browser_context,
    screenshot_public_fiche,
)
from scripts.playwright_browser import gmb_profile_dir
from src.config import get_client, gmb_ui_session_path
from src.gmb.listing_cid import resolve_listing_cid
from src.reporting.gmb_business_card import is_valid_public_fiche_png


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_id", help="Client id (e.g. origincbd)")
    parser.add_argument(
        "--show",
        action="store_true",
        help="Non-headless (required in noVNC).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    client = get_client(args.client_id)
    if not client:
        print(f"Unknown client: {args.client_id}", file=sys.stderr)
        return 1

    gmb_cfg = client.gmb or {}
    sessions = ROOT / "outputs" / "_sessions"
    session_path = gmb_ui_session_path(client, sessions)
    if not session_path.is_file():
        print(f"Missing session: {session_path}", file=sys.stderr)
        return 1

    raw = json.loads(session_path.read_text(encoding="utf-8"))
    storage_state = raw.get("storage_state")

    perf_file = sessions / f"gmb-performance-{client.id}.txt"
    perf_url = perf_file.read_text(encoding="utf-8").strip() if perf_file.is_file() else ""

    project = str(gmb_cfg.get("ui_project_name") or "").strip() or client.name
    search_query = str(gmb_cfg.get("ui_search_query") or "").strip() or _default_query(
        project, client.website or "",
    )
    fiche_match = gmb_cfg.get("ui_fiche_match") or []
    if isinstance(fiche_match, str):
        fiche_match = [fiche_match]
    fiche_hints = [str(x).strip() for x in fiche_match if str(x).strip()]

    out_dir = ROOT / "scripts" / "clients" / client.id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gmb_business_card.png"

    profile = gmb_profile_dir(
        sessions,
        fallback=str(sessions / f"chrome-profile-gmb-{client.id}"),
    )
    listing_cid = resolve_listing_cid(
        str(gmb_cfg.get("ui_listing_cid") or ""),
        perf_url,
    )

    launch_args = SimpleNamespace(
        profile=str(profile) if profile.is_dir() else "",
        channel="",
        show=args.show,
    )

    print(f"Search query: {search_query!r}")
    if listing_cid:
        print(f"Listing CID: {listing_cid}")
    print(f"Output: {out_path}")
    print("Open noVNC, sign in if needed, then wait for the screenshot…")

    with sync_playwright() as pw:
        context, browser, page = _launch_browser_context(
            pw, launch_args, storage_state,
        )
        try:
            shot = screenshot_public_fiche(
                page,
                out_path,
                search_query=search_query,
                fiche_match=fiche_hints,
                listing_cid=listing_cid or None,
            )
        finally:
            try:
                context.close()
            except Exception:
                pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    if not shot or not out_path.is_file():
        print(
            "Capture failed — try adjusting ui_search_query / ui_fiche_match.",
            file=sys.stderr,
        )
        return 1
    if not is_valid_public_fiche_png(out_path):
        print(
            "Saved PNG does not look like a knowledge panel — "
            "delete it and retry with a clearer Maps/Search view.",
            file=sys.stderr,
        )
        return 1
    print(f"OK — valid reference saved to {out_path}")
    print("Add to config/clients.yaml under gmb.business_card_reference if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
