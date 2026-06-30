"""Recover Clarity headline KPIs from dashboard PNGs when DOM scrape missed them."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.reporting.gmb_card_ocr import ocr_text_from_png

logger = logging.getLogger(__name__)

_KPI_PATTERNS: dict[str, tuple[str, ...]] = {
    "sessions": (r"sessions?",),
    "pages_per_session": (
        r"pages?\s+par\s+session",
        r"pages?\s+per\s+session",
    ),
    "scroll_depth": (
        r"profondeur\s+de\s+d[eé]filement",
        r"scroll\s+depth",
    ),
    "active_time": (
        r"temps\s+d.?activit[eé]\s+pass[eé]",
        r"active\s+time",
    ),
}


def _normalize_ocr(text: str) -> str:
    return (
        (text or "")
        .replace("\u202f", " ")
        .replace("\xa0", " ")
        .replace("'", "'")
        .replace("'", "'")
        .lower()
    )


def _digits_only(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _sanitize_kpi_value(key: str, raw: str) -> str | None:
    """Reject obvious OCR false positives (e.g. 59196 as scroll depth)."""
    val = (raw or "").strip()
    if not val:
        return None
    lower = val.lower()
    if key == "scroll_depth":
        if "%" in val:
            digits = _digits_only(val)
            if digits and int(digits) <= 100:
                return val
            return None
        digits = _digits_only(val)
        if not digits:
            return val
        n = int(digits)
        if n <= 100:
            return val if "%" in val else f"{n}%"
        return None
    if key == "pages_per_session":
        if re.search(r"\b(sec|min|s|m|h)\b", lower):
            return None
        digits = _digits_only(val)
        if digits and int(digits) > 50:
            return None
        return val
    if key == "active_time":
        if re.search(r"\b(sec|min|s|m|h)\b", lower):
            return val
        digits = _digits_only(val)
        if digits and int(digits) > 7200:
            return None
        return val
    if key == "sessions":
        digits = _digits_only(val)
        if digits and int(digits) > 50_000_000:
            return None
        return val
    return val


def _value_after_label(block: str, patterns: tuple[str, ...]) -> str | None:
    norm = _normalize_ocr(block)
    for pat in patterns:
        m = re.search(
            rf"{pat}[^\d]{{0,40}}(-?[\d][\d\s.,]*\s*(?:%|sec|min|s|m|h)?)",
            norm,
            flags=re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    lines = norm.splitlines()
    for i, line in enumerate(lines):
        if not any(re.search(pat, line, re.IGNORECASE) for pat in patterns):
            continue
        for candidate in (line, lines[i + 1] if i + 1 < len(lines) else ""):
            nums = re.findall(
                r"-?[\d][\d\s.,]*\s*(?:%|sec|min|s|m|h)?",
                candidate,
                flags=re.IGNORECASE,
            )
            if nums:
                return nums[-1].strip()
    return None


def _ocr_top_band(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError:
        return ocr_text_from_png(path)
    try:
        img = Image.open(path).convert("RGB")
    except OSError:
        return ""
    w, h = img.size
    band = img.crop((0, 0, w, max(int(h * 0.28), 120)))
    tmp = path.parent / f".{path.stem}_kpi_ocr.png"
    try:
        band.save(tmp, format="PNG")
        return ocr_text_from_png(tmp)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _sessions_from_devices_png(path: Path) -> str | None:
    text = ocr_text_from_png(path)
    if not text:
        return None
    counts: list[int] = []
    for m in re.finditer(r"(\d[\d\s.,]*)\s*\(", text):
        digits = re.sub(r"\D", "", m.group(1))
        if not digits:
            continue
        try:
            n = int(digits)
        except ValueError:
            continue
        if 0 < n < 5_000_000:
            counts.append(n)
    if len(counts) >= 2:
        total = sum(counts[:3])
        logger.info(
            "[clarity-kpi-ocr] sessions estimated from devices chart: %s",
            total,
        )
        return f"{total:,}".replace(",", " ")
    return None


def extract_clarity_kpis_from_pngs(output_dir: Path) -> dict[str, str]:
    """Best-effort KPI recovery from overview/dashboard/devices screenshots."""
    out: dict[str, str] = {}
    candidates = (
        output_dir / "clarity_card_overview.png",
        output_dir / "clarity_dashboard.png",
    )
    band_text = ""
    for path in candidates:
        if path.is_file():
            band_text = _ocr_top_band(path)
            if band_text.strip():
                break
    if band_text:
        for key, patterns in _KPI_PATTERNS.items():
            val = _value_after_label(band_text, patterns)
            if val:
                clean = _sanitize_kpi_value(key, val)
                if clean:
                    out[key] = clean
    if "sessions" not in out:
        sessions = _sessions_from_devices_png(
            output_dir / "clarity_card_devices.png",
        )
        if sessions:
            out["sessions"] = sessions
    return out


def merge_clarity_kpi_fallback(
    ui_payload: dict[str, Any] | None,
    output_dir: Path,
) -> dict[str, str]:
    """Fill missing KPI strings from PNG OCR when JSON scrape returned nulls."""
    merged: dict[str, str] = {}
    kpis = (ui_payload or {}).get("kpis") or {}
    for key in _KPI_PATTERNS:
        entry = kpis.get(key)
        raw = entry.get("value") if isinstance(entry, dict) else None
        if raw and str(raw).strip():
            merged[key] = str(raw).strip()
    missing = [k for k in _KPI_PATTERNS if k not in merged]
    if not missing:
        return merged
    ocr_vals = extract_clarity_kpis_from_pngs(output_dir)
    for key in missing:
        if ocr_vals.get(key):
            clean = _sanitize_kpi_value(key, ocr_vals[key])
            if clean:
                merged[key] = clean
                logger.info("[clarity-kpi-ocr] recovered %s=%s", key, merged[key])
    return merged


_BAD_CLARITY_WIDGET_RE = re.compile(
    r"retours rapides|quick back|événements intelligents|smart event|"
    r"utilisateur principal|top user|flutter|désormais disponible",
    re.IGNORECASE,
)


def clarity_widget_png_valid(card_id: str, path: Path) -> bool:
    """Reject Clarity widget PNGs that clearly show the wrong dashboard card."""
    if not path.is_file() or path.stat().st_size < 500:
        return False
    try:
        text = ocr_text_from_png(path)
    except OSError:
        return True
    if not (text or "").strip():
        return True
    norm = _normalize_ocr(text)
    if _BAD_CLARITY_WIDGET_RE.search(norm):
        logger.warning(
            "[clarity-widget-ocr] %s rejected (wrong widget content in %s)",
            card_id,
            path.name,
        )
        return False
    return True
