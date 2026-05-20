"""Extract Google Business Profile KPIs + screenshots from business.google.com.

Flow:
1. Open Google Business Profile (saved session / optional Chrome profile).
2. Select the project/location (e.g. "Origincbd").
3. Screenshot the location overview (``gmb_business_card.png``).
4. Click "<N> interactions avec les clients" to open Performance.
5. Open the period picker, select **previous calendar month** (e.g. April
   when run in May), click **Appliquer**.
6. For each tab (Vue d'ensemble, Appels, Réservations, Itinéraire, Clics
   vers le site Web): read the headline KPI and save a chart screenshot.

Run ``gmb_ui_login.py`` first so the session has access to the account.

Outputs (alongside --out path):
- gmb_ui.json:           { captured_at, url, project, kpis, charts }
- gmb_business_card.png  (location overview)
- gmb_card_overview.png  (Vue d'ensemble)
- gmb_card_calls.png, gmb_card_bookings.png, gmb_card_directions.png,
  gmb_card_website_clicks.png
- gmb_dashboard.png      optional full-page (--screenshot)

Usage:
  python scripts/gmb_ui_extract.py ^
      --session outputs/_sessions/gmb-origincbd.json ^
      --out outputs/origincbd/2026-04/gmb_ui.json ^
      --project-name Origincbd ^
      --profile outputs/_sessions/chrome-profile-gmb ^

  DeepCleaning wrapper::

      python scripts/clients/deepcleaning/gmb_ui_extract.py 2026-04
      [--period-start 2026-04-01 --period-end 2026-04-30] ^
      [--show]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import (Frame, Page,
                                  TimeoutError as PlaywrightTimeoutError,
                                  sync_playwright)


TAB_TARGETS: list[dict[str, Any]] = [
    {"id": "overview",
     "labels": ["Vue d'ensemble", "Vue d’ensemble", "Overview"]},
    {"id": "calls",
     "labels": ["Appels", "Calls"]},
    {"id": "bookings",
     "labels": ["Réservations", "Bookings"]},
    {"id": "directions",
     "labels": ["Itinéraire", "Itinéraires", "Directions"]},
    {"id": "website_clicks",
     "labels": ["Clics vers le site Web", "Clics vers le site web",
                  "Clics vers le site", "Website clicks"]},
]

DATE_PRESET_LABELS = [
    "Mois précédent", "Mois dernier", "Le mois dernier",
    "Last month", "Previous month",
]

_FR_MONTHS = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]


def _fr_month_year(iso_date: str) -> str | None:
    if not iso_date or len(iso_date) < 7:
        return None
    try:
        year = int(iso_date[:4])
        month = int(iso_date[5:7])
        if not 1 <= month <= 12:
            return None
    except ValueError:
        return None
    return f"{_FR_MONTHS[month - 1]} {year}"


def _apply_google_compat(context) -> None:
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True,
                         help="Session JSON file from gmb_ui_login.py")
    parser.add_argument("--out", required=True,
                         help="Output JSON path (gmb_ui.json)")
    parser.add_argument("--project-name", default="",
                         help="GMB location/project label to click on "
                              "business.google.com (e.g. Origincbd).")
    parser.add_argument("--business-name", default="",
                         help="Alias for --project-name when set.")
    parser.add_argument("--location-name", default="",
                         help="Fallback for --project-name (website or id).")
    parser.add_argument("--profile", default="",
                         help="Persistent Chromium profile (recommended; "
                              "same as gmb_ui_login.py --profile).")
    parser.add_argument("--period-start", default="",
                         help="Optional YYYY-MM-DD (overrides auto month−1).")
    parser.add_argument("--period-end", default="",
                         help="Optional YYYY-MM-DD end (defaults to same month).")
    parser.add_argument("--no-auto-period", action="store_true",
                         help="Do not use month−1 auto; require --period-start.")
    parser.add_argument("--channel", default="chrome",
                         help="Browser channel (default: chrome).")
    parser.add_argument("--screenshot", default="",
                         help="Optional full-page screenshot path.")
    parser.add_argument("--show", action="store_true",
                         help="Run non-headless for debugging.")
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="Skip Google Search; open business.google.com and select project only.",
    )
    parser.add_argument(
        "--prefer-gmb-app",
        action="store_true",
        help="Try business.google.com before Google Search (Knowledge Panel).",
    )
    parser.add_argument(
        "--project-names",
        default="",
        help="Comma-separated extra location labels (aliases for --project-name).",
    )
    parser.add_argument(
        "--dashboard-url",
        default="",
        help="Open this URL directly (e.g. saved Performance dashboard from login).",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="You navigate to the Performance dashboard; press ENTER to scrape KPIs.",
    )
    parser.add_argument(
        "--manual-skip-period",
        action="store_true",
        help="With --manual: do not change the date picker (set it yourself).",
    )
    return parser.parse_args()


def _pick_dashboard_page(context, fallback: Page) -> Page:
    """Prefer the tab that already shows the GBP Performance overlay."""
    best: Page | None = None
    for candidate in context.pages:
        if not _page_alive(candidate):
            continue
        if _search_is_blocked(candidate):
            continue
        url = candidate.url or ""
        if "#mpd=" in url or "promote/performance" in url:
            return candidate
        if "business.google.com" in url:
            best = candidate
    return best if best is not None else fallback


def _persist_session(session_path: Path, context, page: Page) -> None:
    """Save cookies + current URL for the next run."""
    target = _pick_dashboard_page(context, page)
    url = ""
    if _page_alive(target):
        try:
            url = target.url
        except Exception:
            url = ""
    payload = {"url": url, "storage_state": context.storage_state()}
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log(f"session: saved {session_path} (url={url[:80]}…)" if len(url) > 80
         else f"session: saved {session_path} (url={url})")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[gmb-ui] {msg}", flush=True)


def _safe_wait_idle(page: Page, timeout: int = 15_000) -> None:
    # Swallow timeouts *and* "Target page closed" errors so the script can
    # keep running (or shut down cleanly) when the user closes the browser.
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def _page_alive(page: Page | None) -> bool:
    if page is None:
        return False
    try:
        return not page.is_closed()
    except Exception:
        return False


GMB_LOCATIONS_URL = "https://business.google.com/locations"

# -----------------------------------------------------------------------------
# Google Business Profile (business.google.com)
# -----------------------------------------------------------------------------

def _resolve_project_name(args: argparse.Namespace) -> str:
    for candidate in (args.project_name, args.business_name,
                      args.location_name):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return ""


def _project_name_candidates(args: argparse.Namespace) -> list[str]:
    """Ordered unique labels to match on business.google.com/locations."""
    names: list[str] = []
    for raw in (args.project_name, getattr(args, "project_names", "")):
        if not raw:
            continue
        for part in str(raw).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    for candidate in (args.business_name, args.location_name):
        if candidate and str(candidate).strip():
            part = str(candidate).strip()
            if part not in names:
                names.append(part)
    return names


def _search_is_blocked(page: Page) -> bool:
    url = (page.url or "").lower()
    return "google.com/sorry" in url or "/sorry/" in url


def open_gmb_app(page: Page, start_url: str = "") -> bool:
    """Navigate to Google Business Profile."""
    url = (start_url or "").strip() or GMB_LOCATIONS_URL
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        _log(f"gmb: navigation failed: {exc}")
        return False
    for label in ("Tout accepter", "Accept all", "J'accepte", "OK"):
        try:
            page.get_by_role("button", name=label).first.click(timeout=1_500)
            break
        except Exception:
            continue
    _safe_wait_idle(page, timeout=20_000)
    time.sleep(2.0)
    if "accounts.google.com/signin" in page.url:
        _log("gmb: Google sign-in required — re-run gmb_ui_login.py.")
        return False
    return True


def _try_select_project_label(page: Page, project_name: str) -> bool:
    escaped = re.escape(project_name)
    patterns = [
        re.compile(escaped, re.I),
        re.compile(rf"{escaped}.*", re.I),
    ]
    for pattern in patterns:
        try:
            loc = page.get_by_text(pattern).first
            loc.scroll_into_view_if_needed(timeout=3_000)
            loc.click(timeout=8_000)
            _log(f"project: selected {project_name!r}")
            _safe_wait_idle(page, timeout=20_000)
            time.sleep(2.0)
            return True
        except Exception:
            continue
    try:
        if page.evaluate(JS_CLICK_BY_TEXT, escaped):
            _log(f"project: selected {project_name!r} (JS)")
            _safe_wait_idle(page, timeout=20_000)
            time.sleep(2.0)
            return True
    except Exception:
        pass
    return False


JS_SELECT_BY_KEYWORDS = r"""
(keywords) => {
  const kws = (keywords || []).map(k => String(k).toLowerCase()).filter(k => k.length >= 3);
  if (!kws.length) return null;
  const nodes = document.querySelectorAll(
    'a, button, [role="row"], [role="listitem"], div, span'
  );
  for (const el of nodes) {
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 140) continue;
    const low = t.toLowerCase();
    const hits = kws.filter(k => low.includes(k)).length;
    if (hits >= Math.min(2, kws.length) || (kws.length === 1 && hits === 1)) {
      try {
        el.click();
        return t;
      } catch (e) { /* continue */ }
    }
  }
  return null;
}
"""


def select_gmb_project(page: Page, project_name: str,
                       aliases: list[str] | None = None) -> bool:
    """Click the location row/card matching ``project_name`` or an alias."""
    names: list[str] = []
    if project_name and str(project_name).strip():
        names.append(str(project_name).strip())
    for alias in aliases or []:
        alias = str(alias).strip()
        if alias and alias not in names:
            names.append(alias)
    if not names:
        return True

    for label in names:
        if _try_select_project_label(page, label):
            return True

    keywords: list[str] = []
    for label in names:
        for token in re.split(r"[\s\-_.]+", label):
            token = token.strip().lower()
            if len(token) >= 4 and token not in keywords:
                keywords.append(token)
    try:
        picked = page.evaluate(JS_SELECT_BY_KEYWORDS, keywords)
        if picked:
            _log(f"project: selected via keywords {keywords!r} -> {picked!r}")
            _safe_wait_idle(page, timeout=20_000)
            time.sleep(2.0)
            return True
    except Exception as exc:
        _log(f"project: keyword select failed: {exc}")

    _log(f"project: could not find any of {names!r} on the page.")
    return False


def screenshot_public_fiche(page: Page, out_path: Path) -> str | None:
    """Screenshot the public GBP fiche on Google Search (not the owner dashboard)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        clip = page.evaluate(KNOWLEDGE_PANEL_CLIP_JS)
    except Exception as exc:
        _log(f"public fiche: evaluate failed: {exc}")
        clip = None
    if not clip:
        _log("public fiche: knowledge panel not found on search page.")
        return None
    try:
        page.screenshot(path=str(out_path), clip=clip)
        _log(f"public fiche: saved {out_path.name}")
        return str(out_path)
    except Exception as exc:
        _log(f"public fiche: screenshot failed: {exc}")
        return None


