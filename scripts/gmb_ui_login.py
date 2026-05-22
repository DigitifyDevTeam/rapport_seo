"""Interactive login to Google Business Profile (Playwright).

Opens Chromium so you can sign in and open the Performance dashboard.
Press ENTER when Performances is visible (Vue d'ensemble, 702 interactions, …).

The script saves cookies + the best dashboard URL into a session file for
``gmb_ui_extract.py``. Valid saves include:

- ``business.google.com/...#mpd=...`` (classic GBP app)
- ``google.com/search?...#mpd=...`` (Search fiche → interactions link)
- ``google.com/search?...`` with the Performance panel open (no ``#mpd=`` yet)

Usage:
  python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-origincbd.json
  python scripts/gmb_ui_login.py --out outputs/_sessions/gmb-origincbd.json ^
      --profile outputs/_sessions/chrome-profile-gmb-origincbd
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

PERF_URL_MARKERS = ("#mpd=", "promote/performance", "/performance")
SIGNIN_MARKERS = (
    "accounts.google.com/v3/signin",
    "accounts.google.com/signin",
    "accounts.google.com/ServiceLogin",
    "accountchooser",
)


def _apply_google_compat(context) -> None:
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """
    )


def _is_signin_url(url: str) -> bool:
    url = url or ""
    return "accounts.google.com" in url and any(m in url for m in SIGNIN_MARKERS)


def _url_looks_like_performance(url: str) -> bool:
    url = url or ""
    return any(m in url for m in PERF_URL_MARKERS)


def _page_shows_performance_ui(page: Page) -> bool:
    """True when the owner Performance dashboard is visible (any host URL)."""
    checks = (
        ("text=Performances", 2_000),
        ("text=Performance", 1_500),
        ("text=Interactions avec la fiche", 1_500),
        ("text=Interactions avec les clients", 1_500),
        ("text=Vue d'ensemble", 1_500),
        ("text=Vue d’ensemble", 1_500),
        ("role=tab", 1_000),
    )
    for selector, timeout in checks:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=timeout):
                if selector.startswith("role=tab"):
                    # Tabs alone are weak; require a performance title too.
                    try:
                        if page.get_by_text("Performances", exact=False).first.is_visible(
                            timeout=800,
                        ):
                            return True
                    except Exception:
                        pass
                    continue
                return True
        except Exception:
            continue
    return False


def _find_performance_target(context: BrowserContext) -> tuple[Page | None, str, str]:
    """Return (page, url, reason) for the best open tab showing Performance."""
    pages = list(context.pages)
    if not pages:
        return None, "", "no browser tabs"

    best: tuple[Page | None, str, str] | None = None
    for page in pages:
        url = page.url or ""
        if _is_signin_url(url):
            continue
        if _url_looks_like_performance(url):
            return page, url, "URL contains performance marker (#mpd= or /performance)"
        if _page_shows_performance_ui(page):
            reason = "Performance UI visible"
            if "#mpd=" in url:
                return page, url, reason + " (#mpd= in URL)"
            if "google.com/search" in url:
                # Prefer Search+Performance over plain business.google.com list.
                if best is None or "google.com/search" not in (best[1] or ""):
                    best = (page, url, reason + " (Google Search dashboard)")
            elif best is None:
                best = (page, url, reason)

    if best:
        return best
    # Last resort: any non-sign-in tab (user may still be loading).
    for page in pages:
        url = page.url or ""
        if not _is_signin_url(url) and "business.google.com" in url:
            return page, url, "business.google.com (confirm Performance is open)"
    return None, pages[0].url if pages else "", "still on sign-in or wrong tab"


