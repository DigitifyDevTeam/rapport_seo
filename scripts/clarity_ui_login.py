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
import os
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


def _atomic_write_text(path: Path, text: str) -> None:
    """Write session JSON by rename, so a root-owned file can still be replaced.

    Opening the existing file for truncate needs write permission on that file.
    Replacing it only needs write permission on the directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _propagate_clarity_session(sessions_dir: Path, payload: dict, source: Path) -> None:
    """Copy one agency login to all Clarity session files (same Microsoft account)."""
    text = json.dumps(payload, indent=2)
    _atomic_write_text(sessions_dir / "clarity-shared.json", text)
    for client_id in _AGENCY_CLARITY_SYNC_IDS:
        target = sessions_dir / f"clarity-{client_id}.json"
        if target.resolve() == source.resolve():
            continue
        _atomic_write_text(target, text)
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


_GOOGLE_AUTH_COOKIE_NAMES = frozenset({
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LSID",
    "ACCOUNT_CHOOSER",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Host-GAPS",
})


def _cookie_name_set(cookies: list) -> set[str]:
    return {str(item.get("name") or "") for item in cookies if isinstance(item, dict)}


def _has_google_sso(cookies: list) -> bool:
    names = _cookie_name_set(cookies)
    if names & _GOOGLE_AUTH_COOKIE_NAMES:
        return True
    for item in cookies:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").lower()
        name = str(item.get("name") or "")
        if "google." in domain and name in _GOOGLE_AUTH_COOKIE_NAMES:
            return True
    return False


def _summarize_cookie_hosts(cookies: list) -> str:
    hosts: dict[str, int] = {}
    for item in cookies:
        if not isinstance(item, dict):
            continue
        host = str(item.get("domain") or "?").strip() or "?"
        hosts[host] = hosts.get(host, 0) + 1
    if not hosts:
        return "(none)"
    parts = [f"{host}×{count}" for host, count in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ", ".join(parts[:12])


def _warn_if_session_not_persistent(cookies: list) -> None:
    """Explain whether Microsoft KMSI or Google SSO cookies were actually saved."""
    names = _cookie_name_set(cookies)
    print(f"Saved {len(cookies)} cookies ({_summarize_cookie_hosts(cookies)}).", flush=True)
    if "ESTSAUTHPERSISTENT" in names:
        print(
            "OK: ESTSAUTHPERSISTENT found — Microsoft session can last weeks if keep-alive runs.",
            flush=True,
        )
        return
    if any(name.startswith("ESTSAUTH") for name in names):
        print(
            "WARNING: Microsoft cookies without ESTSAUTHPERSISTENT. "
            "Tick 'Keep me signed in' on a Microsoft login if you see that box.",
            flush=True,
        )
        return
    if _has_google_sso(cookies):
        print(
            "OK: Google SSO cookies found (Clarity signed in with Google).",
            flush=True,
        )
        print(
            "There is no Microsoft 'Keep me signed in' box for Google login. "
            "Install the keep-alive cron — Google still expires unused sessions.",
            flush=True,
        )
        return
    print("", flush=True)
    print(
        "WARNING: no Microsoft ESTSAUTH* and no Google SID/SAPISID cookies. "
        "Headless cron will hit the sign-in page. Stay on the Clarity dashboard "
        "with KPI numbers visible, then press ENTER again after a fresh login.",
        flush=True,
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
        text = json.dumps(payload, indent=2)
        try:
            _atomic_write_text(out_path, text)
            _propagate_clarity_session(out_path.parent, payload, out_path)
        except OSError as exc:
            print(
                f"Cannot write {out_path}: {exc}",
                file=sys.stderr,
            )
            print(
                "On the VPS, take ownership of the Clarity JSON files only "
                "(do not chmod Chrome profiles), then run this login again:",
                file=sys.stderr,
            )
            print(
                "  docker compose --profile tools exec -T -u 0 seo-vnc "
                "bash -lc 'chown $(id -u):$(id -g) /app/outputs/_sessions/clarity-*.json'",
                file=sys.stderr,
            )
            context.close()
            return 1
        print(f"Saved session to {out_path}")
        print(f"Captured dashboard URL: {url}")
        _warn_if_session_not_persistent(cookies)
        browser = getattr(context, "_ephemeral_browser", None)
        context.close()
        if browser:
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