# -----------------------------------------------------------------------------
# Google Search + Knowledge Panel (legacy fallback)
# -----------------------------------------------------------------------------

KNOWLEDGE_PANEL_CLIP_JS = r"""
() => {
  const ownerMarkers = [
    'Votre établissement sur Google',
    'interactions avec les clients',
    'Éditer la fiche',
    'Efficacité de la fiche',
    'Compléter les infos',
    'Voir les avis',
  ];
  const publicSignals = /avis Google|Magasin de|Ouvert ·|Itinéraire|Site Web/i;

  function clipFromRoot(root) {
    if (!root) return null;
    const rootRect = root.getBoundingClientRect();
    if (rootRect.width < 220 || rootRect.height < 200) return null;
    const text = (root.innerText || '');
    if (!publicSignals.test(text) && !root.querySelector('img')) return null;

    let cutY = rootRect.bottom;
    for (const el of root.querySelectorAll('*')) {
      const t = (el.innerText || '').trim();
      if (!t || t.length > 140) continue;
      for (const phrase of ownerMarkers) {
        if (t.includes(phrase)) {
          const r = el.getBoundingClientRect();
          if (r.top > rootRect.top + 100) {
            cutY = Math.min(cutY, r.top - 6);
          }
          break;
        }
      }
    }

    let topY = rootRect.top;
    for (const img of root.querySelectorAll('img')) {
      const r = img.getBoundingClientRect();
      if (r.width > 48 && r.height > 36 && r.top < cutY - 40) {
        topY = Math.min(topY, r.top);
      }
    }

    const height = cutY - topY;
    if (height < 260) return null;
    return {
      x: Math.max(0, rootRect.left),
      y: Math.max(0, topY),
      width: rootRect.width,
      height: Math.min(height, window.innerHeight - topY),
    };
  }

  const rhs = document.querySelector('#rhs');
  const rhsClip = clipFromRoot(rhs);
  if (rhsClip) return rhsClip;

  const candidates = [
    'div.kp-wholepage',
    'div[role="complementary"]',
    'div.knowledge-panel',
    'div.osrp-blk',
    '[data-attrid="kc:/local:one_line_summary"]',
  ];
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const clip = clipFromRoot(el);
    if (clip) return clip;
    const rect = el.getBoundingClientRect();
    if (rect.width > 220 && rect.height > 260) {
      return { x: Math.max(0, rect.left), y: Math.max(0, rect.top),
                width: rect.width, height: rect.height };
    }
  }
  return null;
}
"""


def open_search(page: Page, query: str) -> bool:
    if not query:
        _log("search: no business name given.")
        return False
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?hl=fr&q={encoded}"
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as exc:
        _log(f"search: navigation failed: {exc}")
        return False

    # Consent dialog (EU). Best-effort.
    for label in ("Tout accepter", "Accept all", "J'accepte"):
        try:
            page.get_by_role("button", name=label).first.click(timeout=1_500)
            break
        except Exception:
            continue

    _safe_wait_idle(page, timeout=15_000)
    time.sleep(2.5)
    if _search_is_blocked(page):
        _log("search: blocked by Google (CAPTCHA); use business.google.com fallback.")
        return False
    return True


