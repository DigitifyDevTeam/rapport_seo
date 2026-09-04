"""Scrape SimpleSERP compare tables and render a keyword-compare-only deck.

Usage:
    python scripts/run_keyword_compare_only.py \\
        --client guivarche \\
        --from-date 01/08/2026 \\
        --to-date 01/09/2026

Output:
    outputs/<client>/compare_<from>_<to>/
      simpleserp_*.json
      keyword_compare_report.pptx
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from simpleserp_shared_extract import (  # noqa: E402
    extract_client_projects,
    parse_flexible_date,
)
from src.config import TEMPLATE_PATH, get_client  # noqa: E402
from src.periods import format_date_fr  # noqa: E402
from src.reporting.ensure_template import ensure_report_template  # noqa: E402
from src.reporting.pptx_report import render as render_pptx  # noqa: E402
from src.transform.simpleserp_compare import (  # noqa: E402
    KEYWORD_COMPARE_MAX_SLIDES,
    build_compare_frame,
    rows_from_payload,
    split_compare_frames,
)

logger = logging.getLogger(__name__)


def _load_simpleserp_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read SimpleSERP JSON %s: %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _output_dir(client_id: str, from_date: date, to_date: date) -> Path:
    return (
        ROOT
        / "outputs"
        / client_id
        / f"compare_{from_date.isoformat()}_{to_date.isoformat()}"
    )


def _report_month_label(to_date: date) -> str:
    """Folder month key — end month of the compare window."""
    return f"{to_date.year:04d}-{to_date.month:02d}"


def build_keyword_compare_data(
    client_id: str,
    output_dir: Path,
    *,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    client = get_client(client_id)
    cfg = client.simpleserp or {}
    projects = list(cfg.get("projects") or [])
    if not projects:
        raise RuntimeError(f"Client {client_id} has no simpleserp.projects in clients.yaml")

    brands = {
        str(p.get("id") or "").strip(): str(p.get("label") or p.get("id") or "").strip()
        for p in projects
        if isinstance(p, dict)
    }
    brand_left = brands.get("guivarche") or "Guivarche"
    brand_right = brands.get("maillard") or "Maillard"
    range_label = f"{format_date_fr(from_date)} – {format_date_fr(to_date)}"
    title_base = (
        f"Comparaison mots-clés ({brand_left} vs {brand_right}) — {range_label}"
    )

    empty = pd.DataFrame()
    data: dict[str, Any] = {
        "keyword_compare_only": True,
        "keyword_compare_enabled": True,
        "keyword_compare_slide_count": 0,
        "keyword_compare_brand_left": brand_left,
        "keyword_compare_brand_right": brand_right,
        "keyword_compare_date_range": range_label,
        "report_date": to_date.isoformat(),
        "client_name": client.name,
    }
    for part in range(1, KEYWORD_COMPARE_MAX_SLIDES + 1):
        data[f"table_keyword_compare_{part}"] = empty
        data[f"keyword_compare_title_{part}"] = title_base

    g_payload = _load_simpleserp_json(output_dir / "simpleserp_guivarche.json")
    m_payload = _load_simpleserp_json(output_dir / "simpleserp_maillard.json")
    frame = build_compare_frame(
        rows_from_payload(g_payload),
        rows_from_payload(m_payload),
    )
    chunks = split_compare_frames(frame)
    slide_count = len(chunks)
    data["keyword_compare_slide_count"] = slide_count
    for idx, chunk in enumerate(chunks, start=1):
        data[f"table_keyword_compare_{idx}"] = chunk
        data[f"keyword_compare_title_{idx}"] = (
            f"{title_base} — {idx}/{slide_count}"
        )
    if frame.empty:
        logger.warning(
            "Keyword compare tables empty — check SimpleSERP JSON under %s",
            output_dir,
        )
    return data


def run_keyword_compare_only(
    client_id: str,
    from_date: date,
    to_date: date,
    *,
    headless: bool = True,
    output_dir: Path | None = None,
) -> Path:
    if from_date >= to_date:
        raise ValueError("from-date must be before to-date")

    dest = output_dir or _output_dir(client_id, from_date, to_date)
    dest.mkdir(parents=True, exist_ok=True)
    month = _report_month_label(to_date)

    logger.info(
        "[%s] scraping SimpleSERP compare %s → %s",
        client_id,
        from_date.isoformat(),
        to_date.isoformat(),
    )
    extract_client_projects(
        client_id,
        month,
        headless=headless,
        out_dir=dest,
        from_date=from_date,
        to_date=to_date,
    )

    ensure_report_template(TEMPLATE_PATH)
    data = build_keyword_compare_data(
        client_id,
        dest,
        from_date=from_date,
        to_date=to_date,
    )
    data_path = dest / "keyword_compare_data.json"
    data_path.write_text(
        json.dumps(
            {
                key: (val.to_dict(orient="records") if isinstance(val, pd.DataFrame) else val)
                for key, val in data.items()
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    pptx_path = dest / "keyword_compare_report.pptx"
    render_pptx(TEMPLATE_PATH, pptx_path, data)
    logger.info("[%s] wrote %s", client_id, pptx_path)
    return pptx_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="guivarche", help="Client id")
    parser.add_argument(
        "--from-date",
        required=True,
        help="Compare start date (DD/MM/YYYY)",
    )
    parser.add_argument(
        "--to-date",
        required=True,
        help="Compare end date (DD/MM/YYYY)",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Override output directory",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show browser while scraping SimpleSERP",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = _parse_args()
    from_date = parse_flexible_date(args.from_date)
    to_date = parse_flexible_date(args.to_date)
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    run_keyword_compare_only(
        args.client,
        from_date,
        to_date,
        headless=not args.show,
        output_dir=out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
