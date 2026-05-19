"""Read headline totals from ``gmb_card_*.png`` GBP Performance screenshots.

Used when Playwright cannot read the DOM number but the card image was saved.
Requires ``pytesseract`` and a system ``tesseract`` binary (see README / .env
``TESSERACT_CMD`` on Windows).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

_GMB_CARD_FILES: dict[str, str] = {
    "overview": "gmb_card_overview.png",
    "calls": "gmb_card_calls.png",
    "bookings": "gmb_card_bookings.png",
    "directions": "gmb_card_directions.png",
    "website_clicks": "gmb_card_website_clicks.png",
}

_WARNED_NO_TESS = False
_WARNED_NO_PYTESSERACT = False

_DEFAULT_TESSERACT_CMDS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _tesseract_executable() -> str | None:
    cmd = (os.environ.get("TESSERACT_CMD") or "").strip()
    if cmd and Path(cmd).is_file():
        return cmd
    for candidate in _DEFAULT_TESSERACT_CMDS:
        if Path(candidate).is_file():
            return candidate
    which = shutil.which("tesseract")
    return which or None


def _configure_tesseract_cmd() -> None:
    import pytesseract

    cmd = _tesseract_executable()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _ocr_tesseract_cli(pil_img: Image.Image, psm: int, tesseract: str) -> str:
    """Run the ``tesseract`` binary (no ``pytesseract`` package required)."""
    tmp_path = Path(tempfile.gettempdir()) / f"gmb_ocr_{os.getpid()}_{id(pil_img)}.png"
    try:
        pil_img.save(tmp_path, format="PNG")
        for lang in ("fra+eng", "eng"):
            args = [
                tesseract,
                str(tmp_path),
                "-",
                "--oem",
                "3",
                "--psm",
                str(psm),
                "-l",
                lang,
                "-c",
                "tessedit_char_whitelist=0123456789.,%+-",
            ]
            kwargs: dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "timeout": 90,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(args, **kwargs)
            if proc.returncode != 0:
                continue
            out = (proc.stdout or "").strip()
            if out:
                return proc.stdout or ""
        return ""
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("[gmb-ocr] tesseract CLI failed: %s", exc)
        return ""
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _ints_from_ocr_text(text: str) -> list[int]:
    """Parse integers from OCR output (supports French grouping spaces)."""
    raw = text.replace("\u202f", " ").replace("\xa0", " ")
    candidates: list[int] = []
    for m in re.finditer(r"\d[\d\s.,]*", raw):
        digits = re.sub(r"\D", "", m.group(0))
        if not digits:
            continue
        try:
            n = int(digits)
        except ValueError:
            continue
        if n > 50_000_000:
            continue
        candidates.append(n)
    return candidates


def _pick_headline_int(candidates: list[int]) -> int | None:
    """Drop axis years when other totals exist; prefer the headline-scale total."""
    if not candidates:
        return None
    years = set(range(2015, 2036))
    non_year = [c for c in candidates if c not in years]
    pool = non_year if non_year else candidates
    return max(pool)


def _best_headline_int(text: str) -> int | None:
    """Prefer headline lines over chart axes (e.g. year labels)."""
    lines = (text or "").strip().splitlines() or [text or ""]
    first = _pick_headline_int(_ints_from_ocr_text(lines[0]))
    if first is not None:
        return first
    early = "\n".join(lines[:5])
    return _pick_headline_int(_ints_from_ocr_text(early))


def _binarize(gray: Image.Image) -> Image.Image:
    arr = np.asarray(gray, dtype=np.uint8)
    t = max(120, min(220, int(np.median(arr))))
    out = (arr > t).astype(np.uint8) * 255
    return Image.fromarray(out, mode="L")


def _prepare_variants(gray: Image.Image) -> list[Image.Image]:
    """Several pre-processings so Tesseract survives light UI variance."""
    variants: list[Image.Image] = []
    ac = ImageOps.autocontrast(gray, cutoff=2)
    variants.append(ImageEnhance.Contrast(ac).enhance(1.45))
    variants.append(_binarize(ac))
    variants.append(ImageEnhance.Sharpness(ac).enhance(1.2))
    return variants


def _ocr_region(pytesseract: Any, pil_img: Image.Image, psm: int) -> str:
    cfg = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789.,%+- "
    try:
        return pytesseract.image_to_string(pil_img, lang="fra+eng", config=cfg)
    except Exception:  # noqa: BLE001
        return pytesseract.image_to_string(pil_img, lang="eng", config=cfg)


def headline_int_from_chart_png(path: Path) -> str | None:
    """Return a formatted integer string (e.g. ``702``) or ``None`` if OCR fails."""
    global _WARNED_NO_TESS, _WARNED_NO_PYTESSERACT
    if not path.is_file():
        return None

    pytesseract: Any = None
    try:
        import pytesseract as _pt
        pytesseract = _pt
    except ImportError:
        if not _WARNED_NO_PYTESSERACT:
            logger.info(
                "[gmb-ocr] package pytesseract not installed; using the "
                "Tesseract CLI if found. For in-process OCR: pip install pytesseract"
            )
            _WARNED_NO_PYTESSERACT = True

    tess_bin = _tesseract_executable()
    if pytesseract is None and not tess_bin:
        if not _WARNED_NO_TESS:
            logger.warning(
                "[gmb-ocr] no OCR path: install pytesseract (pip install pytesseract) "
                "and/or install Tesseract OCR and set TESSERACT_CMD in .env."
            )
            _WARNED_NO_TESS = True
        return None

    if pytesseract is not None:
        _configure_tesseract_cmd()

    try:
        img = Image.open(path).convert("L")
    except OSError as exc:
        logger.debug("[gmb-ocr] could not open %s: %s", path, exc)
        return None

    w, h = img.size
    if w < 80 or h < 40:
        return None

    def ocr_string(pil_img: Image.Image, psm: int) -> str:
        if pytesseract is not None:
            try:
                return _ocr_region(pytesseract, pil_img, psm)
            except Exception:
                pass
        if tess_bin:
            return _ocr_tesseract_cli(pil_img, psm, tess_bin)
        return ""

    # Relative crops: tight headline band first, then broader header.
    crops_rel = (
        (0.02, 0.0, 0.98, 0.20),
        (0.04, 0.0, 0.96, 0.32),
        (0.05, 0.0, 0.92, 0.48),
    )
    best: int | None = None
    for x0, y0, x1, y1 in crops_rel:
        box = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
        crop = img.crop(box)
        if crop.width < 8 or crop.height < 6:
            continue
        for prep in _prepare_variants(crop):
            scaled = prep.resize(
                (prep.width * 3, prep.height * 3),
                Image.Resampling.LANCZOS,
            )
            blurred = scaled.filter(ImageFilter.MedianFilter(size=3))
            for psm in (7, 6, 11, 13):
                try:
                    text = ocr_string(blurred, psm)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "[gmb-ocr] OCR psm=%s failed for %s: %s", psm, path, exc
                    )
                    continue
                n = _best_headline_int(text or "")
                if n is not None:
                    best = n
                    break
            if best is not None:
                break
        if best is not None:
            break

    if best is None:
        logger.debug("[gmb-ocr] no headline int for %s", path)
    return str(best) if best is not None else None


def extract_gmb_kpis_from_chart_paths(
    charts: dict[str, str] | None,
    output_dir: Path,
) -> dict[str, str]:
    """Read KPI digits from resolved chart paths, falling back to default filenames."""
    out: dict[str, str] = {}
    charts = charts or {}
    for key, default_name in _GMB_CARD_FILES.items():
        raw = charts.get(key)
        if raw:
            p = Path(str(raw))
            if not p.is_absolute():
                p = (output_dir / p).resolve()
        else:
            p = output_dir / default_name
        val = headline_int_from_chart_png(p)
        if val is not None:
            out[key] = val
    return out


def extract_gmb_kpis_from_card_dir(output_dir: Path) -> dict[str, str]:
    """Build ``{tab_id: formatted_value}`` from card PNGs in ``output_dir``."""
    return extract_gmb_kpis_from_chart_paths({}, output_dir)
