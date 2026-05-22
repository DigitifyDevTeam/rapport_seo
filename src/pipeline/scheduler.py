"""APScheduler entry point (optional long-lived process on the VPS).

Prefer **systemd timer** or **cron** calling ``python -m src.pipeline.monthly_job``
so the server does not need a 24/7 Python process.

Usage::

    python -m src.pipeline.scheduler
"""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.periods import schedule_day_of_month
from src.pipeline.monthly_job import run_scheduled_monthly_job

logger = logging.getLogger(__name__)


def _schedule_hour() -> int:
    raw = (os.environ.get("SEO_REPORT_SCHEDULE_HOUR") or "6").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 6


def _schedule_minute() -> int:
    raw = (os.environ.get("SEO_REPORT_SCHEDULE_MINUTE") or "0").strip()
    try:
        return max(0, min(59, int(raw)))
    except ValueError:
        return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    day = schedule_day_of_month()
    hour = _schedule_hour()
    minute = _schedule_minute()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_scheduled_monthly_job,
        CronTrigger(day=day, hour=hour, minute=minute),
        id="monthly-seo-report",
        replace_existing=True,
    )
    logger.info(
        "Scheduler started; reports will run on day %s at %02d:%02d",
        day,
        hour,
        minute,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
