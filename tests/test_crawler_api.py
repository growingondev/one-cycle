import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crawler import main as crawler_api


class CrawlerApiTest(unittest.TestCase):
    def setUp(self):
        crawler_api.jobs.clear()
        self.client = TestClient(crawler_api.app)

    def tearDown(self):
        crawler_api.jobs.clear()

    def test_full_collection_uses_common_job_status_contract(self):
        domain_result = {
            "execution_id": "execution-test-1",
            "execution_status": "success",
            "data": [],
        }

        with patch.object(
            crawler_api,
            "crawl_lh_notices",
            return_value=domain_result,
        ):
            accepted = self.client.post("/v1/crawl-jobs")

        self.assertEqual(accepted.status_code, 200)
        job_id = accepted.json()["job_id"]

        status = self.client.get(f"/v1/crawl-jobs/{job_id}")
        self.assertEqual(status.json()["status"], "completed")

        result = self.client.get(
            f"/v1/crawl-jobs/{job_id}/result"
        )
        self.assertEqual(result.json()["result"], domain_result)

    def test_recollect_job_forwards_only_target_filename(self):
        domain_result = {
            "execution_id": "retry-document-1",
            "status": "success",
            "data": {"documents": []},
            "errors": [],
        }

        with patch.object(
            crawler_api,
            "recollect_lh_notice",
            return_value=domain_result,
        ) as recollect:
            accepted = self.client.post(
                "/v1/recollect-jobs",
                json={
                    "source_announcement_id": "NOTICE-1",
                    "detail_url": "https://example.com/notice/1",
                    "target_file_name": "failed-document.hwpx",
                },
            )

        self.assertEqual(accepted.status_code, 200)
        recollect.assert_called_once_with(
            "NOTICE-1",
            "https://example.com/notice/1",
            target_file_name="failed-document.hwpx",
        )
        job_id = accepted.json()["job_id"]
        self.assertEqual(self.client.get(f"/v1/crawl-jobs/{job_id}").json()["status"], "completed")
        self.assertEqual(
            self.client.get(f"/v1/crawl-jobs/{job_id}/result").json()["result"], domain_result
        )

    def test_full_collection_is_rejected_while_another_job_runs(self):
        crawler_api.jobs["running-job"] = {
            "job_id": "running-job",
            "status": "running",
        }

        response = self.client.post("/v1/crawl-jobs")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["error_code"],
            "CRAWLER_JOB_ALREADY_RUNNING",
        )

    def test_scan_route_is_absent(self):
        self.assertEqual(self.client.post("/v1/scan-jobs").status_code, 404)
        self.assertNotIn("/v1/scan-jobs", crawler_api.app.openapi()["paths"])

    def test_recollect_conflicts_with_full_collection(self):
        crawler_api.jobs["full"] = {"status": "running"}
        result = self.client.post("/v1/recollect-jobs", json={
            "source_announcement_id": "A", "detail_url": "https://example.test/A",
        })
        self.assertEqual(result.status_code, 409)

    def test_failed_task_remains_queryable_and_releases_busy_state(self):
        with patch.object(crawler_api, "crawl_lh_notices", side_effect=RuntimeError("failed")):
            accepted = self.client.post("/v1/crawl-jobs")
        job_id = accepted.json()["job_id"]
        self.assertEqual(self.client.get(f"/v1/crawl-jobs/{job_id}").json()["status"], "failed")
        self.assertEqual(self.client.get(f"/v1/crawl-jobs/{job_id}/result").json()["error_code"],
                         "CRAWLER_EXECUTION_FAILED")
        self.assertFalse(crawler_api.is_crawler_busy())


if __name__ == "__main__":
    unittest.main()
