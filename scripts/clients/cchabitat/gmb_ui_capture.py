"""CC Habitat — manual GMB capture (noVNC on VPS, separate Gmail).

Usage::

    python scripts/clients/cchabitat/gmb_ui_capture.py 2026-05
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "gmb_ui_extract.py"
SESSION = ROOT / "outputs" / "_sessions" / "gmb-cchabitat.json"


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
    out_dir = ROOT / "outputs" / "cchabitat" / month
    out_dir.mkdir(parents=True, exist_ok=True)
    period_start, period_end = _period_bounds(month)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--session", str(SESSION),
        "--out", str(out_dir / "gmb_ui.json"),
        "--screenshot", str(out_dir / "gmb_dashboard.png"),
        "--project-name", "Concept Confort Habitat",
        "--business-name", "Concept Confort Habitat couvreur Val-de-Marne",
        "--location-name", "cc-habitat.com",
        "--channel", "chromium",
        "--manual",
        "--manual-skip-period",
        "--no-auto-period",
        "--period-start", period_start,
        "--period-end", period_end,
        "--show",
        "--client-id", "cchabitat",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
