"""Convert a generated ``.pptx`` report into a PDF.

Two backends are supported:

1. **LibreOffice** (``soffice`` on PATH) — works on Linux, macOS and
   Windows when LibreOffice is installed. This is the default because it
   does not depend on Microsoft Office.
2. **Microsoft PowerPoint via COM** — used as a fallback on Windows when
   LibreOffice is not available and ``pywin32`` is installed.

If neither backend is available the function logs a warning and returns
``None``; the PowerPoint file remains usable as-is.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def export(pptx_path: Path, pdf_path: Path | None = None) -> Path | None:
    pptx_path = Path(pptx_path)
    pdf_path = Path(pdf_path) if pdf_path else pptx_path.with_suffix(".pdf")

    if _try_libreoffice(pptx_path, pdf_path):
        return pdf_path
    if os.name == "nt" and _try_powerpoint_com(pptx_path, pdf_path):
        return pdf_path

    logger.warning(
        "No PDF backend available. Install LibreOffice or pywin32 to enable "
        "automatic PDF export.")
    return None


def _try_libreoffice(pptx_path: Path, pdf_path: Path) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir",
             str(pdf_path.parent), str(pptx_path)],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("LibreOffice conversion failed: %s", exc.stderr)
        return False
    produced = pdf_path.parent / (pptx_path.stem + ".pdf")
    if produced != pdf_path and produced.exists():
        produced.replace(pdf_path)
    return pdf_path.exists()


def _try_powerpoint_com(pptx_path: Path, pdf_path: Path) -> bool:
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        powerpoint = win32com.client.Dispatch("Powerpoint.Application")
        powerpoint.Visible = 1
        deck = powerpoint.Presentations.Open(str(pptx_path), WithWindow=False)
        deck.SaveAs(str(pdf_path), 32)
        deck.Close()
        powerpoint.Quit()
    except Exception as exc:  # noqa: BLE001
        logger.error("PowerPoint COM conversion failed: %s", exc)
        return False
    return pdf_path.exists()
