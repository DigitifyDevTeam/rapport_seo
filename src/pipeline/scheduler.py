"""APScheduler entry point.

Generates a report for every client on the 5th of each month at 06:00 in
the local timezone. Run as a long-lived process or register the module as
a Windows Scheduled Task / cron job.

Usage::

    python -m src.pipeline.scheduler
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import load_clients
from src.periods import Period
from src.pipeline.run_monthly import run_for_client

logger = logging.getLogger(__name__)


def run_monthly_job() -> None:
    period = Period.previous_complete()
    logger.info("Running monthly job for %s", period.label)
    for client in load_clients():
        try:
            run_for_client(client, period)
        except Exception:  # noqa: BLE001
            logger.exception("Report failed for %s", client.id)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    scheduler = BlockingScheduler()
    scheduler.add_job(run_monthly_job,
                       CronTrigger(day=5, hour=6, minute=0),
                       id="monthly-seo-report",
                       replace_existing=True)
    logger.info("Scheduler started; reports will run on the 5th at 06:00")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
