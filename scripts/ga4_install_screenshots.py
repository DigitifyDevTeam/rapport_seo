"""Copy GA4 dashboard screenshots into a monthly report folder.

Use when capture automation is not set up yet, or to refresh cards for one month.

Example::

    python scripts/ga4_install_screenshots.py --client origincbd --month 2026-04 \\
        --traffic-top path/to/ga4_wide_capture.png
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import PROJECT_ROOT, get_client
from src.periods import Period
from src.pipeline.run_monthly import (  # noqa: E402
    _GA4_UI_CAPTURE_VERSION,
    _GA4_UI_FILE_MAP,
    _ga4_property_id,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument(
        "--traffic-top",
        help="Wide PNG with Visites mensuelles + Identifiant du pays (GA4 UI).",
    )
    parser.add_argument(
        "--visites",
        help="Optional separate PNG for Visites mensuelles only.",
    )
    parser.add_argument(
        "--country",
        help="Optional separate PNG for Identifiant du pays only.",
    )
    parser.add_argument(
        "--also-client-assets",
        action="store_true",
        help="Also save copies under scripts/clients/<client>/ga4_assets/.",
    )
    args = parser.parse_args(argv)

    client = get_client(args.client)
    period = Period.parse(args.month)
    out_dir = client.output_dir / period.label
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = {
        "traffic_top": args.traffic_top,
        "visites": args.visites,
        "country": args.country,
    }
    copied: dict[str, str] = {}
    for key, raw in mapping.items():
        if not raw:
            continue
        src = Path(raw).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(src)
        dest = out_dir / _GA4_UI_FILE_MAP[key]
        shutil.copy2(src, dest)
        copied[key] = str(dest)
        print(f"copied {src.name} -> {dest}")

    if not copied:
        parser.error("Provide at least one of --traffic-top, --visites, --country")

    payload = {
        "capture_version": _GA4_UI_CAPTURE_VERSION,
        "captured_at": datetime.now().isoformat(),
        "report_month": period.label,
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "property_id": _ga4_property_id(client),
        "source": "manual_install",
        "charts": copied,
    }
    json_path = out_dir / "ga4_ui.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {json_path}")

    if args.also_client_assets:
        assets_dir = PROJECT_ROOT / "scripts" / "clients" / client.id / "ga4_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for key, dest in copied.items():
            shutil.copy2(dest, assets_dir / _GA4_UI_FILE_MAP[key])
            print(f"saved default asset {assets_dir / _GA4_UI_FILE_MAP[key]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
