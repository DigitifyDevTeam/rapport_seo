"""Verify GMB session files are ready for unattended Docker reports.

Each production client needs ``outputs/_sessions/gmb-<id>.json`` with a
Performance URL (``#mpd=`` or ``promote/performance``), saved on Windows::

    python scripts/clients/<client>/gmb_ui_prepare.py

Then copy ``gmb-<client>.json`` to the VPS. Same model as Origincbd.

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
            f"{session_path.name} stopped at /locations — on Windows run "
            f"python scripts/clients/{client_id}/gmb_ui_prepare.py "
            f"(wait for Performance + #mpd=)"
        )

    return False, (
        f"{session_path.name} has no Performance URL — on Windows run "
        f"python scripts/clients/{client_id}/gmb_ui_prepare.py"
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
            "\nFix (one-time per failing client, on your PC):\n"
            "  python scripts/clients/<client>/gmb_ui_prepare.py\n"
            "  Copy outputs/_sessions/gmb-<client>.json to the VPS\n",
            file=sys.stderr,
        )
        return 1
    print("\nAll GMB sessions ready for automated monthly capture on the VPS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
