"""DeepCleaning — one-time Google Business Profile login.

Usage::

    python scripts/clients/deepcleaning/gmb_ui_login.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "outputs" / "_sessions" / "gmb-deepcleaning.json"
PROFILE = ROOT / "outputs" / "_sessions" / "chrome-profile-gmb"
SCRIPT = ROOT / "scripts" / "gmb_ui_login.py"


def main() -> int:
    print("Alias for gmb_ui_prepare.py — use: python scripts/clients/deepcleaning/gmb_ui_prepare.py")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(SESSION),
        "--profile", str(PROFILE),
        "--start-url", "https://business.google.com/locations",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
