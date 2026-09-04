"""Scrape public SimpleSERP shared dashboards using the 1m comparison preset.

Usage:
    python scripts/simpleserp_shared_extract.py --client guivarche --month 2026-07
    python scripts/simpleserp_shared_extract.py --client guivarche --month 2026-09 \\
        --from-date 01/08/2026 --to-date 01/09/2026
    python scripts/simpleserp_shared_extract.py --url URL --out out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_client
from src.periods import Period


def _log(msg: str) -> None:
    print(f"[simpleserp] {msg}", flush=True)


def _wait_dashboard(page: Page, timeout_ms: int = 60_000) -> None:
    page.wait_for_selector("text=Keywords", timeout=timeout_ms)
    page.wait_for_selector("button:has-text('1m')", timeout=timeout_ms)


_ARIA_DATE_RE = re.compile(
    r"^(?:Today,\s+)?\w+,\s+(\w+)\s+(\d+)(?:st|nd|rd|th),\s+(\d{4})$"
)
_MONTHS_EN = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


def _ordinal(day: int) -> str:
    if 11 <= (day % 100) <= 13:
        return f"{day}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _aria_date_label(value: date) -> str:
    return f"{value.strftime('%A')}, {value.strftime('%B')} {_ordinal(value.day)}, {value.year}"


def _parse_aria_date_label(label: str) -> date | None:
    match = _ARIA_DATE_RE.match(label.strip())
    if not match:
        return None
    month_name, day_text, year_text = match.groups()
    month = _MONTHS_EN.get(month_name)
    if not month:
        return None
    try:
        return date(int(year_text), month, int(day_text))
    except ValueError:
        return None


def _visible_month_for_calendar(page: Page, calendar_index: int) -> tuple[int, int] | None:
    """Return ``(year, month)`` for the month currently shown in a calendar."""
    labels: list[date] = []
    for btn in page.get_by_role("button").all():
        name = (btn.get_attribute("aria-label") or btn.inner_text() or "").strip()
        parsed = _parse_aria_date_label(name)
        if parsed is not None:
            labels.append(parsed)
    if not labels:
        return None
    labels.sort(key=lambda d: (d.year, d.month, d.day))
    per_calendar = max(28, len(labels) // 2)
    start = calendar_index * per_calendar
    chunk = labels[start:start + per_calendar] or labels
    anchor = chunk[len(chunk) // 2]
    return anchor.year, anchor.month


def _pick_date_in_calendar(page: Page, target: date, *, calendar_index: int) -> None:
    """Pick *target* in the From (0) or To (1) calendar of the Custom dialog."""
    aria = _aria_date_label(target)
    prev = page.get_by_role("button", name="Go to the Previous Month")
    nxt = page.get_by_role("button", name="Go to the Next Month")
    for attempt in range(48):
        buttons = page.get_by_role("button", name=aria)
        if buttons.count() > calendar_index:
            btn = buttons.nth(calendar_index)
            try:
                btn.scroll_into_view_if_needed(timeout=3_000)
                btn.click(timeout=10_000)
                _log(f"selected {target.isoformat()} in calendar {calendar_index}")
                return
            except Exception:
                pass
        visible = _visible_month_for_calendar(page, calendar_index)
        if visible is None:
            raise RuntimeError("SimpleSERP custom date dialog: calendar not found")
        vy, vm = visible
        ty, tm = target.year, target.month
        if (ty, tm) < (vy, vm):
            prev.nth(calendar_index).click(timeout=10_000)
        elif (ty, tm) > (vy, vm):
            nxt.nth(calendar_index).click(timeout=10_000)
        else:
            raise RuntimeError(
                f"SimpleSERP date {target.isoformat()} not clickable "
                f"(calendar {calendar_index}, attempt {attempt + 1})"
            )
        page.wait_for_timeout(350)
    raise RuntimeError(f"Could not pick {target.isoformat()} in calendar {calendar_index}")


def apply_custom_date_compare(page: Page, from_date: date, to_date: date) -> None:
    """Open Custom and compare keyword ranks between two exact dates."""
    btn = page.get_by_role("button", name="Custom", exact=True)
    if btn.count() == 0:
        btn = page.locator("button", has_text="Custom").first
    btn.click(timeout=15_000)
    page.wait_for_selector("text=Select Date Range for Comparison", timeout=20_000)
    _log(f"custom compare {from_date.isoformat()} → {to_date.isoformat()}")
    _pick_date_in_calendar(page, from_date, calendar_index=0)
    _pick_date_in_calendar(page, to_date, calendar_index=1)
    page.get_by_role("button", name="Apply", exact=True).click(timeout=15_000)
    try:
        page.wait_for_selector("text=Select Date Range for Comparison",
                               state="hidden", timeout=20_000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    try:
        page.wait_for_selector("table tbody tr", timeout=20_000)
    except Exception:
        _log("warning: keyword table rows not seen after custom apply; continuing")
    for _ in range(15):
        rate = previous_fill_rate(scrape_keywords(page))
        if rate >= 0.15:
            _log(f"custom table ready (previous fill {rate:.0%})")
            return
        page.wait_for_timeout(400)
    _log("warning: Previous still sparse after custom range; scraping anyway")


def parse_flexible_date(value: str) -> date:
    """Parse ``DD/MM/YYYY``, ``DD/MM/YY``, or ``YYYY-MM-DD``."""
    text = value.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date {value!r} — use DD/MM/YYYY or YYYY-MM-DD")


def apply_one_month_compare(page: Page) -> None:
    """Click the ``1m`` preset (one-month comparison) before Custom."""
    btn = page.get_by_role("button", name="1m", exact=True)
    if btn.count() == 0:
        btn = page.locator("button", has_text="1m").first
    btn.click(timeout=15_000)

    # Wait for loading overlay to clear, then for Previous to populate.
    try:
        page.wait_for_selector("text=Loading shared dashboard", state="hidden",
                               timeout=20_000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    try:
        page.wait_for_selector("table tbody tr", timeout=20_000)
    except Exception:
        _log("warning: keyword table rows not seen after 1m click; continuing")

    # Poll until Previous has values (table can refresh a beat after the click).
    for _ in range(15):
        rate = previous_fill_rate(scrape_keywords(page))
        if rate >= 0.15:
            _log(f"1m table ready (previous fill {rate:.0%})")
            return
        page.wait_for_timeout(400)
    _log("warning: Previous still sparse after 1m; scraping anyway")


def scrape_keywords(page: Page) -> list[dict[str, str]]:
    data = page.evaluate(
        """() => {
          const table = document.querySelector('table');
          if (!table) return [];
          const headers = [...table.querySelectorAll('thead th, tr th')]
            .map(th => (th.innerText || '').trim().toLowerCase());
          const idx = {
            keyword: headers.findIndex(h => h === 'keyword'),
            current: headers.findIndex(h => h === 'current'),
            previous: headers.findIndex(h => h === 'previous'),
            change: headers.findIndex(h => h === 'change'),
          };
          const bodyRows = [...table.querySelectorAll('tbody tr')];
          const rows = bodyRows.length
            ? bodyRows
            : [...table.querySelectorAll('tr')].slice(1);
          const cellText = (td) => {
            if (!td) return '-';
            const raw = (td.innerText || '').trim().replace(/\\s+/g, ' ');
            return raw || '-';
          };
          const out = [];
          for (const tr of rows) {
            const cells = [...tr.querySelectorAll('td')];
            if (!cells.length) continue;
            const keyword = idx.keyword >= 0
              ? cellText(cells[idx.keyword]) : cellText(cells[0]);
            if (!keyword || keyword === '-') continue;
            out.push({
              keyword,
              current: idx.current >= 0 ? cellText(cells[idx.current]) : '-',
              previous: idx.previous >= 0 ? cellText(cells[idx.previous]) : '-',
              change: idx.change >= 0 ? cellText(cells[idx.change]) : '-',
            });
          }
          return out;
        }"""
    )
    return list(data or [])


def previous_fill_rate(keywords: list[dict[str, str]]) -> float:
    if not keywords:
        return 0.0
    ok = 0
    for row in keywords:
        prev = str(row.get("previous") or "").strip()
        if prev and prev != "-":
            ok += 1
    return ok / len(keywords)


def extract_shared_dashboard(
    url: str,
    *,
    headless: bool = True,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    if (from_date is None) ^ (to_date is None):
        raise ValueError("Provide both from_date and to_date, or neither")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        _log(f"open {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        _wait_dashboard(page)
        if from_date and to_date:
            _log("apply custom date comparison")
            apply_custom_date_compare(page, from_date, to_date)
            comparison = "custom"
        else:
            _log("click 1m comparison preset")
            apply_one_month_compare(page)
            comparison = "1m"
        keywords = scrape_keywords(page)
        title = ""
        try:
            title = page.locator("h1").first.inner_text(timeout=3_000).strip()
        except Exception:
            title = ""
        browser.close()

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": url,
        "title": title,
        "comparison": comparison,
        "previous_fill_rate": round(previous_fill_rate(keywords), 3),
        "keywords": keywords,
    }
    if from_date and to_date:
        payload["from_date"] = from_date.isoformat()
        payload["to_date"] = to_date.isoformat()
    return payload


def extract_client_projects(
    client_id: str,
    month: str,
    *,
    headless: bool = True,
    out_dir: Path | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Path]:
    client = get_client(client_id)
    cfg = client.simpleserp or {}
    projects = list(cfg.get("projects") or [])
    if not projects:
        raise RuntimeError(f"No simpleserp.projects for client {client_id}")

    period = Period.parse(month)
    dest = out_dir or (client.output_dir / period.label)
    dest.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    for project in projects:
        pid = str(project.get("id") or "project").strip()
        url = str(project.get("shared_url") or "").strip()
        if not url:
            continue
        payload = extract_shared_dashboard(
            url,
            headless=headless,
            from_date=from_date,
            to_date=to_date,
        )
        payload["project_id"] = pid
        payload["label"] = str(project.get("label") or pid)
        payload["report_month"] = period.label
        if from_date and to_date:
            payload["report_label"] = (
                f"{from_date.isoformat()}_{to_date.isoformat()}"
            )
        path = dest / f"simpleserp_{pid}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        _log(f"wrote {path} ({len(payload.get('keywords') or [])} keywords, "
             f"fill {payload.get('previous_fill_rate')})")
        written[pid] = path
        time.sleep(0.5)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="", help="Client id (e.g. guivarche)")
    parser.add_argument("--month", default="", help="Report month YYYY-MM")
    parser.add_argument("--from-date", default="",
                        help="Custom compare start (DD/MM/YYYY)")
    parser.add_argument("--to-date", default="",
                        help="Custom compare end (DD/MM/YYYY)")
    parser.add_argument("--url", default="", help="Single shared dashboard URL")
    parser.add_argument("--out", default="",
                        help="Output JSON path (single URL mode)")
    parser.add_argument("--show", action="store_true", help="Non-headless browser")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    headless = not args.show
    from_date = parse_flexible_date(args.from_date) if args.from_date else None
    to_date = parse_flexible_date(args.to_date) if args.to_date else None
    if args.client and args.month:
        extract_client_projects(
            args.client,
            args.month,
            headless=headless,
            from_date=from_date,
            to_date=to_date,
        )
        return 0
    if args.url and args.out:
        payload = extract_shared_dashboard(
            args.url,
            headless=headless,
            from_date=from_date,
            to_date=to_date,
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        _log(f"wrote {out}")
        return 0
    print("Provide --client/--month or --url/--out", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
