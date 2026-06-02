"""DeepCleaning — manual capture if automated extract cannot open Performance.

Use when ``gmb_ui_extract.py`` finds the fiche but not « Interactions avec les clients ».

Usage::

    python scripts/clients/deepcleaning/gmb_ui_capture.py 2026-04
"""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "gmb_ui_extract.py"
SESSION = ROOT / "outputs" / "_sessions" / "gmb-deepcleaning.json"


def _period_bounds(month: str) -> tuple[str, str]:
    year_s, mon_s = month.split("-", 1)
    year, mon = int(year_s), int(mon_s)
    if mon == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, mon - 1
    start = f"{py:04d}-{pm:02d}-25"
    end = f"{year:04d}-{mon:02d}-25"
    return start, end


def main() -> int:
    month = sys.argv[1] if len(sys.argv) > 1 else "2026-04"
    out_dir = ROOT / "outputs" / "deepcleaning" / month
    out_dir.mkdir(parents=True, exist_ok=True)
    period_start, period_end = _period_bounds(month)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--session", str(SESSION),
        "--out", str(out_dir / "gmb_ui.json"),
        "--screenshot", str(out_dir / "gmb_dashboard.png"),
        "--project-name", "Deep Cleaning",
        # On VPS/Docker we usually don't have system Google Chrome installed.
        # Always force Playwright's bundled Chromium so --show works inside noVNC.
        "--channel", "chromium",
        "--manual",
        "--manual-skip-period",
        "--no-auto-period",
        "--period-start", period_start,
        "--period-end", period_end,
        "--show",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
