"""Verify GMB session files are ready for unattended Docker reports.

Each production client needs ``outputs/_sessions/gmb-<id>.json`` with a
Performance URL (``#mpd=`` or ``promote/performance``), or
``gmb-performance-<id>.txt``, created via::

    ./scripts/docker_gmb_prepare.sh <client_id>

Exit 0 when all OK, 1 when any client is missing or not on Performance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import gmb_ui_session_path, load_production_clients

SESSIONS = ROOT / "outputs" / "_sessions"


def _session_ready(client_id: str, session_path: Path) -> tuple[bool, str]:
    perf_file = SESSIONS / f"gmb-performance-{client_id}.txt"
    if perf_file.is_file():
        text = perf_file.read_text(encoding="utf-8").strip()
        if "#mpd=" in text or "promote/performance" in text:
            return True, f"OK ({perf_file.name})"

    if not session_path.is_file():
        return False, f"missing {session_path.name}"

    try:
        url = str(json.loads(session_path.read_text(encoding="utf-8")).get("url") or "")
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON: {exc}"

    if "#mpd=" in url or "promote/performance" in url:
        return True, f"OK (#mpd= in {session_path.name})"

    if url.rstrip("/").endswith("business.google.com/locations"):
        return False, (
            f"{session_path.name} stopped at /locations — run "
            f"./scripts/docker_gmb_prepare.sh {client_id}"
        )

    return False, (
        f"{session_path.name} has no Performance URL — run "
        f"./scripts/docker_gmb_prepare.sh {client_id}"
    )


def main() -> int:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    clients = load_production_clients()
    if not clients:
        print("No production clients in config/clients.yaml", file=sys.stderr)
        return 1

    bad = 0
    for client in clients:
        if not (client.gmb or {}):
            continue
        path = gmb_ui_session_path(client, SESSIONS)
        ok, detail = _session_ready(client.id, path)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {client.id}: {detail}")
        if not ok:
            bad += 1

    if bad:
        print(
            "\nFix: SSH to the VPS with TTY and run prepare once per failing client:\n"
            "  chmod +x scripts/docker_gmb_prepare.sh\n"
            "  ./scripts/docker_gmb_prepare.sh deepcleaning\n",
            file=sys.stderr,
        )
        return 1
    print("\nAll GMB sessions ready for automated monthly capture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
