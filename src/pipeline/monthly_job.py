"""Scheduled monthly job: all production clients + Google Drive upload.

Used by cron/systemd on the VPS (day 26 by default)::

    python -m src.pipeline.monthly_job

Manual run for a specific month::

    python -m src.pipeline.monthly_job --month 2026-04
"""

from __future__ import annotations

import argparse
import logging

from src.config import load_production_clients
from src.periods import Period
from src.pipeline.drive_upload import upload_report_artifacts
from src.pipeline.run_monthly import run_for_client

logger = logging.getLogger(__name__)


def run_scheduled_monthly_job(month: str | None = None) -> int:
    """Run reports for production clients and upload artifacts to Drive."""
    period = Period.parse(month) if month else Period.for_scheduled_run()
    logger.info("Monthly job starting for period %s", period.label)

    failures = 0
    for client in load_production_clients():
        logger.info("=== Client %s (%s) ===", client.id, client.name)
        try:
            artifacts = run_for_client(client, period)
        except Exception:  # noqa: BLE001
            logger.exception("Report failed for %s", client.id)
            failures += 1
            continue
        try:
            upload_report_artifacts(client, period, artifacts)
        except Exception:  # noqa: BLE001
            logger.exception("Drive upload failed for %s", client.id)
            failures += 1

    if failures:
        logger.error("Monthly job finished with %s failure(s)", failures)
        return 1
    logger.info("Monthly job finished successfully for %s", period.label)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        help="Reporting month YYYY-MM (default: current month on schedule day)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return run_scheduled_monthly_job(args.month)


if __name__ == "__main__":
    raise SystemExit(main())
