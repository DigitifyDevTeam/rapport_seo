"""Interactive login to Google Business Profile (Playwright).

Saves cookies + dashboard URL for ``gmb_ui_extract.py``.

**If Playwright stays on accounts.google.com/signin** (even after MFA),
Google is blocking automated browsers. Use real Chrome instead::

    .\\scripts\\gmb_login_real_chrome.ps1

Or per client::

    python scripts/clients/origincbd/gmb_ui_prepare.py

Usage:
  python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-origincbd.json
  python scripts/gmb_ui_login.py --out ... --cdp http://127.0.0.1:9222
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

PERF_URL_MARKERS = ("#mpd=", "promote/performance", "/performance")
SIGNIN_MARKERS = (
    "accounts.google.com/v3/signin",
    "accounts.google.com/signin",
    "accounts.google.com/ServiceLogin",
    "accountchooser",
    "signin/rejected",
    "signin/identifier",
)


def _apply_google_compat(context) -> None:
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """
    )


def _default_profile_for_out(out_path: Path) -> Path | None:
    name = out_path.name
    if name.startswith("gmb-") and name.endswith(".json"):
        client = name[4:-5]
        return out_path.parent / f"chrome-profile-gmb-{client}"
    return None


def _is_signin_url(url: str) -> bool:
    url = url or ""
    return "accounts.google.com" in url and any(m in url for m in SIGNIN_MARKERS)


def _url_looks_like_performance(url: str) -> bool:
    url = url or ""
    return any(m in url for m in PERF_URL_MARKERS)


def _page_shows_performance_ui(page: Page) -> bool:
    checks = (
        ("text=Performances", 2_000),
        ("text=Performance", 1_500),
        ("text=Interactions avec la fiche", 1_500),
        ("text=Interactions avec les clients", 1_500),
        ("text=Vue d'ensemble", 1_500),
        ("text=Vue d’ensemble", 1_500),
    )
    for selector, timeout in checks:
        try:
            if page.locator(selector).first.is_visible(timeout=timeout):
                return True
        except Exception:
            continue
    return False


def _find_performance_target(context: BrowserContext) -> tuple[Page | None, str, str]:
    pages = list(context.pages)
    if not pages:
        return None, "", "no browser tabs"

    best: tuple[Page | None, str, str] | None = None
    for page in pages:
        url = page.url or ""
        if _is_signin_url(url):
            continue
        if _url_looks_like_performance(url):
            return page, url, "URL contains #mpd= or /performance"
        if _page_shows_performance_ui(page):
            reason = "Performance UI visible"
            if "google.com/search" in url:
                if best is None or "google.com/search" not in (best[1] or ""):
                    best = (page, url, reason + " (Google Search)")
            elif best is None:
                best = (page, url, reason)

    if best:
        return best
    for page in pages:
        url = page.url or ""
        if not _is_signin_url(url) and ("google.com" in url or "business.google.com" in url):
            return page, url, "logged-in page (confirm Performance is open)"
    return None, pages[0].url if pages else "", "still on sign-in"


def _print_tab_status(context: BrowserContext) -> None:
    print("\n  Open tabs:")
    for i, page in enumerate(context.pages, 1):
        url = (page.url or "")[:110]
        if _is_signin_url(page.url or ""):
            flag = " [SIGN-IN — Google blocked automation; use gmb_login_real_chrome.ps1]"
        elif _page_shows_performance_ui(page):
            flag = " [Performance visible ✓]"
        else:
            flag = ""
        print(f"    {i}. {url}{flag}")


def _save_session(
    context: BrowserContext,
    save_page: Page,
    out_path: Path,
    *,
    force: bool = False,
) -> int:
    url = save_page.url or ""
    if _is_signin_url(url) and not force:
        print("\n  Refusing to save: still on Google sign-in.", file=sys.stderr)
        return 1

    if (
        not force
        and "business.google.com" in url
        and "#mpd=" not in url
        and "promote/performance" not in url
        and not _page_shows_performance_ui(save_page)
    ):
        print(
            "\n  Refusing to save: still on business.google.com/locations.\n"
            "  Open « interactions avec les clients » → Performance, then ENTER again.",
            file=sys.stderr,
        )
        return 1

    if "google.com/search" in url and "#mpd=" not in url:
        try:
            link = save_page.locator('a[href*="#mpd="]').first
            href = link.get_attribute("href", timeout=3_000)
            if href and "#mpd=" in href:
                url = href if href.startswith("http") else f"https://www.google.com{href}"
        except Exception:
            pass

    payload = {"url": url, "storage_state": context.storage_state()}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved session to {out_path}")
    print(f"Captured URL: {url[:220]}")
    return 0


