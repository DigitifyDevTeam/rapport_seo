"""One-time GA4 login for Guivarche.

    python scripts/clients/guivarche/ga4_ui_prepare.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ga4_ui_prepare.py"


def main() -> int:
    return subprocess.call(
        [sys.executable, str(SCRIPT), "--client", "guivarche"],
        cwd=str(ROOT),
    )


if __name__ == "__main__":
    raise SystemExit(main())
