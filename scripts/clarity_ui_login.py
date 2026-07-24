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
from scripts.playwright_browser import chromium_vnc_launch_kwargs, in_vnc

_AGENCY_CLARITY_SYNC_IDS = (
    "deepcleaning",
    "origincbd",
    "digitify",
    "guivarche",
    "cchabitat",
)


def _propagate_clarity_session(sessions_dir: Path, payload: dict, source: Path) -> None:
    """Copy one agency login to all Clarity session files (same Microsoft account)."""
    text = json.dumps(payload, indent=2)
    (sessions_dir / "clarity-shared.json").write_text(text, encoding="utf-8")
    for client_id in _AGENCY_CLARITY_SYNC_IDS:
        target = sessions_dir / f"clarity-{client_id}.json"
        if target.resolve() == source.resolve():
            continue
        target.write_text(text, encoding="utf-8")
    print(
        "Synced Clarity cookies to clarity-shared.json and agency client sessions.",
        flush=True,
    )


def _launch_clarity_context(pw, profile: Path, launch_kw: dict):
    """Ephemeral browser in noVNC (avoids crashpad/user-data-dir issues); profile optional elsewhere."""
    if in_vnc():
        print("Using ephemeral Chromium (no persistent profile) in noVNC.", flush=True)
        browser = pw.chromium.launch(**launch_kw)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        context._ephemeral_browser = browser  # noqa: SLF001 — closed in main()
        return context

    return launch_gmb_persistent_context(pw, profile, launch_kw)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Session JSON output path")
    parser.add_argument(
        "--profile",
        default="outputs/_sessions/chrome-profile-clarity",
        help="Persistent Chromium profile (skipped in noVNC — session JSON is enough)",
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
    if not in_vnc():
        profile.mkdir(parents=True, exist_ok=True)
        unlock_chrome_profile(profile)

    project_id = (args.project_id or "").strip()
    start_url = (
        f"https://clarity.microsoft.com/projects/view/{project_id}/dashboard"
        if project_id
        else "https://clarity.microsoft.com/"
    )

    launch_kw = chromium_vnc_launch_kwargs()

    with sync_playwright() as pw:
        try:
            context = _launch_clarity_context(pw, profile, launch_kw)
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
        print("     IMPORTANT: tick 'Rester connecté' / 'Keep me signed in'")
        print("     so a PERSISTENT cookie is saved (otherwise the session")
        print("     dies after one run and reports come back empty).")
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
        _propagate_clarity_session(out_path.parent, payload, out_path)
        print(f"Saved session to {out_path}")
        print(f"Captured dashboard URL: {url}")
        browser = getattr(context, "_ephemeral_browser", None)
        context.close()
        if browser:
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
