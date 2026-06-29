"""One Google login for DeepCleaning, Origincbd, Digitify, and Guivarche GMB sessions.

Same Google account: save cookies once in ``gmb-deepcleaning.json``, then capture
each brand's Performance URL (``#mpd=``) into ``gmb-performance-<client>.txt``.

Usage::

    python scripts/gmb_ui_prepare_shared_account.py
    python scripts/gmb_ui_prepare_shared_account.py --skip-master

On the VPS (VNC)::

    ./scripts/gmb_ui_prepare_vnc.sh

Copy to the server::

    outputs/_sessions/gmb-deepcleaning.json
    outputs/_sessions/gmb-performance-origincbd.txt
    outputs/_sessions/gmb-performance-digitify.txt
    outputs/_sessions/gmb-performance-guivarche.txt

Do **not** upload ``gmb-origincbd.json`` / ``gmb-digitify.json`` / ``gmb-guivarche.json`` unless you want a
dedicated session (they block shared-session fallback).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "outputs" / "_sessions"

MASTER_CLIENT = "deepcleaning"
PERF_URL_CLIENTS = ("origincbd", "digitify", "guivarche")
DEFAULT_CLIENTS = (MASTER_CLIENT, *PERF_URL_CLIENTS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-master",
        action="store_true",
        help="Skip DeepCleaning prepare (cookies already in gmb-deepcleaning.json).",
    )
    parser.add_argument(
        "--clients",
        default=",".join(DEFAULT_CLIENTS),
        help="Comma-separated client ids (default: deepcleaning,origincbd,digitify,guivarche).",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="Do not run check_gmb_vps_sessions.py at the end.",
    )
    return parser.parse_args()


def _run(cmd: list[str], *, step: str) -> int:
    print(f"\n=== {step} ===\n")
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    args = _parse_args()
    clients = [c.strip() for c in args.clients.split(",") if c.strip()]
    SESSIONS.mkdir(parents=True, exist_ok=True)

    print("Shared GMB prepare (one Google account)")
    print("  Master session:", SESSIONS / f"gmb-{MASTER_CLIENT}.json")
    for cid in PERF_URL_CLIENTS:
        if cid in clients:
            print(f"  Performance URL: {SESSIONS / f'gmb-performance-{cid}.txt'}")

    if MASTER_CLIENT in clients and not args.skip_master:
        master_script = (
            ROOT / "scripts" / "clients" / MASTER_CLIENT / "gmb_ui_prepare.py"
        )
        if not master_script.is_file():
            print(f"Missing {master_script}", file=sys.stderr)
            return 1
        rc = _run([sys.executable, str(master_script)], step=f"Login + {MASTER_CLIENT} Performance")
        if rc != 0:
            print("Master prepare failed.", file=sys.stderr)
            return rc
    elif args.skip_master:
        master_json = SESSIONS / f"gmb-{MASTER_CLIENT}.json"
        perf_only = MASTER_CLIENT not in clients and any(
            c in clients for c in PERF_URL_CLIENTS
        )
        if not master_json.is_file():
            if perf_only:
                print(
                    f"Note: {master_json.name} missing — continuing (browser login via VPS profile).",
                )
                print(
                    "Run deepcleaning prepare later so monthly reports have saved cookies.",
                )
            else:
                print(f"Missing {master_json}", file=sys.stderr)
                print(
                    "Run: bash scripts/gmb_ui_prepare_vnc_client.sh deepcleaning",
                    file=sys.stderr,
                )
                return 1
        elif master_json.is_file():
            print(f"Using existing {master_json.name}")

    for client_id in PERF_URL_CLIENTS:
        if client_id not in clients:
            continue
        capture = ROOT / "scripts" / "capture_gmb_performance_url.py"
        rc = _run(
            [sys.executable, str(capture), client_id, "--show"],
            step=f"Performance URL for {client_id}",
        )
        if rc != 0:
            print(f"Performance URL capture failed for {client_id}.", file=sys.stderr)
            return rc

    if not args.no_check:
        check = ROOT / "scripts" / "check_gmb_vps_sessions.py"
        _run([sys.executable, str(check)], step="Verify sessions")

    print("\nDone. Copy to the VPS:")
    print(f"  {SESSIONS / f'gmb-{MASTER_CLIENT}.json'}")
    for cid in PERF_URL_CLIENTS:
        if cid in clients:
            print(f"  {SESSIONS / f'gmb-performance-{cid}.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
