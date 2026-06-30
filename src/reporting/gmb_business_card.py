"""Validate and repair ``gmb_business_card.png`` (public GBP fiche screenshot)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from PIL import Image

from src.reporting.gmb_card_ocr import ocr_text_from_png

logger = logging.getLogger(__name__)

# Organic SERP snippet / local pack list (wrong) vs full knowledge panel (correct).
_ORGANIC_MARKERS = (
    "fleurs cbd, huiles",
    "boutique cbd | cbd shop",
    "produits dédiés au cbd",
    "https://originecbd",
)
_LOCAL_PACK_MARKERS = (
    "vous êtes arrivé à la fin de la liste",
    "fin de la liste",
    "résultats pour",
    "plus de lieux",
)
# Empty Google Maps shell (city illustration + generic chrome, no business loaded).
_MAPS_PLACEHOLDER_MARKERS = (
    "à proximité",
    "ajouter un libellé",
    "à propos de ces données",
    "envoyer vers un téléphone",
)
_PANEL_MARKERS = (
    "avis google",
    "magasin de",
    "gérez cette fiche",
    "modifier les infos",
    "concepteur de sites",
    "agence web",
    "ouvert",
    "itinéraire",
    "appeler",
    "site web",
    "enregistrer",
    "partager",
    "adresse",
    "téléphone",
    "boutique",
    "magasin de cbd",
    "nettoyage",
    "deep cleaning",
    "lavage",
    "canapé",
    "canape",
    "matelas",
    "tapis",
)


def _is_maps_placeholder(text: str) -> bool:
    """Generic Maps UI without a loaded place (city illustration + action row)."""
    lower = text.lower()
    placeholder_hits = sum(1 for m in _MAPS_PLACEHOLDER_MARKERS if m in lower)
    if placeholder_hits < 2:
        return False
    business_hints = (
        "origine",
        "cbd",
        "magasin",
        "avis google",
        "gérez cette fiche",
        "75004",
        "7500",
        "digitify",
        "deep cleaning",
        "deepcleaning",
        "nettoyage",
        "colombes",
        "téléphone",
        "adresse",
    )
    return not any(hint in lower for hint in business_hints)


def _looks_like_panel_by_shape(path: Path) -> bool:
    """Heuristic when Tesseract is unavailable (e.g. local Windows dev)."""
    try:
        with Image.open(path) as im:
            w, h = im.size
    except OSError:
        return False
    if h < 280 or w < 200:
        return False
    if w > 0 and h / w < 0.42:
        return False
    return True


def is_valid_public_fiche_png(path: Path) -> bool:
    """True when OCR suggests a full GBP panel, not an organic blue-link snippet."""
    if not path.is_file():
        return False
    text = ocr_text_from_png(path).lower()
    if len(text.strip()) < 12:
        ok = _looks_like_panel_by_shape(path)
        logger.info(
            "[gmb-card] %s: OCR unavailable/empty — shape heuristic=%s",
            path.name, ok,
        )
        return ok
    organic_hits = sum(1 for m in _ORGANIC_MARKERS if m in text)
    pack_hits = sum(1 for m in _LOCAL_PACK_MARKERS if m in text)
    panel_hits = sum(1 for m in _PANEL_MARKERS if m in text)
    if _is_maps_placeholder(text):
        logger.info("[gmb-card] %s: generic Maps placeholder (no business loaded)", path.name)
        return False
    if pack_hits >= 1:
        logger.info(
            "[gmb-card] %s: looks like local pack list (pack=%d)",
            path.name, pack_hits,
        )
        return False
    if organic_hits >= 1 and panel_hits < 2:
        logger.info(
            "[gmb-card] %s: looks like organic snippet (organic=%d panel=%d)",
            path.name, organic_hits, panel_hits,
        )
        return False
    if panel_hits >= 2:
        return True
    if panel_hits >= 1 and organic_hits == 0 and pack_hits == 0:
        if _looks_like_panel_by_shape(path):
            return True
    # Multiple "Site Web" / "Ouvert" lines usually means a results list, not one panel.
    if text.count("site web") >= 2 or text.count("ouvert") >= 2:
        logger.info(
            "[gmb-card] %s: multiple listing action buttons — local pack",
            path.name,
        )
        return False
    if "origine cbd" in text and ("paris" in text or "75004" in text):
        return panel_hits >= 1
    if "digitify" in text and panel_hits >= 1:
        return True
    if "deep cleaning" in text or "deepcleaning" in text:
        return panel_hits >= 1 or _looks_like_panel_by_shape(path)
    logger.info(
        "[gmb-card] %s: insufficient panel signals (panel=%d)",
        path.name, panel_hits,
    )
    return False


def reference_png_for_client(
    client_id: str,
    *,
    reference_path: Path | None = None,
) -> Path | None:
    """Bundled fiche PNG under ``scripts/clients/<client_id>/``."""
    if reference_path and reference_path.is_file():
        return reference_path
    client_dir = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "clients"
        / client_id
    )
    for name in ("gmb_business_card.png", "gmb_business_card_reference.png"):
        candidate = client_dir / name
        if candidate.is_file():
            return candidate
    return None


def _sync_gmb_ui_business_card(output_dir: Path, card_path: Path) -> None:
    """Point ``gmb_ui.json`` charts.business_card at the report PNG."""
    gmb_ui_path = output_dir / "gmb_ui.json"
    data: dict = {}
    if gmb_ui_path.is_file():
        try:
            loaded = json.loads(gmb_ui_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    charts = data.get("charts")
    if not isinstance(charts, dict):
        charts = {}
    charts["business_card"] = str(card_path.resolve())
    data["charts"] = charts
    try:
        gmb_ui_path.parent.mkdir(parents=True, exist_ok=True)
        gmb_ui_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("[gmb-card] could not update %s: %s", gmb_ui_path, exc)


def _is_usable_reference_png(path: Path) -> bool:
    """Lenient check for manual reference uploads (OCR may be sparse)."""
    if is_valid_public_fiche_png(path):
        return True
    if _looks_like_panel_by_shape(path):
        logger.info(
            "[gmb-card] accepting reference %s via shape heuristic",
            path.name,
        )
        return True
    return False


def apply_business_card_reference(
    output_dir: Path,
    *,
    client_id: str,
    reference_path: Path | None = None,
    force: bool = False,
) -> Path | None:
    """Copy a configured reference PNG into the report month folder."""
    ref = reference_png_for_client(
        client_id,
        reference_path=reference_path,
    )
    if ref is None:
        logger.warning(
            "[gmb-card] reference file missing for %s (expected %s)",
            client_id,
            reference_path
            or f"scripts/clients/{client_id}/gmb_business_card.png",
        )
        return None
    target = output_dir / "gmb_business_card.png"
    if not force and is_valid_public_fiche_png(target):
        return target
    if target.is_file():
        try:
            target.unlink()
        except OSError:
            pass
    if not _is_usable_reference_png(ref):
        logger.warning(
            "[gmb-card] reference image unusable for %s — check %s",
            client_id,
            ref,
        )
        return None
    shutil.copy2(ref, target)
    _sync_gmb_ui_business_card(output_dir, target)
    logger.info(
        "[gmb-card] using reference fiche for %s -> %s",
        client_id,
        target,
    )
    return target


def ensure_valid_business_card(
    output_dir: Path,
    *,
    client_id: str = "",
    reference_path: Path | None = None,
) -> Path | None:
    """Replace invalid ``gmb_business_card.png`` with the bundled reference."""
    target = output_dir / "gmb_business_card.png"
    if is_valid_public_fiche_png(target):
        return target
    if target.is_file():
        try:
            target.unlink()
        except OSError:
            pass
    ref = reference_png_for_client(
        client_id,
        reference_path=reference_path,
    ) if client_id else reference_path
    if ref is None:
        logger.warning(
            "[gmb-card] no valid business card in %s and no reference for %s",
            output_dir, client_id or "?",
        )
        return None
    if not is_valid_public_fiche_png(ref):
        logger.warning(
            "[gmb-card] reference image invalid for %s — not using %s",
            client_id or "?", ref.name,
        )
        return None
    shutil.copy2(ref, target)
    _sync_gmb_ui_business_card(output_dir, target)
    logger.info("[gmb-card] applied reference image for %s -> %s", client_id, target)
    return target
