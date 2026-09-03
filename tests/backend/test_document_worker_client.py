import unittest
from unittest.mock import patch

from backend.app.clients.document_worker_client import (
    process_document,
)
from backend.app.clients.http_json import (
    InternalServiceResponseError,
)


def _key_information():
    return {
        "application_period": {
            "status": "found",
        },
        "eligibility": {
            "status": "found",
        },
        "supply_information": {
            "status": "found",
        },
        "income_asset_criteria": {
            "status": "found",
        },
        "required_documents": {
            "status": "found",
        },
        "winner_announcement": {
            "status": "found",
        },
        "contact_information": {
            "status": "found",
        },
    }


def _worker_response():
    return {
        "document_id": 10,
        "announcement_id": 1,
        "announcement_key": "announcement_001",
        "status": "completed",
        "document_format": "hwpx",
        "output_path": (
            "/data/outputs/"
            "announcement_001/document_10"
        ),
        "summary": {
            "chunk_count": 83,
            "embedding_count": 83,
        },
        "key_information": _key_information(),
    }


class DocumentWorkerClientTest(unittest.TestCase):
    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_retry_sends_start_stage(self, post_json):
        post_json.return_value = _worker_response()

        process_document(
            document_id=10,
            announcement_id=1,
            announcement_key="announcement_001",
            filename="announcement.hwpx",
            document_format="hwpx",
            storage_path="/data/documents/announcement.hwpx",
            start_stage="embedding",
            base_url="http://document-worker:8000/",
            timeout_seconds=600,
        )

        payload = post_json.call_args.kwargs["payload"]
        self.assertEqual(payload["start_stage"], "embedding")

    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_process_document_sends_expected_request(
        self,
        post_json,
    ):
        post_json.return_value = _worker_response()

        result = process_document(
            document_id=10,
            announcement_id=1,
            announcement_key="announcement_001",
            filename="announcement.hwpx",
            document_format="hwpx",
            storage_path=(
                "/data/documents/announcement.hwpx"
            ),
            base_url="http://document-worker:8000/",
            timeout_seconds=600,
        )

        post_json.assert_called_once_with(
            url=(
                "http://document-worker:8000"
                "/v1/documents/10/process"
            ),
            payload={
                "announcement_id": 1,
                "announcement_key": (
                    "announcement_001"
                ),
                "source": {
                    "filename": "announcement.hwpx",
                    "format": "hwpx",
                    "storage_path": (
                        "/data/documents/"
                        "announcement.hwpx"
                    ),
                },
            },
            timeout_seconds=600,
        )

        self.assertEqual(
            result.status,
            "completed",
        )
        self.assertEqual(
            result.summary.chunk_count,
            83,
        )

    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_process_document_accepts_not_found(
        self,
        post_json,
    ):
        response = _worker_response()

        response[
            "key_information"
        ][
            "winner_announcement"
        ] = {
            "status": "not_found",
        }

        post_json.return_value = response

        result = process_document(
            document_id=10,
            announcement_id=1,
            announcement_key="announcement_001",
            filename="announcement.hwpx",
            document_format="hwpx",
            storage_path=(
                "/data/documents/announcement.hwpx"
            ),
            base_url="http://document-worker:8000",
            timeout_seconds=600,
        )

        self.assertEqual(
            result
            .key_information
            .winner_announcement[
                "status"
            ],
            "not_found",
        )

    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_process_document_requires_all_key_information_fields(
        self,
        post_json,
    ):
        response = _worker_response()

        del response[
            "key_information"
        ][
            "contact_information"
        ]

        post_json.return_value = response

        with self.assertRaises(
            InternalServiceResponseError
        ):
            process_document(
                document_id=10,
                announcement_id=1,
                announcement_key=(
                    "announcement_001"
                ),
                filename="announcement.hwpx",
                document_format="hwpx",
                storage_path=(
                    "/data/documents/"
                    "announcement.hwpx"
                ),
                base_url=(
                    "http://document-worker:8000"
                ),
                timeout_seconds=600,
            )

    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_process_document_rejects_invalid_key_information_type(
        self,
        post_json,
    ):
        response = _worker_response()

        response[
            "key_information"
        ][
            "application_period"
        ] = "not_found"

        post_json.return_value = response

        with self.assertRaises(
            InternalServiceResponseError
        ):
            process_document(
                document_id=10,
                announcement_id=1,
                announcement_key=(
                    "announcement_001"
                ),
                filename="announcement.hwpx",
                document_format="hwpx",
                storage_path=(
                    "/data/documents/"
                    "announcement.hwpx"
                ),
                base_url=(
                    "http://document-worker:8000"
                ),
                timeout_seconds=600,
            )

    @patch(
        "backend.app.clients."
        "document_worker_client.post_json"
    )
    def test_process_document_accepts_all_seven_fields(
        self,
        post_json,
    ):
        post_json.return_value = _worker_response()

        result = process_document(
            document_id=10,
            announcement_id=1,
            announcement_key="announcement_001",
            filename="announcement.hwpx",
            document_format="hwpx",
            storage_path=(
                "/data/documents/announcement.hwpx"
            ),
            base_url="http://document-worker:8000",
            timeout_seconds=600,
        )

        payload = (
            result
            .key_information
            .model_dump()
        )

        self.assertEqual(
            set(payload),
            {
                "application_period",
                "eligibility",
                "supply_information",
                "income_asset_criteria",
                "required_documents",
                "winner_announcement",
                "contact_information",
            },
        )


if __name__ == "__main__":
    unittest.main()
