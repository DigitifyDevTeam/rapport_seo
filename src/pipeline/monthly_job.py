"""Run all production clients and upload each report to Google Drive.

    python -m src.pipeline.monthly_job
    python -m src.pipeline.monthly_job --month 2026-04
"""

from __future__ import annotations

import argparse
import logging

from src.config import env, load_production_clients
from src.periods import Period
from src.pipeline.drive_upload import upload_report_artifacts
from src.pipeline.run_monthly import _set_runtime_skip, run_for_client

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
        help="Reporting month YYYY-MM (default: derived from REPORT_CYCLE_DAY in .env)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    # SEO_REPORT_SKIP_CONNECTORS=gmb,clarity skips browsers only; GMB/Clarity APIs
    # still run. Use SEO_REPORT_SKIP_UI_CONNECTORS for the same browser skip.
    skip = (env("SEO_REPORT_SKIP_CONNECTORS") or "").strip()
    if skip:
        api_only = ",".join(
            part.strip()
            for part in skip.split(",")
            if part.strip().lower() not in ("gmb", "clarity"))
        if api_only:
            _set_runtime_skip(api_only)
            logger.info(
                "Skipping API connectors (SEO_REPORT_SKIP_CONNECTORS): %s",
                api_only,
            )
    return run_scheduled_monthly_job(args.month)


if __name__ == "__main__":
    raise SystemExit(main())