def _print_tab_status(context: BrowserContext) -> None:
    print("\n  Open tabs:")
    for i, page in enumerate(context.pages, 1):
        url = (page.url or "")[:100]
        perf = _page_shows_performance_ui(page) if not _is_signin_url(page.url or "") else False
        flag = " [Performance visible]" if perf else ""
        if _is_signin_url(page.url or ""):
            flag = " [still sign-in — finish login here]"
        print(f"    {i}. {url}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Session JSON output path")
    parser.add_argument(
        "--profile",
        default="",
        help="Persistent Chromium profile (recommended — stays logged in).",
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help="Browser channel (chrome recommended on Windows).",
    )
    parser.add_argument(
        "--start-url",
        default="https://www.google.com/search?q=Origine+CBD+Paris",
        help="Initial URL (Search fiche is often easier than business.google.com).",
    )
    parser.add_argument(
        "--location-name",
        default="",
        help="Optional text to click after load (business name).",
    )
    parser.add_argument(
        "--client-hint",
        default="",
        help="Optional client id for on-screen instructions.",
    )
    parser.add_argument(
        "--force-save",
        action="store_true",
        help="Save session from the active tab even if Performance was not detected.",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        launch_kw = dict(
            headless=False,
            channel=args.channel or None,
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        if args.profile:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(Path(args.profile).resolve()),
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
                **launch_kw,
            )
            page = context.pages[0] if context.pages else context.new_page()
            _apply_google_compat(context)
            browser = None
        else:
            browser = pw.chromium.launch(**launch_kw)
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
            )
            _apply_google_compat(context)
            page = context.new_page()

        page.goto(args.start_url, wait_until="domcontentloaded")

        if args.location_name:
            try:
                page.get_by_text(args.location_name, exact=False).first.click(timeout=5_000)
            except Exception:
                pass

        print("")
        print("Use the CHROMIUM WINDOW that Playwright opened (not another browser).")
        print("")
        print("Recommended flow (works like your screenshot):")
        print("  1) Sign in with Google + Authenticator IN THAT WINDOW.")
        print("  2) Open Google Search for the business (or business.google.com).")
        print("  3) Click « XXX interactions avec les clients » / « Performances ».")
        print("  4) Wait until you see « Performances », « Vue d'ensemble », KPIs.")
        print("  5) Press ENTER here.")
        print("")
        print("Tip: use --profile so you stay logged in next month:")
        print("  --profile outputs/_sessions/chrome-profile-gmb-origincbd")
        print("")

        perf_page: Page | None = None
        perf_url = ""
        while True:
            input("Press ENTER when Performance is visible: ")
            perf_page, perf_url, reason = _find_performance_target(context)
            _print_tab_status(context)

            if perf_page and (
                _url_looks_like_performance(perf_url)
                or _page_shows_performance_ui(perf_page)
            ):
                print(f"\n  OK — {reason}")
                break

            if args.force_save and perf_page and not _is_signin_url(perf_url):
                print(f"\n  Force-save from: {perf_url[:100]}")
                break

            if _is_signin_url(perf_url) or all(
                _is_signin_url(p.url or "") for p in context.pages
            ):
                print(
                    "\n  Still on Google SIGN-IN in the Playwright window.\n"
                    "  Complete login + MFA in THAT window, then open Performance,\n"
                    "  then press ENTER again.\n"
                    "  (If you logged in elsewhere, it does not count.)",
                )
                continue

            if perf_page and _page_shows_performance_ui(perf_page):
                print(f"\n  OK — Performance detected ({reason})")
                break

            print(
                "\n  Performance not detected yet.\n"
                "  • Click « interactions avec les clients » on the owner panel\n"
                "  • Or open business.google.com → location → Performance\n"
                "  • Make sure the Performance panel is in the Playwright window\n"
                "  • Type --force-save on the command line to save anyway\n"
                f"  • Best tab URL: {(perf_url or page.url)[:120]}",
            )

        save_page = perf_page or page
        url = save_page.url or perf_url or page.url
        # If Performance is open on Search without #mpd=, try to capture hash from link.
        if "google.com/search" in url and "#mpd=" not in url:
            try:
                link = save_page.locator('a[href*="#mpd="]').first
                href = link.get_attribute("href", timeout=3_000)
                if href and "#mpd=" in href:
                    if href.startswith("/"):
                        url = "https://www.google.com" + href
                    elif href.startswith("http"):
                        url = href
                    else:
                        base = url.split("#", 1)[0]
                        frag = href.split("#", 1)[-1]
                        url = f"{base}#{frag}" if frag.startswith("mpd=") else href
            except Exception:
                pass

        storage_state = context.storage_state()
        payload = {"url": url, "storage_state": storage_state}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved session to {out_path}")
        print(f"Captured URL: {url[:200]}")
        if "#mpd=" not in url and "google.com/search" in url:
            print(
                "Note: URL has no #mpd= — extract will reopen Search and click "
                "« interactions » using this URL + cookies.",
            )

        context.close()
        if browser is not None:
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
