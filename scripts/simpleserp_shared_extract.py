"""Scrape public SimpleSERP shared dashboards using the 1m comparison preset.

Usage:
    python scripts/simpleserp_shared_extract.py --client guivarche --month 2026-07
    python scripts/simpleserp_shared_extract.py --url URL --out out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
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
) -> dict[str, Any]:
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
        _log("click 1m comparison preset")
        apply_one_month_compare(page)
        keywords = scrape_keywords(page)
        title = ""
        try:
            title = page.locator("h1").first.inner_text(timeout=3_000).strip()
        except Exception:
            title = ""
        browser.close()

    return {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": url,
        "title": title,
        "comparison": "1m",
        "previous_fill_rate": round(previous_fill_rate(keywords), 3),
        "keywords": keywords,
    }


def extract_client_projects(
    client_id: str,
    month: str,
    *,
    headless: bool = True,
    out_dir: Path | None = None,
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
        payload = extract_shared_dashboard(url, headless=headless)
        payload["project_id"] = pid
        payload["label"] = str(project.get("label") or pid)
        payload["report_month"] = period.label
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
    parser.add_argument("--url", default="", help="Single shared dashboard URL")
    parser.add_argument("--out", default="",
                        help="Output JSON path (single URL mode)")
    parser.add_argument("--show", action="store_true", help="Non-headless browser")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    headless = not args.show
    if args.client and args.month:
        extract_client_projects(args.client, args.month, headless=headless)
        return 0
    if args.url and args.out:
        payload = extract_shared_dashboard(args.url, headless=headless)
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