def screenshot_knowledge_panel(page: Page, out_path: Path) -> str | None:
    """Alias for the public fiche screenshot on Google Search."""
    return screenshot_public_fiche(page, out_path)


# -----------------------------------------------------------------------------
# Click "X interactions avec les clients" in the Knowledge Panel
# -----------------------------------------------------------------------------

_JS_HELPERS_BODY = r"""
  function _gmbDeepAll(root) {
    const out = [];
    const stack = [root && (root.documentElement || root)];
    while (stack.length) {
      const node = stack.pop();
      if (!node) continue;
      out.push(node);
      if (node.shadowRoot) {
        for (const c of node.shadowRoot.children || []) stack.push(c);
      }
      for (const c of node.children || []) stack.push(c);
    }
    return out;
  }
  function _gmbNormalize(t) {
    return (t || "").replace(/\s+/g, " ").trim();
  }
  function _gmbForEachTextNode(root, fn) {
    function walk(node) {
      if (!node) return;
      if (node.nodeType === 3) {
        fn(node);
        return;
      }
      if (node.nodeType === 1) {
        const el = node;
        if (el.shadowRoot) {
          for (const c of el.shadowRoot.childNodes || []) walk(c);
        }
        for (const c of el.childNodes || []) walk(c);
      }
    }
    if (!root) return;
    if (root.nodeType === 9) {
      walk(root.documentElement);
    } else {
      walk(root);
    }
  }
"""


JS_CLICK_BY_TEXT = "((pattern) => {\n" + _JS_HELPERS_BODY + r"""
  let re;
  try {
    re = new RegExp(pattern, "i");
  } catch (e) {
    return false;
  }
  const all = _gmbDeepAll(document);
  const candidates = [];
  for (const el of all) {
    if (typeof el.click !== "function") continue;
    if (el instanceof SVGElement) continue;
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > 120) continue;
    if (!re.test(t)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    candidates.push({ el, area: rect.width * rect.height, top: rect.top });
  }
  if (!candidates.length) return false;
  candidates.sort((a, b) => a.area - b.area || a.top - b.top);
  candidates[0].el.click();
  return true;
})
"""


JS_CLICK_OWNER_INTERACTIONS = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const re = /\\d[\\d\\s\\u00A0\\u202F]*\\s*interactions?\\s+avec\\s+les\\s+clients/i;
  let best = null;
  let bestArea = Infinity;
  for (const el of document.querySelectorAll(
    'a, button, [role="link"], [role="button"], span, div')) {
    const t = _gmbNormalize(el.textContent || el.innerText || '');
    if (!re.test(t) || t.length > 120) continue;
    if (typeof el.click !== 'function') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.left > window.innerWidth * 0.58) continue;
    let node = el;
    let inOwner = false;
    for (let i = 0; i < 14 && node; i++) {
      const pt = _gmbNormalize(node.textContent || '');
      if (pt.includes('Votre établissement sur Google')
          || pt.includes('Votre etablissement sur Google')) {
        inOwner = true;
        break;
      }
      node = node.parentElement;
    }
    if (!inOwner) continue;
    const area = rect.width * rect.height;
    if (area < bestArea) {
      best = el;
      bestArea = area;
    }
  }
  if (!best) {
    for (const el of document.querySelectorAll('a, button, span, div')) {
      const t = _gmbNormalize(el.textContent || '');
      if (!re.test(t) || t.length > 120) continue;
      const rect = el.getBoundingClientRect();
      if (rect.left > window.innerWidth * 0.55 || rect.width <= 0) continue;
      if (typeof el.click !== 'function') continue;
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      el.click();
      return t;
    }
    return null;
  }
  best.scrollIntoView({ block: 'center', behavior: 'instant' });
  best.click();
  return _gmbNormalize(best.textContent || '');
})()
"""


JS_FRAME_HAS_DASHBOARD = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const all = _gmbDeepAll(document);
  const required = [
    /Vue d['\u2019]ensemble/,
    /Appels/,
    /R\u00e9servations/,
    /Itin\u00e9raire/,
    /Clics vers le site/,
  ];
  for (const el of all) {
    const t = _gmbNormalize(el.textContent);
    if (t.length < 30 || t.length > 8000) continue;
    if (required.every((re) => re.test(t))) return true;
  }
  return false;
})()
"""


def _wait_for_dashboard_frame(page: Page, attempts: int = 25) -> Frame | None:
    """Poll until the Performance iframe is available."""
    try:
        probe = page.evaluate(JS_PROBE)
        _log(f"probe: {probe}")
    except Exception as exc:
        _log(f"probe failed: {exc}")
    for _ in range(attempts):
        frame = find_dashboard_frame(page)
        if frame is not None:
            return frame
        time.sleep(1.0)
    return None


def find_dashboard_frame(page: Page) -> Frame | None:
    """Locate the iframe whose document hosts the Performance dashboard."""
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            if frame.evaluate(JS_FRAME_HAS_DASHBOARD):
                _log(f"dashboard frame: {frame.url}")
                return frame
        except Exception:
            continue
    try:
        if page.main_frame.evaluate(JS_FRAME_HAS_DASHBOARD):
            return page.main_frame
    except Exception:
        pass
    return None


