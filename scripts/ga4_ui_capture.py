"""Capture GA4 home cards for the monthly SEO report (Playwright).

Uses a persistent Chrome profile (same idea as GMB). One-time login::

    python scripts/ga4_ui_prepare.py

Then every ``run_monthly`` run refreshes PNGs for the report period.

Usage::

    python scripts/ga4_ui_capture.py --client origincbd --month 2026-04
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from src.config import (
    OUTPUTS_DIR,
    PROJECT_ROOT,
    get_client,
    gmb_ui_session_path,
    resolve_google_chrome_profile,
)
from src.periods import Period
from scripts.gmb_ui_login import unlock_chrome_profile

GA4_UI_CAPTURE_VERSION = 2
FILE_MAP = {
    "visites": "ga4_card_visites_mensuelles.png",
    "country": "ga4_card_identifiant_pays.png",
}
CARD_TITLES = {
    "visites": ["Visites mensuelles", "Monthly visits", "Active users over time"],
    "country": ["Identifiant du pays", "Country ID", "Active users by Country"],
}
_REAL_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _ga4_property_id(client) -> str | None:
    from src.connectors.ga4 import _ga4_property_id_override

    property_id = (client.ga4 or {}).get("property_id")
    override = _ga4_property_id_override(client.id)
    if override:
        property_id = override
    pid = str(property_id or "").strip()
    return pid if pid.isdigit() else None


def _profile_dir(client, profile_dir: Path | None = None) -> Path:
    if profile_dir is not None and profile_dir.is_dir():
        return profile_dir
    resolved = resolve_google_chrome_profile(client)
    if resolved:
        return resolved
    sessions = PROJECT_ROOT / "outputs" / "_sessions"
    return sessions / f"chrome-profile-ga4-{client.id}"


def _docker_browser_args() -> list[str]:
    args = ["--disable-blink-features=AutomationControlled"]
    flag = (os.environ.get("SEO_REPORT_DOCKER")
            or os.environ.get("SEO_REPORT_BROWSER_NO_SANDBOX") or "")
    if flag.strip().lower() in ("1", "true", "yes", "on"):
        args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ])
    return args


def _apply_google_compat(context) -> None:
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )


def _build_home_url(property_id: str, period: Period) -> str:
    start = period.start.strftime("%Y%m%d")
    end = period.end.strftime("%Y%m%d")
    params = (
        f"_u..nav=maui&_u.dateOption=custom&_u.startDate={start}&_u.endDate={end}"
    )
    return (
        "https://analytics.google.com/analytics/web/#/p"
        f"{property_id}/reports/intelligenthome?params={params}"
    )


def _find_card_element(page, titles: list[str]):
    """Locate the GA4 report card widget (not the whole row)."""
    return page.evaluate_handle(
        """(labels) => {
          const matchesTitle = (text) => {
            const t = (text || "").replace(/\\s+/g, " ").trim();
            if (!t || t.length > 120) return false;
            return labels.some(
              (label) => t === label || t.startsWith(label) || t.includes(label),
            );
          };
          const nodes = document.querySelectorAll(
            "h2, h3, h4, [role='heading'], .card-title, .title-text",
          );
          const candidates = [];
          for (const el of nodes) {
            const own = (el.innerText || el.textContent || "").split("\\n")[0].trim();
            if (!matchesTitle(own)) continue;
            let node = el;
            for (let depth = 0; depth < 16; depth += 1) {
              if (!node.parentElement) break;
              node = node.parentElement;
              const r = node.getBoundingClientRect();
              if (r.width >= 280 && r.height >= 180 && r.bottom > 0 && r.right > 0) {
                candidates.push({ node, area: r.width * r.height });
                break;
              }
            }
          }
          if (!candidates.length) return null;
          candidates.sort((a, b) => a.area - b.area);
          return candidates[0].node;
        }""",
        titles,
    )


def _session_storage_states(client) -> list[tuple[str, dict]]:
    """Playwright storage_state dicts from GMB/GA4 session JSON exports."""
    sessions = OUTPUTS_DIR / "_sessions"
    paths: list[Path] = [
        sessions / f"ga4-{client.id}.json",
        gmb_ui_session_path(client, sessions),
        sessions / "ga4.json",
    ]
    account = (client.google_oauth_account or "").strip().lower()
    if account:
        paths.insert(0, sessions / f"ga4-{account}.json")

    found: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        state = data.get("storage_state")
        if not isinstance(state, dict) or not state.get("cookies"):
            continue
        found.append((path.name, state))
    return found


def _browser_channel() -> str | None:
    channel = (os.environ.get("SEO_REPORT_BROWSER_CHANNEL") or "chromium").strip()
    if channel.lower() in ("", "chromium", "bundled"):
        return None
    return channel


def _shot_cards_from_page(page, visites_path: Path, country_path: Path) -> tuple[bool, bool]:
    def _shot_card(titles: list[str], dest: Path) -> bool:
        handle = _find_card_element(page, titles)
        try:
            if bool(handle.evaluate("el => el == null")):
                return False
            element = handle.as_element()
            element.scroll_into_view_if_needed(timeout=15_000)
            time.sleep(0.8)
            element.screenshot(path=str(dest), timeout=30_000)
        except Exception:
            return False
        finally:
            handle.dispose()
        return dest.is_file() and dest.stat().st_size >= 800

    return (
        _shot_card(CARD_TITLES["visites"], visites_path),
        _shot_card(CARD_TITLES["country"], country_path),
    )


def _capture_with_page(page, home_url: str, *, show: bool,
                       visites_path: Path, country_path: Path) -> tuple[bool, bool]:
    print(f"[ga4-ui] {home_url}")
    docker = (os.environ.get("SEO_REPORT_DOCKER") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    wait_until = "domcontentloaded" if docker else "networkidle"
    goto_timeout = 120_000 if docker else 180_000
    page.goto(home_url, wait_until=wait_until, timeout=goto_timeout)
    time.sleep(6 if not show else 4)
    _wait_for_dashboard(page)
    time.sleep(2)
    return _shot_cards_from_page(page, visites_path, country_path)


def _wait_for_dashboard(page, timeout_ms: int = 90_000) -> None:
    labels = CARD_TITLES["visites"] + CARD_TITLES["country"]
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        url = page.url or ""
        if "accounts.google.com" in url:
            raise RuntimeError(
                "Google sign-in required — run: python scripts/ga4_ui_prepare.py"
            )
        ready = page.evaluate(
            """(ls) => {
              const body = (document.body && document.body.innerText) || "";
              return ls.some((l) => body.includes(l));
            }""",
            labels,
        )
        if ready:
            return
        time.sleep(1.5)
    raise RuntimeError("GA4 dashboard cards did not load in time")


def capture_ga4_ui(
    client_id: str,
    period: Period,
    *,
    show: bool = False,
    profile_dir: Path | None = None,
) -> Path:
    """Write PNGs + ga4_ui.json under outputs/<client>/<month>/."""
    client = get_client(client_id)
    property_id = _ga4_property_id(client)
    if not property_id:
        raise ValueError(f"No numeric GA4 property_id for client {client_id}")

    out_dir = client.output_dir / period.label
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = _profile_dir(client, profile_dir)
    home_url = _build_home_url(property_id, period)
    visites_path = out_dir / FILE_MAP["visites"]
    country_path = out_dir / FILE_MAP["country"]
    channel = _browser_channel()
    visites_ok = country_ok = False
    errors: list[str] = []

    with sync_playwright() as pw:
        for label, state in _session_storage_states(client):
            print(f"[ga4-ui] trying session cookies ({label})")
            browser = pw.chromium.launch(
                headless=not show,
                channel=channel,
                args=_docker_browser_args(),
            )
            try:
                context = browser.new_context(
                    storage_state=state,
                    viewport={"width": 1600, "height": 900},
                    locale="fr-FR",
                    user_agent=_REAL_CHROME_UA,
                    timezone_id="Europe/Paris",
                )
                _apply_google_compat(context)
                page = context.new_page()
                visites_ok, country_ok = _capture_with_page(
                    page, home_url, show=show,
                    visites_path=visites_path, country_path=country_path,
                )
                context.close()
                if visites_ok and country_ok:
                    break
            except Exception as exc:
                errors.append(f"{label}: {exc}")
            finally:
                browser.close()
            visites_ok = country_ok = False

        if not (visites_ok and country_ok) and profile.is_dir():
            print(f"[ga4-ui] Chrome profile: {profile}")
            unlock_chrome_profile(profile)
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=not show,
                channel=channel,
                viewport={"width": 1600, "height": 900},
                locale="fr-FR",
                user_agent=_REAL_CHROME_UA,
                timezone_id="Europe/Paris",
                ignore_default_args=["--enable-automation"],
                args=_docker_browser_args(),
            )
            _apply_google_compat(context)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                visites_ok, country_ok = _capture_with_page(
                    page, home_url, show=show,
                    visites_path=visites_path, country_path=country_path,
                )
            except Exception as exc:
                errors.append(f"profile: {exc}")
            context.close()

    if not (visites_ok and country_ok):
        hint = (
            f" Run once: python scripts/ga4_ui_prepare.py --client {client_id}"
        )
        if errors:
            raise RuntimeError("; ".join(errors) + hint)
        if not profile.is_dir():
            raise FileNotFoundError(
                f"No Chrome profile at {profile} and no session JSON with cookies."
                + hint
            )
        raise RuntimeError(
            "Could not capture GA4 cards « Visites mensuelles » / "
            "« Identifiant du pays » separately from the live dashboard"
        )

    charts: dict[str, str] = {}
    if visites_ok:
        charts["visites"] = str(visites_path.resolve())
    if country_ok:
        charts["country"] = str(country_path.resolve())

    payload = {
        "capture_version": GA4_UI_CAPTURE_VERSION,
        "captured_at": datetime.now().isoformat(),
        "report_month": period.label,
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "property_id": property_id,
        "url": home_url,
        "source": "playwright",
        "charts": charts,
    }
    json_path = out_dir / "ga4_ui.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[ga4-ui] wrote {json_path}")
    for key, path in charts.items():
        print(f"[ga4-ui]   {key} -> {path}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--show", action="store_true")
    parser.add_argument(
        "--profile-dir",
        default="",
        help="Chrome user-data dir (default: resolve from client GMB/GA4 sessions)",
    )
    args = parser.parse_args(argv)
    period = Period.parse(args.month)
    profile = Path(args.profile_dir) if args.profile_dir.strip() else None
    try:
        capture_ga4_ui(args.client, period, show=args.show, profile_dir=profile)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
