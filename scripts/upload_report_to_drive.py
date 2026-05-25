#!/usr/bin/env python3
"""Upload an existing client report from outputs/ to Google Drive.

Layout under GOOGLE_DRIVE_FOLDER_ID (e.g. rapport_seo)::

    rapport_seo/<project name>/<YYYY-MM>/<client>_<YYYY-MM>_report.pptx

Usage::

    python scripts/upload_report_to_drive.py --client deepcleaning --month 2026-04
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from src.config import get_client
from src.periods import Period
from src.pipeline.drive_upload import (artifacts_for_period,
                                       upload_report_artifacts)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True,
                        help="Client id from config/clients.yaml")
    parser.add_argument("--month", required=True,
                        help="Reporting month YYYY-MM")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    client = get_client(args.client)
    period = Period.parse(args.month)
    artifacts = artifacts_for_period(client, period)

    if not artifacts.pptx_path.is_file():
        logger.error("PPTX not found: %s", artifacts.pptx_path)
        return 1

    if upload_report_artifacts(client, period, artifacts):
        logger.info("Drive upload OK for %s %s", client.id, period.label)
        return 0
    logger.error("Drive upload failed for %s %s", client.id, period.label)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
