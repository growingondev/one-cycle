from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from backend.app.services.collection_sync_service import (
    run_incremental_sync,
)

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def run_scheduled_sync() -> None:
    try:
        result = run_incremental_sync()
        LOGGER.info(
            "Incremental announcement sync finished: %s",
            result,
        )
    except Exception:
        LOGGER.exception("Incremental announcement sync failed")


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(
        run_scheduled_sync,
        trigger="cron",
        hour="12,15,18",
        minute=0,
        id="lh_incremental_announcement_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    return scheduler


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    scheduler = create_scheduler()
    LOGGER.info(
        "Announcement scheduler started (Asia/Seoul: 12:00, 15:00, 18:00)"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