def _run_cdp_mode(pw, cdp_url: str, out_path: Path, force: bool) -> int:
    print(f"\nConnecting to Chrome at {cdp_url} …")
    try:
        browser = pw.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:
        print(f"Cannot connect: {exc}", file=sys.stderr)
        print("\nStart Chrome first:")
        print("  .\\scripts\\gmb_login_real_chrome.ps1")
        return 1

    if not browser.contexts:
        print("No browser context found.", file=sys.stderr)
        return 1

    context = browser.contexts[0]
    print(f"Connected — {len(context.pages)} tab(s).")
    _print_tab_status(context)

    perf_page, perf_url, reason = _find_performance_target(context)
    if perf_page and (
        _url_looks_like_performance(perf_url)
        or _page_shows_performance_ui(perf_page)
        or not _is_signin_url(perf_url)
    ):
        print(f"\n  Saving — {reason}")
        return _save_session(context, perf_page, out_path, force=force)

    print("\n  Open Performances in Chrome, then run this command again.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Session JSON output path")
    parser.add_argument("--profile", default="", help="Persistent Chrome profile dir")
    default_channel = (os.environ.get("SEO_REPORT_BROWSER_CHANNEL") or "chrome").strip()
    parser.add_argument(
        "--channel",
        default=default_channel or "chrome",
        help="chrome | chromium | msedge",
    )
    parser.add_argument(
        "--start-url",
        default="",
        help="Initial URL (default: Google Search for --client-hint)",
    )
    parser.add_argument("--location-name", default="")
    parser.add_argument("--client-hint", default="origincbd")
    parser.add_argument(
        "--cdp",
        default="",
        help="Connect to real Chrome, e.g. http://127.0.0.1:9222 (see gmb_login_real_chrome.ps1)",
    )
    parser.add_argument("--force-save", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        if args.cdp.strip():
            return _run_cdp_mode(pw, args.cdp.strip(), out_path, args.force_save)

        profile = Path(args.profile).resolve() if args.profile else None
        if profile is None:
            profile = _default_profile_for_out(out_path)
        if profile:
            profile.mkdir(parents=True, exist_ok=True)
            print(f"Using profile: {profile}")

        launch_kw = dict(
            headless=False,
            channel=args.channel or None,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        start_url = (args.start_url or "").strip()
        if not start_url:
            start_url = "https://www.google.com/search?hl=fr&q=Origine+CBD+Paris"

        browser: Browser | None = None
        if profile:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
                **launch_kw,
            )
            page = context.pages[0] if context.pages else context.new_page()
            _apply_google_compat(context)
        else:
            print(
                "\nWARNING: No --profile. Google often blocks login.\n"
                "Prefer: python scripts/clients/origincbd/gmb_ui_prepare.py\n"
                "Or: .\\scripts\\gmb_login_real_chrome.ps1\n",
                file=sys.stderr,
            )
            browser = pw.chromium.launch(**launch_kw)
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
            )
            _apply_google_compat(context)
            page = context.new_page()

        page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)

        if args.location_name:
            try:
                page.get_by_text(args.location_name, exact=False).first.click(timeout=5_000)
            except Exception:
                pass

        print("")
        print("If this window NEVER leaves sign-in after MFA:")
        print("  → Google blocks Playwright. Press Ctrl+C and run:")
        print("  .\\scripts\\gmb_login_real_chrome.ps1")
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
                rc = _save_session(context, perf_page, out_path)
                context.close()
                if browser:
                    browser.close()
                return rc

            if args.force_save and perf_page and not _is_signin_url(perf_url):
                rc = _save_session(context, perf_page, out_path, force=True)
                context.close()
                if browser:
                    browser.close()
                return rc

            if all(_is_signin_url(p.url or "") for p in context.pages):
                print(
                    "\n  ALL tabs still on Google SIGN-IN.\n"
                    "  Playwright cannot complete Google login on your machine.\n"
                    "  Stop (Ctrl+C) and run:\n"
                    "    .\\scripts\\gmb_login_real_chrome.ps1\n",
                )
                continue

            print(
                "\n  Performance not detected. Open « interactions avec les clients »\n"
                "  in THIS window, or switch to real Chrome (script above).",
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