def open_performance_overlay(page: Page) -> Page | None:
    """Click "X interactions avec les clients" (GBP location or Knowledge Panel).

    Returns the page where the Performance dashboard ended up — either the
    current page (overlay opened in place) or a new tab/popup Google spawned.
    Returns None if the click failed.
    """
    if _search_is_blocked(page):
        _log("overlay: skipped — page is Google CAPTCHA / sorry.")
        return None
    context = page.context

    def attempt_click() -> bool:
        on_google_search = "google.com/search" in (page.url or "")
        if on_google_search:
            try:
                page.evaluate(
                    """
                    () => {
                      const all = document.querySelectorAll('div, section');
                      for (const el of all) {
                        const t = (el.innerText || '');
                        if (t.includes('Votre établissement sur Google')
                            && t.includes('interactions avec les clients')) {
                          el.scrollIntoView({ block: 'start', behavior: 'instant' });
                          return true;
                        }
                      }
                      return false;
                    }
                    """
                )
                time.sleep(1.0)
                clicked = page.evaluate(JS_CLICK_OWNER_INTERACTIONS)
                if clicked:
                    _log(f"overlay: clicked owner panel link {clicked!r}")
                    return True
            except Exception as exc:
                _log(f"overlay: owner interactions JS failed: {exc}")
        patterns = [
            re.compile(r"\d[\d\s\u00A0]*\s*interactions?\s+avec\s+les\s+clients",
                       re.I),
            re.compile(r"interactions avec les clients", re.I),
        ]
        if not on_google_search:
            patterns.extend([
                re.compile(r"Performances?", re.I),
                re.compile(r"Statistiques", re.I),
            ])
        for pattern in patterns:
            try:
                locator = page.get_by_text(pattern).first
                locator.scroll_into_view_if_needed(timeout=2_000)
                locator.click(timeout=4_000)
                _log(f"overlay: clicked element matching {pattern.pattern!r}")
                return True
            except Exception:
                continue
        button_labels = ["Interactions avec les clients"]
        if not on_google_search:
            button_labels.extend(["Performances", "Statistiques"])
        for label in button_labels:
            try:
                page.get_by_role("button", name=label,
                                    exact=False).first.click(timeout=3_000)
                _log(f"overlay: clicked button '{label}'")
                return True
            except Exception:
                continue
        return False

    def _wait_performance_ready(target: Page) -> None:
        for _ in range(40):
            if not _page_alive(target):
                return
            try:
                url = target.url or ""
            except Exception:
                url = ""
            if "#mpd=" in url or "promote/performance" in url:
                _log(f"overlay: performance ready ({url[:90]}…)")
                return
            try:
                if target.main_frame.evaluate(JS_FRAME_HAS_DASHBOARD):
                    _log("overlay: performance tabs visible in page")
                    return
            except Exception:
                pass
            time.sleep(1.0)
        _log("overlay: still waiting for performance shell (continuing).")

    pages_before = set(context.pages)
    new_page: Page | None = None
    try:
        with context.expect_page(timeout=10_000) as info:
            if not attempt_click():
                try:
                    link = page.locator(
                        "a, button, span, div",
                    ).filter(has_text=re.compile(
                        r"interactions?\s+avec\s+les\s+clients", re.I,
                    )).first
                    link.scroll_into_view_if_needed(timeout=5_000)
                    link.click(timeout=8_000, force=True)
                    _log("overlay: clicked interactions link (fallback locator).")
                except Exception:
                    _log("overlay: could not click the entry link.")
                    return None
        new_page = info.value
    except PlaywrightTimeoutError:
        new_page = None
    except Exception as exc:
        _log(f"overlay: unexpected error during click: {exc}")
        return None

    if new_page is not None and _page_alive(new_page):
        _log(f"overlay: opened in new tab -> {new_page.url}")
        _wait_performance_ready(new_page)
        _safe_wait_idle(new_page, timeout=25_000)
        time.sleep(2.0)
        return new_page

    # No popup -- the dashboard probably rendered in place as a modal.
    if not _page_alive(page):
        _log("overlay: original page closed; aborting.")
        return None
    _wait_performance_ready(page)
    _safe_wait_idle(page, timeout=20_000)
    time.sleep(2.0)
    new_pages = [p for p in context.pages if p not in pages_before]
    if new_pages and _page_alive(new_pages[-1]):
        target = new_pages[-1]
        _log(f"overlay: detected new tab after click -> {target.url}")
        _wait_performance_ready(target)
        _safe_wait_idle(target, timeout=20_000)
        time.sleep(2.0)
        return target
    _log(f"overlay: dashboard assumed in current page; url={page.url}")
    return page


# -----------------------------------------------------------------------------
# Select date range in the Performance overlay
# -----------------------------------------------------------------------------


JS_FIND_MODAL = "(() => {\n" + _JS_HELPERS_BODY + r"""
  function tagAndReturn(el) {
    const r = el.getBoundingClientRect();
    el.setAttribute("data-gmb-modal", "1");
    return { x: r.left, y: r.top, width: r.width, height: r.height };
  }

  const all = _gmbDeepAll(document);

  for (const el of all) {
    if (!el.getAttribute) continue;
    const role = el.getAttribute("role");
    const tag = (el.tagName || "").toLowerCase();
    if (role !== "dialog" && tag !== "dialog") continue;
    const r = el.getBoundingClientRect();
    if (r.width > 400 && r.height > 250) {
      return tagAndReturn(el);
    }
  }

  const required = [
    /Vue d['\u2019]ensemble/,
    /Appels/,
    /R\u00e9servations/,
    /Itin\u00e9raire/,
    /Clics vers le site/,
  ];
  let best = null;
  for (const el of all) {
    const rect = el.getBoundingClientRect();
    if (rect.width < 600 || rect.height < 300) continue;
    if (rect.top > window.innerHeight) continue;
    const txt = _gmbNormalize(el.textContent);
    if (txt.length > 8000) continue;
    if (!required.every((re) => re.test(txt))) continue;
    const area = rect.width * rect.height;
    if (!best || area < best.area) best = { el, area };
  }
  if (best) return tagAndReturn(best.el);

  return null;
})()
"""


JS_PROBE = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const all = _gmbDeepAll(document);
  let shadowRoots = 0;
  let perfHits = 0;
  let tabHits = 0;
  let dialogs = 0;
  const dialogSamples = [];
  for (const el of all) {
    if (el.shadowRoot) shadowRoots += 1;
    if (!el.textContent) continue;
    const t = _gmbNormalize(el.textContent);
    if (/Performances?/.test(t) && t.length < 30) perfHits += 1;
    if (/Vue d['\u2019]ensemble/.test(t) && t.length < 30) tabHits += 1;
    const role = el.getAttribute && el.getAttribute("role");
    const tag = (el.tagName || "").toLowerCase();
    if (role === "dialog" || tag === "dialog") {
      dialogs += 1;
      if (dialogSamples.length < 3) {
        const r = el.getBoundingClientRect();
        dialogSamples.push({
          tag, role,
          rect: { x: r.left, y: r.top, w: r.width, h: r.height },
        });
      }
    }
  }
  return {
    elementCount: all.length,
    shadowRoots,
    perfHits,
    tabHits,
    dialogs,
    dialogSamples,
    iframeCount: document.querySelectorAll('iframe').length,
  };
})()
"""


JS_CLICK_IN_MODAL = "((labels) => {\n" + _JS_HELPERS_BODY + r"""
  const tagged = document.querySelector('[data-gmb-modal="1"]');
  const all = tagged
    ? _gmbDeepAll(tagged)
    : _gmbDeepAll(document);
  const candidates = [];
  for (const el of all) {
    if (typeof el.click !== "function") continue;
    if (el instanceof SVGElement) continue;
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > 80) continue;
    if (!labels.some((l) => t === l)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.width > 360 || rect.height > 80) continue;
    candidates.push({ el, area: rect.width * rect.height });
  }
  if (!candidates.length) return false;
  candidates.sort((a, b) => a.area - b.area);
  candidates[0].el.click();
  return true;
})
"""


# Same shape as JS_CLICK_IN_MODAL, but ignores the modal scope. Useful for
# elements that mount outside the modal (e.g. dropdown menus on Material).
# Filters out SVG nodes (their text labels match too but they cannot be
# clicked through the HTMLElement.click() API).
JS_CLICK_ANYWHERE = "((labels) => {\n" + _JS_HELPERS_BODY + r"""
  const all = _gmbDeepAll(document);
  const candidates = [];
  for (const el of all) {
    if (typeof el.click !== "function") continue;
    if (el instanceof SVGElement) continue;
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > 80) continue;
    if (!labels.some((l) => t === l)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.width > 380 || rect.height > 80) continue;
    candidates.push({ el, area: rect.width * rect.height });
  }
  if (!candidates.length) return false;
  candidates.sort((a, b) => a.area - b.area);
  candidates[0].el.click();
  return true;
})
"""


JS_FIND_DATE_BUTTON = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const tagged = document.querySelector('[data-gmb-modal="1"]');
  const all = tagged
    ? _gmbDeepAll(tagged)
    : _gmbDeepAll(document);
  // Match the dropdown button which shows a *range* like
  // "déc. 2025 - mai 2026". Chart x-axis labels are single months only
  // so they won't match this stricter pattern.
  const month = "(?:janv\\.|f\\u00e9vr\\.|mars|avr\\.|mai|juin|juil\\.|ao\\u00fbt|sept\\.|oct\\.|nov\\.|d\\u00e9c\\.)";
  const rangeRe = new RegExp(
    month + "\\s*\\d{4}\\s*[\\-\\u2013\\u2014\\u2212]\\s*" + month + "\\s*\\d{4}",
    "i",
  );
  let best = null;
  for (const el of all) {
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > 80) continue;
    if (!rangeRe.test(t)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.width > 520 || rect.height > 80) continue;
    if (!best || (rect.width * rect.height) < best.area) {
      best = { el, area: rect.width * rect.height };
    }
  }
  if (!best) return false;
  best.el.click();
  return true;
})()
"""


