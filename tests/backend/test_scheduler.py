import unittest

from backend.app.scheduler import create_scheduler


class SchedulerConfigurationTest(unittest.TestCase):
    def test_incremental_sync_runs_three_times_in_korea_timezone(self):
        scheduler = create_scheduler()
        job = scheduler.get_job("lh_incremental_announcement_sync")

        self.assertIsNotNone(job)
        self.assertEqual(str(scheduler.timezone), "Asia/Seoul")
        self.assertIn("hour='12,15,18'", str(job.trigger))
        self.assertIn("minute='0'", str(job.trigger))
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)
        self.assertEqual(job.misfire_grace_time, 600)


if __name__ == "__main__":
    unittest.main()
