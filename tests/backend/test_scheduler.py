import unittest
from unittest.mock import patch

from backend.app.scheduler import create_scheduler, run_scheduled_sync
from backend.app.services.pipeline_gateway import CollectionAlreadyRunningError


class SchedulerConfigurationTest(unittest.TestCase):
    def test_full_collection_runs_three_times_in_korea_timezone(self):
        scheduler = create_scheduler()
        job = scheduler.get_job("lh_full_announcement_collection")

        self.assertIsNotNone(job)
        self.assertEqual(str(scheduler.timezone), "Asia/Seoul")
        self.assertIn("hour='12,15,18'", str(job.trigger))
        self.assertIn("minute='0'", str(job.trigger))
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)
        self.assertEqual(job.misfire_grace_time, 600)
        self.assertEqual(job.func, run_scheduled_sync)
        self.assertIsNone(scheduler.get_job("lh_incremental_announcement_sync"))

    @patch("backend.app.scheduler.collect_announcements")
    def test_scheduler_calls_full_collection(self, collect):
        collect.return_value = {"status": "success"}
        with self.assertLogs("backend.app.scheduler", level="INFO") as logs:
            run_scheduled_sync()
        collect.assert_called_once_with()
        self.assertIn("finished", logs.output[0])

    @patch("backend.app.scheduler.collect_announcements")
    def test_pipeline_failure_result_is_not_logged_as_success(self, collect):
        collect.return_value = {"status": "failed"}
        with self.assertLogs("backend.app.scheduler", level="ERROR"):
            run_scheduled_sync()

    @patch("backend.app.scheduler.collect_announcements")
    def test_busy_collection_is_skipped(self, collect):
        collect.side_effect = CollectionAlreadyRunningError("busy")
        with self.assertLogs("backend.app.scheduler", level="INFO") as logs:
            run_scheduled_sync()
        self.assertIn("skipped", logs.output[0])

    @patch("backend.app.scheduler.collect_announcements")
    def test_exception_does_not_stop_scheduler(self, collect):
        collect.side_effect = RuntimeError("worker unavailable")
        with self.assertLogs("backend.app.scheduler", level="ERROR"):
            run_scheduled_sync()


if __name__ == "__main__":
    unittest.main()
