import unittest

from fastapi import HTTPException

from backend.app.api.routes.admin import (
    _raise_crawler_api_error,
)
from backend.app.clients.crawler_client import (
    CrawlerJobFailedError,
)
from backend.app.clients.http_json import (
    InternalServiceHTTPError,
    InternalServiceResponseError,
    InternalServiceUnavailableError,
)


class AdminCrawlerErrorMappingTest(unittest.TestCase):
    def _mapped(self, error: Exception) -> HTTPException:
        with self.assertRaises(HTTPException) as raised:
            _raise_crawler_api_error(error)
        return raised.exception

    def test_busy_error_is_conflict(self):
        mapped = self._mapped(
            InternalServiceHTTPError(
                status_code=409,
                error_code="CRAWLER_JOB_ALREADY_RUNNING",
                message="Crawler is busy.",
            )
        )

        self.assertEqual(mapped.status_code, 409)
        self.assertEqual(
            mapped.detail,
            {
                "error_code": "CRAWLER_JOB_ALREADY_RUNNING",
                "message": "Crawler is busy.",
            },
        )

    def test_unavailable_error_is_service_unavailable(self):
        mapped = self._mapped(
            InternalServiceUnavailableError(
                "connection refused"
            )
        )

        self.assertEqual(mapped.status_code, 503)
        self.assertEqual(
            mapped.detail["error_code"],
            "CRAWLER_SERVICE_UNAVAILABLE",
        )

    def test_invalid_response_is_bad_gateway(self):
        mapped = self._mapped(
            InternalServiceResponseError(
                "invalid crawler response"
            )
        )

        self.assertEqual(mapped.status_code, 502)
        self.assertEqual(
            mapped.detail["error_code"],
            "CRAWLER_RESPONSE_INVALID",
        )

    def test_failed_job_is_bad_gateway(self):
        mapped = self._mapped(
            CrawlerJobFailedError(
                job_id="job-1",
                error_code="CRAWLER_EXECUTION_FAILED",
                message="crawl failed",
            )
        )

        self.assertEqual(mapped.status_code, 502)
        self.assertEqual(
            mapped.detail,
            {
                "error_code": "CRAWLER_EXECUTION_FAILED",
                "message": "crawl failed",
            },
        )


if __name__ == "__main__":
    unittest.main()
