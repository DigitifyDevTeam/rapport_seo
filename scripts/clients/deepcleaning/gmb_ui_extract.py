"""DeepCleaning — automated GMB (same steps as Origincbd).

Search → fiche screenshot → interactions → période → onglets KPI + PNG.

Usage::

    python scripts/clients/deepcleaning/gmb_ui_extract.py 2026-04
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "gmb_ui_extract.py"
# Same Google account as Origincbd (see config gmb.ui_session_client).
SESSION = ROOT / "outputs" / "_sessions" / "gmb-origincbd.json"
PROFILE = ROOT / "outputs" / "_sessions" / "chrome-profile-gmb-origincbd"

SEARCH_QUERY = "Deep Cleaning Lavage et nettoyage professionnel Colombes"
PROJECT_NAME = "Deep Cleaning"


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

    if not SESSION.is_file():
        print(f"Run first: python scripts/clients/deepcleaning/gmb_ui_prepare.py")
        return 1

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--session", str(SESSION),
        "--out", str(out_dir / "gmb_ui.json"),
        "--screenshot", str(out_dir / "gmb_dashboard.png"),
        "--project-name", PROJECT_NAME,
        "--business-name", SEARCH_QUERY,
        "--location-name", "deepcleaning.fr",
        "--profile", str(PROFILE),
        "--no-auto-period",
        "--period-start", period_start,
        "--period-end", period_end,
    ]
    saved = json.loads(SESSION.read_text(encoding="utf-8")).get("url") or ""
    if "#mpd=" in str(saved):
        cmd.extend(["--dashboard-url", str(saved).strip()])

    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
