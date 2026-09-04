import unittest
from unittest.mock import call, patch

from backend.app.clients import crawler_client
from backend.app.clients.crawler_client import (
    CrawlerJobFailedError,
    CrawlerJobTimeoutError,
)
from backend.app.clients.http_json import (
    InternalServiceResponseError,
)
from backend.app.core.config import settings


class CrawlerClientTest(unittest.TestCase):
    def _settings(self, **overrides):
        values = {
            "crawler_service_base_url": (
                "http://crawler:8000"
            ),
            "crawler_service_timeout_seconds": 30.0,
            "crawler_job_timeout_seconds": 60.0,
            "crawler_job_poll_interval_seconds": 1.0,
        }
        values.update(overrides)
        return patch.multiple(settings, **values)

    def test_full_crawl_polls_and_returns_result(self):
        domain_result = {
            "execution_id": "execution-1",
            "execution_status": "success",
            "data": [],
        }

        with (
            self._settings(),
            patch.object(
                crawler_client,
                "post_json",
                return_value={
                    "job_id": "job-1",
                    "status": "queued",
                },
            ) as post_json,
            patch.object(
                crawler_client,
                "get_json",
                side_effect=[
                    {
                        "job_id": "job-1",
                        "status": "queued",
                    },
                    {
                        "job_id": "job-1",
                        "status": "running",
                    },
                    {
                        "job_id": "job-1",
                        "status": "completed",
                    },
                    {
                        "job_id": "job-1",
                        "status": "completed",
                        "result": domain_result,
                    },
                ],
            ) as get_json,
            patch.object(
                crawler_client.time,
                "sleep",
            ) as sleep,
        ):
            result = crawler_client.crawl_announcements()

        self.assertEqual(result, domain_result)
        post_json.assert_called_once_with(
            url="http://crawler:8000/v1/crawl-jobs",
            payload={},
            timeout_seconds=30.0,
        )
        self.assertEqual(
            get_json.call_args_list,
            [
                call(
                    url=(
                        "http://crawler:8000"
                        "/v1/crawl-jobs/job-1"
                    ),
                    timeout_seconds=30.0,
                ),
                call(
                    url=(
                        "http://crawler:8000"
                        "/v1/crawl-jobs/job-1"
                    ),
                    timeout_seconds=30.0,
                ),
                call(
                    url=(
                        "http://crawler:8000"
                        "/v1/crawl-jobs/job-1"
                    ),
                    timeout_seconds=30.0,
                ),
                call(
                    url=(
                        "http://crawler:8000"
                        "/v1/crawl-jobs/job-1/result"
                    ),
                    timeout_seconds=30.0,
                ),
            ],
        )
        self.assertEqual(sleep.call_count, 2)

    def test_recollect_sends_expected_payload(self):
        domain_result = {
            "execution_id": "recollect-1",
            "status": "success",
            "source_announcement_id": "NOTICE-1",
        }

        with (
            self._settings(),
            patch.object(
                crawler_client,
                "post_json",
                return_value={
                    "job_id": "job-2",
                    "status": "queued",
                },
            ) as post_json,
            patch.object(
                crawler_client,
                "get_json",
                side_effect=[
                    {
                        "job_id": "job-2",
                        "status": "completed",
                    },
                    {
                        "job_id": "job-2",
                        "status": "completed",
                        "result": domain_result,
                    },
                ],
            ),
        ):
            result = crawler_client.recollect_announcement(
                source_announcement_id="NOTICE-1",
                detail_url="https://example.com/notice/1",
            )

        self.assertEqual(result, domain_result)
        post_json.assert_called_once_with(
            url="http://crawler:8000/v1/recollect-jobs",
            payload={
                "source_announcement_id": "NOTICE-1",
                "detail_url": "https://example.com/notice/1",
            },
            timeout_seconds=30.0,
        )

    def test_failed_job_preserves_error_contract(self):
        with (
            self._settings(),
            patch.object(
                crawler_client,
                "post_json",
                return_value={
                    "job_id": "job-3",
                    "status": "queued",
                },
            ),
            patch.object(
                crawler_client,
                "get_json",
                return_value={
                    "job_id": "job-3",
                    "status": "failed",
                    "error_code": "CRAWLER_EXECUTION_FAILED",
                    "message": "crawl failed",
                },
            ),
        ):
            with self.assertRaises(
                CrawlerJobFailedError
            ) as raised:
                crawler_client.crawl_announcements()

        self.assertEqual(
            raised.exception.job_id,
            "job-3",
        )
        self.assertEqual(
            raised.exception.error_code,
            "CRAWLER_EXECUTION_FAILED",
        )
        self.assertEqual(
            raised.exception.message,
            "crawl failed",
        )

    def test_job_timeout_is_reported(self):
        with (
            self._settings(
                crawler_job_timeout_seconds=1.0,
            ),
            patch.object(
                crawler_client,
                "post_json",
                return_value={
                    "job_id": "job-4",
                    "status": "queued",
                },
            ),
            patch.object(
                crawler_client,
                "get_json",
                return_value={
                    "job_id": "job-4",
                    "status": "running",
                },
            ),
            patch.object(
                crawler_client.time,
                "monotonic",
                side_effect=[100.0, 102.0],
            ),
        ):
            with self.assertRaises(
                CrawlerJobTimeoutError
            ):
                crawler_client.crawl_announcements()

    def test_completed_job_requires_result_object(self):
        with (
            self._settings(),
            patch.object(
                crawler_client,
                "post_json",
                return_value={
                    "job_id": "job-5",
                    "status": "queued",
                },
            ),
            patch.object(
                crawler_client,
                "get_json",
                side_effect=[
                    {
                        "job_id": "job-5",
                        "status": "completed",
                    },
                    {
                        "job_id": "job-5",
                        "status": "completed",
                    },
                ],
            ),
        ):
            with self.assertRaises(
                InternalServiceResponseError
            ):
                crawler_client.crawl_announcements()


if __name__ == "__main__":
    unittest.main()
