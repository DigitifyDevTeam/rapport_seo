"""Print GMB location IDs by opening business.google.com with saved sessions.

This bypasses the My Business Account Management API (rate-limited).
Run on Windows where the GMB sessions in ``outputs/_sessions/`` are valid:

    python scripts/find_gmb_location_ids.py            # all gmb-*.json
    python scripts/find_gmb_location_ids.py origincbd  # one client
    python scripts/find_gmb_location_ids.py --keep-open  # debug mode

Strategy (per session):
1. Open business.google.com/locations with the saved storage_state.
2. If Google bounces to a sign-in URL, report session expired.
3. Scan the rendered DOM (data attributes, hrefs, in-page JSON blobs) for
   ``/locations/<digits>`` patterns and any 10-20 digit GBP IDs.
4. Click each "See your profile / Voir le profil" link in turn; the URL
   that opens contains the canonical ``/locations/<id>`` we need.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_client, gmb_ui_session_path  # noqa: E402

SESSIONS_DIR = PROJECT_ROOT / "outputs" / "_sessions"

LOC_URL_RE = re.compile(r"/locations?/(\d{6,})")
LOC_ID_RE = re.compile(r'"(\d{10,})"')


def _extract_ids(text: str) -> list[str]:
    """Return location IDs found anywhere in HTML, JSON blobs, or URLs."""
    seen: list[str] = []

    def _add(value: str) -> None:
        if value and value not in seen:
            seen.append(value)

    for match in LOC_URL_RE.findall(text or ""):
        _add(match)
    # Look for long all-digit identifiers in JSON payloads embedded in scripts.
    # GBP IDs are typically 10-20 digits; filter common false positives.
    for match in LOC_ID_RE.findall(text or ""):
        if len(match) >= 10 and not match.startswith(("0", "1604", "1605")):
            _add(match)
    return seen


def _looks_like_login(url: str) -> bool:
    url = url or ""
    return (
        "accounts.google.com" in url
        and ("signin" in url or "accountchooser" in url
             or "ServiceLogin" in url or "AccountLite" in url)
    )


def _scan_profile_links(page: Page) -> list[str]:
    """Click each "Voir le profil" link, harvest the resulting /locations/<id>."""
    discovered: list[str] = []
    labels = ("Voir le profil", "Voir votre profil", "See your profile",
              "View your profile", "View profile")
    try:
        rows_count = 0
        for label in labels:
            try:
                rows_count = max(rows_count, page.get_by_text(label).count())
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        rows_count = 0

    for idx in range(rows_count):
        try:
            link = None
            for label in labels:
                try:
                    candidate = page.get_by_text(label).nth(idx)
                    if candidate and candidate.count() > 0:
                        link = candidate
                        break
                except Exception:  # noqa: BLE001
                    continue
            if link is None:
                continue
            with page.expect_popup(timeout=8_000) as popup_info:
                link.click(timeout=5_000)
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=15_000)
            ids = _extract_ids(popup.url) + _extract_ids(popup.content())
            for loc_id in ids:
                if loc_id not in discovered:
                    discovered.append(loc_id)
            popup.close()
        except Exception:  # noqa: BLE001
            try:
                # Some links open in same tab; collect URL changes.
                ids = _extract_ids(page.url)
                for loc_id in ids:
                    if loc_id not in discovered:
                        discovered.append(loc_id)
            except Exception:  # noqa: BLE001
                pass
    return discovered


def discover(session_file: Path, *, headed: bool, keep_open: bool) -> list[str]:
    print(f"\n=== {session_file.name} ===", flush=True)
    raw = json.loads(session_file.read_text(encoding="utf-8"))
    storage_state = raw.get("storage_state")
    if not storage_state:
        print(f"  skip — no storage_state in {session_file}")
        return []

    found: list[str] = []
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
            final_url = page.url
            print(f"  final URL: {final_url}")
            if _looks_like_login(final_url):
                print("  session EXPIRED/rejected — re-run gmb_ui_login.py.")
                return []
            html = page.content()
            for loc_id in _extract_ids(final_url) + _extract_ids(html):
                if loc_id not in found:
                    found.append(loc_id)
            if not found:
                print("  scanning profile links...")
                for loc_id in _scan_profile_links(page):
                    if loc_id not in found:
                        found.append(loc_id)
            if keep_open:
                print("  --keep-open: leaving browser open. Press Enter here "
                      "when you have manually copied the IDs from the URL bar.")
                try:
                    input()
                except EOFError:
                    time.sleep(120)
        finally:
            context.close()
            browser.close()

    if not found:
        print("  no location IDs found.")
        return []
    print("  IDs found:")
    for loc_id in found:
        print(f"    locations/{loc_id}")
    return found


def _iter_client_sessions(
    filter_clients: Iterable[str],
) -> list[tuple[str, Path]]:
    """Return ``(client_id, session_file)``; honors ``gmb.ui_session_client``."""
    if not SESSIONS_DIR.is_dir():
        print(f"No sessions dir at {SESSIONS_DIR}", file=sys.stderr)
        return []
    requested = [c.lower().strip() for c in filter_clients if c.strip()]
    if not requested:
        requested = [
            s.stem.removeprefix("gmb-")
            for s in sorted(SESSIONS_DIR.glob("gmb-*.json"))
        ]
    seen_paths: set[Path] = set()
    out: list[tuple[str, Path]] = []
    for client_id in requested:
        try:
            client = get_client(client_id)
        except KeyError:
            print(f"Unknown client id: {client_id}", file=sys.stderr)
            continue
        path = gmb_ui_session_path(client, SESSIONS_DIR)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        owner = path.stem.removeprefix("gmb-")
        if owner != client_id:
            print(
                f"[{client_id}] using shared session {path.name} "
                f"(ui_session_client={owner})",
                flush=True,
            )
        out.append((client_id, path))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "clients", nargs="*",
        help="Optional client ids (origincbd, digitify, ...) to filter.",
    )
    parser.add_argument("--headless", action="store_true",
                        help="Run without showing the browser window.")
    parser.add_argument(
        "--keep-open", action="store_true",
        help="Pause after each session so you can read URLs manually.",
    )
    args = parser.parse_args(argv)

    client_sessions = _iter_client_sessions(args.clients)
    if not client_sessions:
        print("No matching clients / sessions.", file=sys.stderr)
        return 1

    summary: list[str] = []
    for client_id, session in client_sessions:
        ids = discover(
            session, headed=not args.headless, keep_open=args.keep_open,
        )
        if ids:
            line = (f"GMB_LOCATION_ID_{client_id.upper()}="
                    f"locations/{ids[0]}")
            summary.append(line)

    if summary:
        print("\n=== Paste into .env ===")
        for line in summary:
            print(line)
    else:
        print("\nNo IDs collected. Use --keep-open and look at the URL "
              "in the address bar when you click your business; the part "
              "/locations/<digits> is the ID.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