def _safe_wait_idle_target(target: Page | Frame, timeout: int = 15_000) -> None:
    try:
        target.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


JS_LIST_MENUITEMS = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const all = _gmbDeepAll(document);
  const items = [];
  for (const el of all) {
    const role = el.getAttribute && el.getAttribute("role");
    const tag = (el.tagName || "").toLowerCase();
    const interactive = (role === "menuitem" || role === "option"
                            || role === "radio" || tag === "li"
                            || tag === "button");
    if (!interactive) continue;
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > 60) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.width > 360) continue;
    items.push({ role: role || tag, text: t,
                  w: Math.round(rect.width), h: Math.round(rect.height) });
  }
  return items.slice(0, 40);
})()
"""


def _open_date_dropdown(target: Page | Frame) -> bool:
    try:
        opened = target.evaluate(JS_FIND_DATE_BUTTON)
    except Exception as exc:
        _log(f"date range: evaluate failed: {exc}")
        return False
    if not opened:
        _log("date range: could not open the dropdown.")
        return False
    time.sleep(1.2)
    return True


def select_previous_month_preset(target: Page | Frame) -> bool:
    """Pick Google's built-in previous-month preset (current month − 1)."""
    if not _open_date_dropdown(target):
        return False
    for preset in DATE_PRESET_LABELS:
        try:
            if not target.evaluate(JS_CLICK_ANYWHERE, [preset]):
                continue
            time.sleep(0.5)
            if target.evaluate(JS_CLICK_ANYWHERE,
                              ["Appliquer", "Apply", "OK"]):
                _log(f"date range: applied preset {preset!r} (month − 1).")
                time.sleep(3.0)
                _safe_wait_idle_target(target, timeout=8_000)
                return True
        except Exception as exc:
            _log(f"date range: preset {preset!r} failed: {exc}")
    return False


def select_date_range(target: Page | Frame, period_start: str,
                       period_end: str) -> bool:
    """Open the GBP date dropdown and pick the single month that contains
    ``period_start``.

    Google's picker is a two-click range selector with month buttons
    ("avr. 2026", "mai 2026", ...) and an "Appliquer" confirm button. To get
    a single month we click the same button twice (start = end = target
    month), then "Appliquer".
    """
    start_label = _fr_month_year(period_start)
    end_label = _fr_month_year(period_end) or start_label
    if not start_label:
        _log("date range: no valid period dates supplied; skipping.")
        return False

    if not _open_date_dropdown(target):
        return False

    _log(f"date range: setting range to {start_label} -> {end_label}.")
    try:
        # First click resets any in-progress selection and sets the start.
        if not target.evaluate(JS_CLICK_ANYWHERE, [start_label]):
            _log(f"date range: start month {start_label!r} not found.")
            return False
        time.sleep(0.6)
        # Second click sets the end of the range. When start_label ==
        # end_label this yields a single-month selection.
        if not target.evaluate(JS_CLICK_ANYWHERE, [end_label]):
            _log(f"date range: end month {end_label!r} not found.")
            return False
        time.sleep(0.6)
        if not target.evaluate(JS_CLICK_ANYWHERE,
                                  ["Appliquer", "Apply", "OK"]):
            _log("date range: 'Appliquer' button not found.")
            return False
    except Exception as exc:
        _log(f"date range: month-picker click failed: {exc}")
        return False

    _log(f"date range: applied {start_label} -> {end_label}.")
    time.sleep(3.0)
    _safe_wait_idle_target(target, timeout=8_000)
    return True


def select_reporting_period(target: Page | Frame, period_start: str,
                             period_end: str, *, auto_previous: bool) -> bool:
    """Apply the reporting month to the Performance date picker."""
    if auto_previous:
        _log("date range: auto mode — current calendar month − 1.")
        if select_previous_month_preset(target):
            return True
        start, end = _default_period()
        _log(f"date range: preset unavailable; using {start[:7]}.")
        return select_date_range(target, start, end)
    if not period_start:
        start, end = _default_period()
        return select_reporting_period(target, start, end, auto_previous=True)
    return select_date_range(target, period_start, period_end)


def _normalize_kpi_digits(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw).replace("\u202f", "").replace("\xa0", ""))
    if not digits:
        return None
    try:
        n = int(digits)
    except ValueError:
        return None
    if n > 50_000_000:
        return None
    return f"{n:,}".replace(",", " ")


