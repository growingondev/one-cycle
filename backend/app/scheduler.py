from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from backend.app.services.pipeline_gateway import (
    CollectionAlreadyRunningError,
    collect_announcements,
)

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def run_scheduled_sync() -> None:
    """기존 함수명은 유지하되 전체 수집·문서 처리·검증·전환을 실행한다."""
    try:
        result = collect_announcements()
        if result.get("status") != "success":
            LOGGER.error("Full announcement collection did not succeed: %s", result)
            return
        LOGGER.info(
            "Full announcement collection finished: %s",
            result,
        )
    except CollectionAlreadyRunningError:
        LOGGER.info("Full announcement collection skipped: collection already running")
    except Exception:
        LOGGER.exception("Full announcement collection failed")


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(
        run_scheduled_sync,
        trigger="cron",
        hour="12,15,18",
        minute=0,
        id="lh_full_announcement_collection",
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
