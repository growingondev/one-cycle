import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib import error

from backend.app.clients.http_json import (
    InternalServiceHTTPError,
    InternalServiceResponseError,
    InternalServiceUnavailableError,
    get_json,
    post_json,
)


class InternalHttpJsonClientTest(unittest.TestCase):
    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_post_json_returns_json_object(
        self,
        urlopen,
    ):
        response = MagicMock()
        response.read.return_value = (
            b'{"status":"ok","value":123}'
        )

        urlopen.return_value.__enter__.return_value = (
            response
        )

        result = post_json(
            url="http://rag:8000/v1/test",
            payload={
                "message": "hello",
            },
            timeout_seconds=10,
        )

        self.assertEqual(
            result,
            {
                "status": "ok",
                "value": 123,
            },
        )

        request_object = urlopen.call_args.args[0]

        self.assertEqual(
            request_object.get_method(),
            "POST",
        )

        self.assertEqual(
            request_object.get_header(
                "Content-type"
            ),
            "application/json",
        )

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_post_json_preserves_service_error_contract(
        self,
        urlopen,
    ):
        body = (
            b'{'
            b'"error":{'
            b'"code":"RAG_EMBEDDING_UNAVAILABLE",'
            b'"message":"Embedding service unavailable."'
            b'}'
            b'}'
        )

        urlopen.side_effect = error.HTTPError(
            url="http://rag:8000/v1/rag/answer",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=BytesIO(body),
        )

        with self.assertRaises(
            InternalServiceHTTPError
        ) as raised:
            post_json(
                url=(
                    "http://rag:8000"
                    "/v1/rag/answer"
                ),
                payload={
                    "announcement_id": 1,
                    "question": "test",
                },
                timeout_seconds=10,
            )

        self.assertEqual(
            raised.exception.status_code,
            503,
        )
        self.assertEqual(
            raised.exception.error_code,
            "RAG_EMBEDDING_UNAVAILABLE",
        )
        self.assertEqual(
            raised.exception.message,
            "Embedding service unavailable.",
        )

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_post_json_rejects_invalid_json_response(
        self,
        urlopen,
    ):
        response = MagicMock()
        response.read.return_value = (
            b"this-is-not-json"
        )

        urlopen.return_value.__enter__.return_value = (
            response
        )

        with self.assertRaises(
            InternalServiceResponseError
        ):
            post_json(
                url="http://worker:8000/v1/test",
                payload={
                    "document_id": 1,
                },
                timeout_seconds=10,
            )

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_post_json_maps_connection_failure(
        self,
        urlopen,
    ):
        urlopen.side_effect = error.URLError(
            "connection refused"
        )

        with self.assertRaises(
            InternalServiceUnavailableError
        ):
            post_json(
                url="http://worker:8000/v1/test",
                payload={
                    "document_id": 1,
                },
                timeout_seconds=10,
            )

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_get_json_returns_json_object(
        self,
        urlopen,
    ):
        response = MagicMock()
        response.read.return_value = (
            b'{"job_id":"job-1","status":"running"}'
        )
        urlopen.return_value.__enter__.return_value = (
            response
        )

        result = get_json(
            url="http://crawler:8000/v1/crawl-jobs/job-1",
            timeout_seconds=10,
        )

        self.assertEqual(result["status"], "running")
        request_object = urlopen.call_args.args[0]
        self.assertEqual(request_object.get_method(), "GET")

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_fastapi_detail_error_contract(
        self,
        urlopen,
    ):
        body = (
            b'{"detail":{'
            b'"error_code":"CRAWLER_JOB_ALREADY_RUNNING",'
            b'"message":"Crawler is busy."}}'
        )
        urlopen.side_effect = error.HTTPError(
            url="http://crawler:8000/v1/crawl-jobs",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=BytesIO(body),
        )

        with self.assertRaises(
            InternalServiceHTTPError
        ) as raised:
            post_json(
                url="http://crawler:8000/v1/crawl-jobs",
                payload={},
                timeout_seconds=10,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.error_code,
            "CRAWLER_JOB_ALREADY_RUNNING",
        )
        self.assertEqual(
            raised.exception.message,
            "Crawler is busy.",
        )

    @patch(
        "backend.app.clients.http_json.request.urlopen"
    )
    def test_fastapi_string_detail_is_preserved(
        self,
        urlopen,
    ):
        urlopen.side_effect = error.HTTPError(
            url="http://crawler:8000/v1/crawl-jobs/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b'{"detail":"Job not found"}'),
        )

        with self.assertRaises(
            InternalServiceHTTPError
        ) as raised:
            get_json(
                url=(
                    "http://crawler:8000"
                    "/v1/crawl-jobs/missing"
                ),
                timeout_seconds=10,
            )

        self.assertEqual(
            raised.exception.error_code,
            "INTERNAL_SERVICE_HTTP_ERROR",
        )
        self.assertEqual(
            raised.exception.message,
            "Job not found",
        )


if __name__ == "__main__":
    unittest.main()