JS_EXTRACT_HEADLINE_FROM_TEXT = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const root = document.querySelector('[data-gmb-modal="1"]')
    || document.body
    || document.documentElement;
  const lines = (root.innerText || '')
    .split('\n')
    .map((l) => _gmbNormalize(l))
    .filter(Boolean);
  const numRe = /^-?\d[\d\s\u00A0\u202F.,]*$/;
  for (let i = 0; i < Math.min(lines.length, 40); i++) {
    const line = lines[i];
    if (!numRe.test(line)) continue;
    const digits = line.replace(/[^\d]/g, '');
    if (!digits || digits.length > 7) continue;
    const n = parseInt(digits, 10);
    if (n > 50000000) continue;
    const next = (lines[i + 1] || '').toLowerCase();
    if (next.includes('interactions') || next.includes('appels')
        || next.includes('réservation') || next.includes('reservation')
        || next.includes('itinéraire') || next.includes('itineraire')
        || next.includes('clics vers le site') || next.includes('website')) {
      return line;
    }
    if (i < 15) return line;
  }
  return null;
})()
"""


def extract_headline_kpi(target: Page | Frame) -> str | None:
    """Read the large headline total from the Performance panel."""
    for _ in range(3):
        try:
            raw = target.evaluate(JS_EXTRACT_HEADLINE_FROM_TEXT)
            value = _normalize_kpi_digits(raw)
            if value:
                return value
        except Exception:
            pass
        try:
            raw = target.evaluate(JS_EXTRACT_BIG_NUMBER_IN_MODAL)
            value = _normalize_kpi_digits(raw)
            if value:
                return value
        except Exception:
            pass
        try:
            raw = target.evaluate(EXTRACT_BIG_NUMBER_JS)
            value = _normalize_kpi_digits(raw)
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.8)
    return None


# -----------------------------------------------------------------------------
# Click a tab + extract KPI + screenshot
# -----------------------------------------------------------------------------

EXTRACT_BIG_NUMBER_JS = r"""
() => {
  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }
  function isNumberLike(t) {
    return /^-?\d[\d\s\u00A0\u202F.,]*\s*(%|k|K|m|M)?$/u.test(t);
  }
  const seen = [];
  const all = document.querySelectorAll("*");
  for (const el of all) {
    const t = normalize(el.textContent);
    if (!t || t.length > 24) continue;
    if (!isNumberLike(t)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.top < 0 || rect.top > window.innerHeight) continue;
    const style = window.getComputedStyle(el);
    const size = parseFloat(style.fontSize || "0");
    if (size < 18) continue;
    seen.push({ text: t, size, top: rect.top });
  }
  if (!seen.length) return null;
  seen.sort((a, b) => b.size - a.size || a.top - b.top);
  return seen[0].text;
}
"""


CONTENT_REGION_CLIP_JS = r"""
() => {
  const containers = document.querySelectorAll('div, section, main');
  let best = null;
  for (const el of containers) {
    const hasViz = el.querySelector('svg, canvas');
    if (!hasViz) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 460 || rect.height < 220) continue;
    if (rect.top < 0 || rect.top > window.innerHeight) continue;
    const area = rect.width * rect.height;
    if (!best || area > best.area) {
      best = { area,
                rect: { x: rect.left, y: rect.top,
                        width: rect.width, height: rect.height } };
    }
  }
  if (!best) return null;
  const padding = 10;
  return {
    x: Math.max(0, best.rect.x - padding),
    y: Math.max(0, best.rect.y - padding),
    width: Math.min(window.innerWidth, best.rect.width + 2 * padding),
    height: Math.min(window.innerHeight, best.rect.height + 2 * padding),
  };
}
"""


JS_EXTRACT_BIG_NUMBER_IN_MODAL = "(() => {\n" + _JS_HELPERS_BODY + r"""
  const tagged = document.querySelector('[data-gmb-modal="1"]');
  const modalRoot = tagged || document.body || document.documentElement;
  const scope = tagged ? _gmbDeepAll(tagged) : _gmbDeepAll(document);

  function isNumberLike(t) {
    // Match digits with optional French/English spacers (non-breaking spaces),
    // dots, commas, and common KPI suffixes.
    return /^-?\\s*\\d[\\d\\s\\u00A0\u202F.,]*\\s*(%|k|K|m|M)?$/u.test(t);
  }
  function visible(el) {
    if (!el || el.nodeType !== 1) return false;
    const st = window.getComputedStyle(el);
    if (st.visibility === "hidden" || st.display === "none"
        || parseFloat(st.opacity || "1") < 0.05) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
  }
  function effectiveFontSize(el) {
    let e = el;
    for (let i = 0; i < 10 && e; i++) {
      const s = parseFloat(window.getComputedStyle(e).fontSize || "0");
      if (s >= 10) return s;
      e = e.parentElement;
    }
    return parseFloat(window.getComputedStyle(el).fontSize || "0") || 0;
  }
  function scoreCandidate(size, top) {
    // Give a massive boost to elements that are higher up on the screen (KPIs are usually headers)
    let s = size * 1000 - top * 1.5;
    if (top > window.innerHeight * 0.4) s *= 0.5;
    return s;
  }

  const seen = [];
  const maxTok = 36;

  for (const el of scope) {
    if (!el || el.nodeType !== 1) continue;
    if (!visible(el)) continue;
    const t = _gmbNormalize(el.textContent);
    if (!t || t.length > maxTok) continue;
    if (!isNumberLike(t)) continue;
    const rect = el.getBoundingClientRect();
    const size = effectiveFontSize(el);
    if (size < 9.5 && rect.height < 8) continue;
    seen.push({
      text: t,
      score: scoreCandidate(size, rect.top),
    });
  }

  _gmbForEachTextNode(modalRoot, (tn) => {
    const raw = _gmbNormalize(tn.nodeValue);
    if (!raw || raw.length > maxTok) return;
    if (!isNumberLike(raw)) return;
    const el = tn.parentElement;
    if (!el || !visible(el)) return;
    const rect = el.getBoundingClientRect();
    const size = effectiveFontSize(el);
    if (size < 9.5) return;
    seen.push({
      text: raw,
      score: scoreCandidate(size, rect.top) + 15,
    });
  });

  if (!seen.length) {
    const upper = window.innerHeight * 0.58;
    _gmbForEachTextNode(modalRoot, (tn) => {
      const raw = _gmbNormalize(tn.nodeValue);
      if (!raw || raw.length > maxTok) return;
      if (!isNumberLike(raw)) return;
      const el = tn.parentElement;
      if (!el || !visible(el)) return;
      const rect = el.getBoundingClientRect();
      if (rect.top > upper) return;
      const size = effectiveFontSize(el);
      if (size < 8.5) return;
      seen.push({
        text: raw,
        score: scoreCandidate(size, rect.top) + 8,
      });
    });
    for (const el of scope) {
      if (!el || el.nodeType !== 1) continue;
      if (!visible(el)) continue;
      const t = _gmbNormalize(el.textContent);
      if (!t || t.length > maxTok) continue;
      if (!isNumberLike(t)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.top > upper) continue;
      const size = effectiveFontSize(el);
      if (size < 8.5 && rect.height < 10) continue;
      seen.push({
        text: t,
        score: scoreCandidate(size, rect.top),
      });
    }
  }

  if (!seen.length) return null;
  seen.sort((a, b) => b.score - a.score);
  return seen[0].text;
})()
"""


JS_TAG_MODAL_CONTENT = r"""
(() => {
  const modal = document.querySelector('[data-gmb-modal="1"]');
  if (!modal) return false;
  modal.setAttribute('data-gmb-capture', '1');
  return true;
})()
"""


def _ocr_headline_from_saved_png(path: Path) -> str | None:
    """Read the big KPI digit from a saved card screenshot (optional Tesseract)."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from src.reporting.gmb_card_ocr import headline_int_from_chart_png
    except ImportError:
        return None
    return headline_int_from_chart_png(path)


def click_tab(target: Page | Frame, labels: list[str]) -> bool:
    try:
        return bool(target.evaluate(JS_CLICK_IN_MODAL, labels))
    except Exception as exc:
        _log(f"tab click: evaluate failed: {exc}")
        return False


def _owner_page(target: Page | Frame) -> Page:
    if isinstance(target, Frame):
        return target.page
    return target


