"""Test Microsoft Clarity Data Export API for a single client.

Usage:
  python scripts/clarity_test.py --client origincbd
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import get_client  # noqa: E402
from src.connectors import clarity as clarity_connector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, help="Client id, e.g. origincbd")
    args = parser.parse_args()

    client = get_client(args.client)

    # Connector ignores dates (Clarity only supports last 1-3 days), but pass sane values.
    end = date.today()
    start = end - timedelta(days=30)

    payload = clarity_connector.fetch(client, start, end)
    if not payload:
        print("No data returned (missing project_id or token, or request failed).")
        return 2

    df = payload.get("insights")
    if df is None:
        print("No 'insights' key in payload.")
        return 3

    print(f"OK: received insights rows={len(df)} cols={len(df.columns)}")
    if len(df.columns) > 0:
        print("Columns:", ", ".join(map(str, df.columns[:30])))

    import json as _json
    out_path = _PROJECT_ROOT / "outputs" / "_debug" / "clarity_inspect.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(df.to_json(orient="records", force_ascii=False),
                        encoding="utf-8")
    print(f"Wrote raw structure to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

