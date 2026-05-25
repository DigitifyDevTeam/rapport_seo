"""Digitify — GMB session is shared with Origincbd (same Google account).

Do not create ``gmb-digitify.json``. Run Origincbd prepare once::

    python scripts/clients/origincbd/gmb_ui_prepare.py

Then run reports for digitify / deepcleaning normally.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORIGINCBD_PREPARE = ROOT / "scripts" / "clients" / "origincbd" / "gmb_ui_prepare.py"


def main() -> int:
    print("Digitify uses the same Google account as Origincbd.")
    print("Launching Origincbd GMB session capture (shared cookies)…")
    print("")
    return subprocess.call([sys.executable, str(ORIGINCBD_PREPARE)], cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