def _screenshot_performance_card(target: Page | Frame, out_path: Path) -> bool:
    """Save the chart card PNG (Playwright ElementHandle has no ``clip`` arg)."""
    page = _owner_page(target)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    clip: dict[str, float] | None = None
    try:
        clip = target.evaluate(CONTENT_REGION_CLIP_JS)
    except Exception:
        clip = None

    if clip:
        try:
            if isinstance(target, Frame):
                frame_box = target.frame_element().bounding_box()
                if frame_box:
                    abs_clip = {
                        "x": frame_box["x"] + clip["x"],
                        "y": frame_box["y"] + clip["y"],
                        "width": clip["width"],
                        "height": clip["height"],
                    }
                    page.screenshot(path=str(out_path), clip=abs_clip,
                                    timeout=15_000)
                    return out_path.is_file()
            page.screenshot(path=str(out_path), clip=clip, timeout=15_000)
            return out_path.is_file()
        except Exception as exc:
            _log(f"screenshot: page clip failed: {exc}")

    try:
        if target.evaluate(JS_TAG_MODAL_CONTENT):
            target.locator('[data-gmb-capture="1"]').first.screenshot(
                path=str(out_path), timeout=15_000,
            )
            if out_path.is_file():
                return True
    except Exception as exc:
        _log(f"screenshot: modal content failed: {exc}")

    try:
        target.evaluate(JS_FIND_MODAL)
        target.locator('[data-gmb-modal="1"]').first.screenshot(
            path=str(out_path), timeout=15_000,
        )
        if out_path.is_file():
            return True
    except Exception as exc:
        _log(f"screenshot: modal panel failed: {exc}")

    try:
        if isinstance(target, Frame):
            target.frame_element().screenshot(path=str(out_path), timeout=15_000)
        else:
            page.screenshot(path=str(out_path), full_page=False, timeout=15_000)
        return out_path.is_file()
    except Exception as exc:
        _log(f"screenshot: fallback failed: {exc}")
        return False


def capture_tab(target: Page | Frame, tab: dict[str, Any],
                 out_dir: Path) -> tuple[str | None, str | None]:
    try:
        target.evaluate(JS_FIND_MODAL)
    except Exception:
        pass
    if not click_tab(target, tab["labels"]):
        _log(f"tab '{tab['id']}': could not click.")
        return None, None
    time.sleep(2.5)
    _safe_wait_idle_target(target, timeout=10_000)
    time.sleep(1.0)
    try:
        target.evaluate(JS_FIND_MODAL)
    except Exception:
        pass

    value = extract_headline_kpi(target)

    chart_path: str | None = None
    outfile = out_dir / f"gmb_card_{tab['id']}.png"
    if _screenshot_performance_card(target, outfile):
        chart_path = str(outfile)

    if value is None:
        value = extract_headline_kpi(target)

    if value is None and chart_path:
        png = Path(chart_path)
        if png.is_file():
            ocr_val = _ocr_headline_from_saved_png(png)
            if ocr_val is not None:
                value = ocr_val

    _log(f"tab '{tab['id']}': value={value!r} chart={chart_path or '<none>'}")
    return value, chart_path


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------

def _default_query(business_name: str, location_name: str) -> str:
    if business_name:
        return business_name
    if location_name:
        return location_name
    return ""


def _default_period() -> tuple[str, str]:
    """Previous calendar month (start + end dates for the month picker)."""
    today = date.today()
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1
    start = f"{prev_year:04d}-{prev_month:02d}-01"
    if prev_month == 12:
        next_year, next_month = prev_year + 1, 1
    else:
        next_year, next_month = prev_year, prev_month + 1
    last_day = date(next_year, next_month, 1) - timedelta(days=1)
    return start, last_day.isoformat()


def _launch_browser_context(pw, args: argparse.Namespace,
                             storage_state: Any | None):
    """Return (context, browser_or_none, page)."""
    launch_kw = dict(
        headless=not args.show,
        channel=args.channel or None,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )
    viewport = {"width": 1600, "height": 900}
    if args.profile:
        profile_dir = Path(args.profile).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            locale="fr-FR",
            viewport=viewport,
            **launch_kw,
        )
        _apply_google_compat(context)
        page = context.pages[0] if context.pages else context.new_page()
        return context, None, page
    browser = pw.chromium.launch(**launch_kw)
    ctx_kw: dict[str, Any] = dict(viewport=viewport, locale="fr-FR")
    if storage_state:
        ctx_kw["storage_state"] = storage_state
    context = browser.new_context(**ctx_kw)
    _apply_google_compat(context)
    page = context.new_page()
    return context, browser, page


