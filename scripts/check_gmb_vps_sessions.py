"""Verify GMB session files are ready for unattended Docker reports.

Each client needs a Performance URL (``#mpd=``). Same Google account (DeepCleaning,
Origincbd, Digitify) can share ``gmb-deepcleaning.json`` plus per-brand sidecars::

    python scripts/gmb_ui_prepare_shared_account.py

Exit 0 when all OK, 1 when any client is missing or not on Performance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import ClientConfig, gmb_ui_session_path, load_production_clients

SESSIONS = ROOT / "outputs" / "_sessions"


def _shared_session_owner(client: ClientConfig) -> str | None:
    shared = str((client.gmb or {}).get("ui_session_client") or "").strip()
    if not shared or shared == client.id:
        return None
    own = SESSIONS / f"gmb-{client.id}.json"
    if own.is_file():
        return None
    return shared


def _session_ready(client: ClientConfig, session_path: Path) -> tuple[bool, str]:
    client_id = client.id
    perf_file = SESSIONS / f"gmb-performance-{client_id}.txt"
    shared_owner = _shared_session_owner(client)

    if perf_file.is_file():
        text = perf_file.read_text(encoding="utf-8").strip()
        if "#mpd=" in text or "promote/performance" in text:
            if shared_owner:
                return True, (
                    f"OK (shared gmb-{shared_owner}.json + {perf_file.name})"
                )
            return True, f"OK ({perf_file.name})"

    if not session_path.is_file():
        if shared_owner:
            master = SESSIONS / f"gmb-{shared_owner}.json"
            if not master.is_file():
                return False, (
                    f"missing gmb-{shared_owner}.json and {perf_file.name} — run "
                    "python scripts/gmb_ui_prepare_shared_account.py"
                )
            return False, (
                f"missing {perf_file.name} — run "
                f"python scripts/capture_gmb_performance_url.py {client_id} --show"
            )
        return False, f"missing {session_path.name}"

    try:
        url = str(json.loads(session_path.read_text(encoding="utf-8")).get("url") or "")
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON: {exc}"

    if "#mpd=" in url or "promote/performance" in url:
        if shared_owner and client_id != shared_owner and not perf_file.is_file():
            return False, (
                f"missing {perf_file.name} — run "
                f"bash scripts/gmb_ui_prepare_vnc_client.sh {client_id}"
            )
        return True, f"OK (#mpd= in {session_path.name})"

    if url.rstrip("/").endswith("business.google.com/locations"):
        return False, (
            f"{session_path.name} stopped at /locations — run "
            "python scripts/gmb_ui_prepare_shared_account.py "
            "(wait for Performance + #mpd=)"
        )

    return False, (
        f"{session_path.name} has no Performance URL — run "
        "python scripts/gmb_ui_prepare_shared_account.py"
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
        ok, detail = _session_ready(client, path)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {client.id}: {detail}")
        if not ok:
            bad += 1

    if bad:
        print(
            "\nFix (one-time, same Google account):\n"
            "  python scripts/gmb_ui_prepare_shared_account.py\n"
            "  # or on VPS VNC: ./scripts/gmb_ui_prepare_vnc.sh\n"
            "\nCopy to the VPS:\n"
            "  outputs/_sessions/gmb-deepcleaning.json\n"
            "  outputs/_sessions/gmb-performance-origincbd.txt\n"
            "  outputs/_sessions/gmb-performance-digitify.txt\n"
            "  outputs/_sessions/gmb-performance-guivarche.txt\n"
            "\nCC Habitat (separate Google account):\n"
            "  bash scripts/gmb_ui_prepare_vnc_client.sh cchabitat\n"
            "\nRemove stale gmb-origincbd.json / gmb-digitify.json if present "
            "(they block shared-session fallback).\n",
            file=sys.stderr,
        )
        return 1
    print("\nAll GMB sessions ready for automated monthly capture on the VPS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
