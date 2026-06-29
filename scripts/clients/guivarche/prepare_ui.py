"""One-time UI setup for Guivarche (Clarity session + GMB Performance URL).

Usage::

    python scripts/clients/guivarche/prepare_ui.py
    python scripts/clients/guivarche/prepare_ui.py --skip-clarity
    python scripts/clients/guivarche/prepare_ui.py --skip-gmb
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _run(cmd: list[str], *, label: str) -> int:
    print(f"\n=== {label} ===\n")
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT), stdin=sys.stdin)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-clarity", action="store_true")
    parser.add_argument("--skip-gmb", action="store_true")
    args = parser.parse_args()

    code = 0
    node = "node"
    clarity_session = ROOT / "outputs" / "_sessions" / "clarity-guivarche.json"
    if not args.skip_clarity:
        if clarity_session.is_file():
            print(f"\nClarity session already exists: {clarity_session}")
            print("  (skip with --skip-clarity to run GMB only)\n")
        else:
            code = _run(
                [node, str(ROOT / "scripts" / "clients" / "guivarche" / "clarity_ui_login.js")],
                label="Clarity login (Microsoft)",
            )
            if code != 0:
                return code

    if not args.skip_gmb:
        code = _run(
            [
                sys.executable,
                str(ROOT / "scripts" / "capture_gmb_performance_url.py"),
                "guivarche",
                "--show",
            ],
            label="GMB Performance URL (Google)",
        )
        if code != 0:
            return code

    print("\nDone. Re-run the report:")
    print("  python -m src.pipeline.run_monthly --client guivarche --month 2026-05")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