def main() -> int:
    args = _parse_args()
    session_path = Path(args.session).resolve()
    out_path = Path(args.out).resolve()
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    storage_state: Any | None = None
    saved_url = ""
    if session_path.exists():
        raw = json.loads(session_path.read_text(encoding="utf-8"))
        storage_state = raw.get("storage_state")
        saved_url = str(raw.get("url") or "")
    if not args.profile and not storage_state:
        raise SystemExit(
            "Session file is missing storage_state and no --profile given. "
            "Re-run gmb_ui_login.py."
        )

    auto_period = not args.no_auto_period and not args.period_start
    period_start = args.period_start
    period_end = args.period_end
    if auto_period:
        period_start, period_end = _default_period()
    elif not period_start:
        period_start, period_end = _default_period()
    elif not period_end:
        period_end = period_start

    project_name = _resolve_project_name(args)
    project_aliases = _project_name_candidates(args)
    primary = project_name or (project_aliases[0] if project_aliases else "")
    alias_only = [a for a in project_aliases if a != primary]

    kpis: dict[str, dict[str, str | None]] = {}
    charts: dict[str, str | None] = {}

    with sync_playwright() as pw:
        context, browser, page = _launch_browser_context(pw, args, storage_state)

        if args.manual:
            dash_url = (args.dashboard_url or "").strip() or saved_url
            start_url = dash_url or GMB_LOCATIONS_URL
            if not _page_alive(page):
                page = context.new_page()
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                _log(f"manual: navigation failed: {exc}")
            _safe_wait_idle(page, timeout=20_000)
            time.sleep(1.5)
            print("")
            print("=== GMB manual capture ===")
            print("In the opened browser (same Google account as Origincbd):")
            print("  1) Open the DeepCleaning location / fiche.")
            print("  2) Open Performance (Interactions avec les clients).")
            print("  3) Set the report period in the date picker.")
            print("     Example for 2026-04 report: 25/03/2026 – 25/04/2026.")
            print("  4) Wait until KPI numbers are visible on screen.")
            print("Optional: open the public Google Search fiche in another tab")
            print("for the overview screenshot (business_card).")
            print("")
            print("When ready, return here and press ENTER to capture KPIs + PNGs.")
            print("")
            input()
            _persist_session(session_path, context, page)
            dashboard_page = _pick_dashboard_page(context, page)
            business_card_out = out_dir / "gmb_business_card.png"
            charts: dict[str, str | None] = {}
            kpis: dict[str, dict[str, str | None]] = {}
            for tab_page in context.pages:
                if _search_is_blocked(tab_page):
                    continue
                url = tab_page.url or ""
                if "google.com/search" in url and "sorry" not in url:
                    shot = screenshot_public_fiche(tab_page, business_card_out)
                    if shot:
                        charts["business_card"] = shot
                        break
            dashboard_frame: Frame | None = None
            if _page_alive(dashboard_page):
                dashboard_frame = _wait_for_dashboard_frame(dashboard_page)
            if dashboard_frame is None:
                _log("manual: Performance frame not found — check the open tab.")
            elif not args.manual_skip_period:
                select_reporting_period(
                    dashboard_frame, period_start, period_end,
                    auto_previous=False,
                )
            else:
                _log("manual: keeping your date range (--manual-skip-period).")
            if dashboard_frame is not None:
                for tab in TAB_TARGETS:
                    value, chart = capture_tab(dashboard_frame, tab, out_dir)
                    kpis[tab["id"]] = {"value": value}
                    charts[tab["id"]] = chart
            if args.screenshot and _page_alive(dashboard_page):
                try:
                    dashboard_page.screenshot(
                        path=str(Path(args.screenshot).resolve()),
                        full_page=True,
                    )
                except Exception:
                    pass
            final_url = dashboard_page.url if _page_alive(dashboard_page) else ""
            payload = {
                "captured_at": _now_iso(),
                "url": final_url,
                "project": project_name,
                "query": project_name,
                "period_start": period_start,
                "period_end": period_end,
                "kpis": kpis,
                "charts": charts,
            }
            if not kpis and out_path.exists():
                _log("manual: empty kpis; preserving previous gmb_ui.json")
            else:
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Wrote {out_path}")
            for key, info in kpis.items():
                value = info.get("value") if isinstance(info, dict) else None
                print(f"  KPI {key}: {value or '<not found>'}")
            for key, value in charts.items():
                print(f"  CARD {key}: {value or '<not found>'}")
            try:
                context.close()
            except Exception:
                pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            return 0

        business_card_out = out_dir / "gmb_business_card.png"
        search_query = "" if args.no_search else (
            _default_query(args.business_name, args.location_name)
            or project_name
        )
        dashboard_page: Page | None = None
        dashboard_frame: Frame | None = None
        dash_url = (args.dashboard_url or "").strip() or saved_url

        def _capture_from_gmb_app() -> Page | None:
            if not open_gmb_app(page, dash_url):
                return None
            if primary or alias_only:
                select_gmb_project(page, primary, alias_only)
            # Origincbd uses Google Search for the public fiche; --no-search clients
            # stay on business.google.com only (avoids CAPTCHA on a second Search).
            if not args.no_search:
                if not charts.get("business_card") and search_query:
                    if open_search(page, search_query) and not _search_is_blocked(page):
                        charts["business_card"] = screenshot_public_fiche(
                            page, business_card_out,
                        )
                if charts.get("business_card") is None:
                    charts["business_card"] = screenshot_public_fiche(
                        page, business_card_out,
                    )
            return open_performance_overlay(page)

        # 0) Direct Performance / Knowledge Panel URL saved at login.
        if dash_url and "google.com/search" in dash_url and "#mpd=" in dash_url:
            try:
                page.goto(dash_url, wait_until="domcontentloaded", timeout=60_000)
                _safe_wait_idle(page, timeout=25_000)
                time.sleep(2.0)
                if not _search_is_blocked(page):
                    charts["business_card"] = screenshot_public_fiche(
                        page, business_card_out,
                    )
                    dashboard_page = open_performance_overlay(page)
                    if dashboard_page is None and "#mpd=" in page.url:
                        dashboard_page = page
            except Exception as exc:
                _log(f"dashboard-url: navigation failed: {exc}")

        # A) business.google.com first (when configured).
        if dashboard_page is None and args.prefer_gmb_app:
            dashboard_page = _capture_from_gmb_app()

        # B) Google Search → fiche screenshot → « X interactions » (Origincbd).
        if dashboard_page is None and search_query and open_search(page, search_query):
            _log("search: capturing public fiche (right panel) before Performance.")
            charts["business_card"] = screenshot_public_fiche(
                page, business_card_out,
            )
            dashboard_page = open_performance_overlay(page)

        # C) Fallback: business.google.com.
        if dashboard_page is None and not args.prefer_gmb_app:
            dashboard_page = _capture_from_gmb_app()

        if dashboard_page is not None and _page_alive(dashboard_page):
            dashboard_frame = _wait_for_dashboard_frame(dashboard_page)

        if dashboard_frame is None:
            _log("dashboard frame: not found; aborting Performance capture.")
        if dashboard_frame is not None and dashboard_page is not None:
            try:
                modal_rect = dashboard_frame.evaluate(JS_FIND_MODAL)
                if modal_rect:
                    _log(f"modal: tagged inside frame at {modal_rect}")
            except Exception as exc:
                _log(f"modal: locate inside frame failed: {exc}")
            try:
                handle = dashboard_frame.frame_element()
                box = handle.bounding_box()
                if box:
                    dashboard_page.screenshot(
                        path=str(out_dir / "gmb_modal_debug.png"),
                        clip=box,
                    )
            except Exception as exc:
                _log(f"modal: debug screenshot failed: {exc}")

        # 4) Date range (auto: Mois précédent = today’s month − 1).
        if dashboard_frame is not None:
            select_reporting_period(
                dashboard_frame, period_start, period_end,
                auto_previous=auto_period,
            )

        # 5) Loop the tabs.
        if dashboard_frame is not None:
            for tab in TAB_TARGETS:
                value, chart = capture_tab(dashboard_frame, tab, out_dir)
                kpis[tab["id"]] = {"value": value}
                charts[tab["id"]] = chart

        # OCR fallback on saved card PNGs (needs Tesseract).
        if dashboard_frame is not None:
            root = Path(__file__).resolve().parents[1]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                from src.reporting.gmb_card_ocr import (
                    extract_gmb_kpis_from_chart_paths,
                )
                ocr_kpis = extract_gmb_kpis_from_chart_paths(charts, out_dir)
                for key, ocr_val in ocr_kpis.items():
                    entry = kpis.get(key) or {}
                    if not entry.get("value") and ocr_val:
                        kpis[key] = {"value": ocr_val}
                        _log(f"tab '{key}': OCR value={ocr_val!r}")
            except ImportError:
                pass

        if args.screenshot:
            full_path = Path(args.screenshot).resolve()
            full_path.parent.mkdir(parents=True, exist_ok=True)
            target_page = (dashboard_page if _page_alive(dashboard_page)
                              else page if _page_alive(page) else None)
            if target_page is not None:
                try:
                    target_page.screenshot(path=str(full_path), full_page=True)
                except Exception:
                    pass

        final_url = ""
        for candidate in (dashboard_page, page):
            if _page_alive(candidate):
                try:
                    final_url = candidate.url
                except Exception:
                    final_url = ""
                if final_url:
                    break
        payload = {
            "captured_at": _now_iso(),
            "url": final_url,
            "project": project_name,
            "query": project_name,
            "period_start": period_start,
            "period_end": period_end,
            "kpis": kpis,
            "charts": charts,
        }

        if not kpis and out_path.exists():
            _log("capture returned empty kpis; preserving previous gmb_ui.json")
        else:
            if out_path.exists() and kpis:
                bak = out_path.with_suffix(".json.bak")
                try:
                    import shutil
                    shutil.copy2(out_path, bak)
                except OSError:
                    pass
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        print(f"Wrote {out_path}")
        for key, info in kpis.items():
            value = info.get("value") if isinstance(info, dict) else None
            print(f"  KPI {key}: {value or '<not found>'}")
        for key, value in charts.items():
            print(f"  CARD {key}: {value or '<not found>'}")

        try:
            context.close()
        except Exception:
            pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
