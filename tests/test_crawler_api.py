import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crawler import main as crawler_api


class CrawlerScanApiTest(unittest.TestCase):
    def setUp(self):
        crawler_api.jobs.clear()
        self.client = TestClient(crawler_api.app)

    def tearDown(self):
        crawler_api.jobs.clear()

    def test_scan_job_uses_common_job_status_contract(self):
        domain_result = {
            "execution_id": "scan-test-1",
            "execution_status": "success",
            "notices": [],
        }

        with patch.object(
            crawler_api,
            "scan_lh_notice_list",
            return_value=domain_result,
        ):
            accepted = self.client.post("/v1/scan-jobs")

        self.assertEqual(accepted.status_code, 200)
        job_id = accepted.json()["job_id"]

        status = self.client.get(f"/v1/crawl-jobs/{job_id}")
        self.assertEqual(status.json()["status"], "completed")

        result = self.client.get(
            f"/v1/crawl-jobs/{job_id}/result"
        )
        self.assertEqual(result.json()["result"], domain_result)

    def test_scan_job_is_rejected_while_another_job_runs(self):
        crawler_api.jobs["running-job"] = {
            "job_id": "running-job",
            "status": "running",
        }

        response = self.client.post("/v1/scan-jobs")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["error_code"],
            "CRAWLER_JOB_ALREADY_RUNNING",
        )


if __name__ == "__main__":
    unittest.main()
