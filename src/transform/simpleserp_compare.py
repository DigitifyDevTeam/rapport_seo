"""Build Guivarche vs Maillard SimpleSERP comparison tables."""

from __future__ import annotations

from typing import Any

import pandas as pd

# Internal column names used by the dual-header PPTX renderer.
COL_KEYWORD = "keyword"
COL_G_CUR = "g_current"
COL_G_PREV = "g_previous"
COL_G_CHG = "g_change"
COL_M_CUR = "m_current"
COL_M_PREV = "m_previous"
COL_M_CHG = "m_change"

COMPARE_COLUMNS = (
    COL_KEYWORD,
    COL_G_CUR,
    COL_G_PREV,
    COL_G_CHG,
    COL_M_CUR,
    COL_M_PREV,
    COL_M_CHG,
)

MISSING = "-"

# Keep tables inside the white panel (2 header rows + data rows).
KEYWORD_COMPARE_MAX_ROWS = 13
KEYWORD_COMPARE_MAX_SLIDES = 4


def _norm_key(keyword: str) -> str:
    return " ".join(str(keyword or "").strip().casefold().split())


def _cell(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"n/a", "na", "none", "null", "—"}:
        return MISSING
    return text


def _parse_rank(value: str) -> int | None:
    text = _cell(value)
    if text == MISSING:
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    if cleaned.endswith("+"):
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _derive_change(current: str, previous: str, change: str) -> str:
    """Fill Change when SimpleSERP leaves it blank but both ranks exist."""
    existing = _cell(change)
    if existing != MISSING:
        return existing
    cur = _parse_rank(current)
    prev = _parse_rank(previous)
    if cur is None or prev is None:
        return MISSING
    # Positive = improved (moved up); matches SimpleSERP's Change column.
    return str(prev - cur)


def rows_from_payload(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    """Normalize extractor JSON ``{keywords: [...]}`` into row dicts."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("keywords") or payload.get("rows") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword") or item.get("Keyword") or "").strip()
        if not keyword:
            continue
        current = _cell(item.get("current", item.get("Current")))
        previous = _cell(item.get("previous", item.get("Previous")))
        change = _derive_change(
            current,
            previous,
            _cell(item.get("change", item.get("Change"))),
        )
        out.append({
            "keyword": keyword,
            "current": current,
            "previous": previous,
            "change": change,
        })
    return out


def build_compare_frame(
    guivarche_rows: list[dict[str, str]],
    maillard_rows: list[dict[str, str]],
) -> pd.DataFrame:
    """Order: matched → Guivarche-only → Maillard-only."""
    g_map: dict[str, dict[str, str]] = {}
    for row in guivarche_rows:
        key = _norm_key(row["keyword"])
        if key and key not in g_map:
            g_map[key] = row

    m_map: dict[str, dict[str, str]] = {}
    for row in maillard_rows:
        key = _norm_key(row["keyword"])
        if key and key not in m_map:
            m_map[key] = row

    matched_keys = [k for k in g_map if k in m_map]
    g_only_keys = [k for k in g_map if k not in m_map]
    m_only_keys = [k for k in m_map if k not in g_map]

    records: list[dict[str, str]] = []
    for key in matched_keys:
        g_row, m_row = g_map[key], m_map[key]
        records.append({
            COL_KEYWORD: g_row["keyword"],
            COL_G_CUR: g_row["current"],
            COL_G_PREV: g_row["previous"],
            COL_G_CHG: g_row["change"],
            COL_M_CUR: m_row["current"],
            COL_M_PREV: m_row["previous"],
            COL_M_CHG: m_row["change"],
        })
    for key in g_only_keys:
        g_row = g_map[key]
        records.append({
            COL_KEYWORD: g_row["keyword"],
            COL_G_CUR: g_row["current"],
            COL_G_PREV: g_row["previous"],
            COL_G_CHG: g_row["change"],
            COL_M_CUR: MISSING,
            COL_M_PREV: MISSING,
            COL_M_CHG: MISSING,
        })
    for key in m_only_keys:
        m_row = m_map[key]
        records.append({
            COL_KEYWORD: m_row["keyword"],
            COL_G_CUR: MISSING,
            COL_G_PREV: MISSING,
            COL_G_CHG: MISSING,
            COL_M_CUR: m_row["current"],
            COL_M_PREV: m_row["previous"],
            COL_M_CHG: m_row["change"],
        })

    if not records:
        return pd.DataFrame(columns=list(COMPARE_COLUMNS))
    return pd.DataFrame.from_records(records, columns=list(COMPARE_COLUMNS))


def split_compare_frames(
    frame: pd.DataFrame,
    *,
    max_rows: int = KEYWORD_COMPARE_MAX_ROWS,
    max_slides: int = KEYWORD_COMPARE_MAX_SLIDES,
) -> tuple[pd.DataFrame, ...]:
    """Split rows into slide chunks that fit the PPTX panel."""
    if frame.empty:
        return (frame.copy(),)

    n = len(frame)
    parts = max(1, min(max_slides, (n + max_rows - 1) // max_rows))
    base = n // parts
    rem = n % parts
    chunks: list[pd.DataFrame] = []
    start = 0
    for idx in range(parts):
        size = base + (1 if idx < rem else 0)
        end = start + size
        chunks.append(frame.iloc[start:end].reset_index(drop=True))
        start = end
    return tuple(chunks)
