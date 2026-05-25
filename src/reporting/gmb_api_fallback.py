"""Fill GMB slide assets from the Performance API when browser UI capture fails.

Used on Docker/VPS when Google blocks Search or the Playwright session is stale.
Requires ``GMB_LOCATION_ID_<CLIENT>`` in ``.env`` (or ``gmb.location_id`` in YAML).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

GMB_API_FALLBACK_VERSION = "api-fallback-v1"
# Keep aligned with scripts/gmb_ui_extract.py and run_monthly.GMB_UI_CAPTURE_VERSION.
GMB_UI_CAPTURE_VERSION = "calmonth-v4-public-fiche"

_TAB_FILES: dict[str, str] = {
    "overview": "gmb_card_overview.png",
    "calls": "gmb_card_calls.png",
    "bookings": "gmb_card_bookings.png",
    "directions": "gmb_card_directions.png",
    "website_clicks": "gmb_card_website_clicks.png",
}

_TAB_LABELS: dict[str, str] = {
    "overview": "Interactions totales",
    "calls": "Appels",
    "bookings": "Réservations",
    "directions": "Itinéraires",
    "website_clicks": "Clics vers le site Web",
}

_PRIMARY = "#0F172A"
_ACCENT = "#14B8A6"


def _format_total(value: str) -> str:
    raw = str(value).strip().replace("\u202f", "").replace(" ", "").replace(",", "")
    if not raw.isdigit():
        return str(value).strip()
    n = int(raw)
    return f"{n:,}".replace(",", "\u202f")


def _write_kpi_card_png(path: Path, label: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.axis("off")
    ax.text(
        0.5, 0.72, label.upper(),
        ha="center", va="center", fontsize=11, color="#64748B",
        transform=ax.transAxes,
    )
    ax.text(
        0.5, 0.38, _format_total(value),
        ha="center", va="center", fontsize=34, color=_PRIMARY,
        fontweight="bold", transform=ax.transAxes,
    )
    ax.text(
        0.5, 0.12, "Source : Google Business Profile (API)",
        ha="center", va="center", fontsize=9, color="#94A3B8",
        transform=ax.transAxes,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _write_business_card_placeholder(path: Path, business_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")
    ax.axis("off")
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#E2E8F0")
    ax.text(
        0.5, 0.62, business_name,
        ha="center", va="center", fontsize=14, color=_PRIMARY,
        fontweight="bold", wrap=True, transform=ax.transAxes,
    )
    ax.text(
        0.5, 0.38, "Fiche Google Business Profile",
        ha="center", va="center", fontsize=11, color="#64748B",
        transform=ax.transAxes,
    )
    ax.text(
        0.5, 0.18, "Aperçu via API (capture navigateur indisponible)",
        ha="center", va="center", fontsize=9, color="#94A3B8",
        transform=ax.transAxes,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def gmb_ui_assets_complete(output_dir: Path, kpi_keys: tuple[str, ...]) -> bool:
    """True when KPI JSON values and card PNGs exist for this month."""
    ui_path = output_dir / "gmb_ui.json"
    if not ui_path.is_file():
        return False
    try:
        payload = json.loads(ui_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    kpis = payload.get("kpis") or {}
    for key in kpi_keys:
        entry = kpis.get(key)
        if not isinstance(entry, dict) or not str(entry.get("value") or "").strip():
            return False
        png = output_dir / _TAB_FILES.get(key, f"gmb_card_{key}.png")
        if not png.is_file() or png.stat().st_size < 400:
            return False
    card = output_dir / "gmb_business_card.png"
    return card.is_file() and card.stat().st_size >= 400


def materialize_gmb_from_api(
    output_dir: Path,
    *,
    period_label: str,
    period_start: str,
    period_end: str,
    kpis: dict[str, str],
    project_name: str,
    business_card_path: Path | None = None,
) -> bool:
    """Write ``gmb_ui.json`` + card PNGs from API totals. Returns True if written."""
    if not kpis:
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    charts: dict[str, str] = {}
    kpi_payload: dict[str, dict[str, str]] = {}

    for key, filename in _TAB_FILES.items():
        raw = (kpis.get(key) or "").strip()
        if not raw and key != "bookings":
            continue
        if key == "bookings" and not raw:
            raw = "0"
        label = _TAB_LABELS[key]
        out = output_dir / filename
        _write_kpi_card_png(out, label, raw)
        charts[key] = str(out.resolve())
        kpi_payload[key] = {"value": _format_total(raw)}

    if not kpi_payload:
        return False

    card_out = output_dir / "gmb_business_card.png"
    if business_card_path and business_card_path.is_file():
        import shutil
        shutil.copy2(business_card_path, card_out)
    elif not card_out.is_file() or card_out.stat().st_size < 400:
        _write_business_card_placeholder(card_out, project_name)
    charts["business_card"] = str(card_out.resolve())

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_version": GMB_API_FALLBACK_VERSION,
        "ui_capture_version": GMB_UI_CAPTURE_VERSION,
        "report_month": period_label,
        "period_start": period_start,
        "period_end": period_end,
        "project": project_name,
        "source": "businessprofileperformance_api",
        "kpis": kpi_payload,
        "charts": charts,
    }
    (output_dir / "gmb_ui.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    logger.info(
        "[gmb-api] materialized UI assets in %s from Performance API (%s)",
        output_dir,
        ", ".join(f"{k}={v['value']}" for k, v in kpi_payload.items()),
    )
    return True
