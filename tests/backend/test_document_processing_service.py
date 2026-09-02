from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.clients.document_worker_client import (
    DocumentWorkerResponse,
)
from backend.app.clients.http_json import (
    InternalServiceResponseError,
)
from backend.app.services.document_processing_service import (
    process_document_via_worker,
)


def _worker_response(
    *,
    document_id: int = 30,
    announcement_id: int = 20,
    announcement_key: str = "LH-TEST-001",
    document_format: str = "hwp",
) -> DocumentWorkerResponse:
    return DocumentWorkerResponse.model_validate(
        {
            "document_id": document_id,
            "announcement_id": announcement_id,
            "announcement_key": announcement_key,
            "status": "completed",
            "document_format": document_format,
            "output_path": (
                "/data/outputs/LH-TEST-001/document_30"
            ),
            "summary": {
                "chunk_count": 10,
                "embedding_count": 10,
            },
            "key_information": {
                "application_period": {},
                "eligibility": {},
                "supply_information": {},
                "income_asset_criteria": {},
                "required_documents": {},
                "winner_announcement": {},
                "contact_information": {},
            },
        }
    )


class DocumentProcessingServiceTest(
    unittest.TestCase
):
    def test_worker_request_is_built_from_db_context(
        self,
    ):
        context = {
            "announcement_key": "LH-TEST-001",
            "announcement_db_id": 20,
            "document_db_id": 30,
            "filename": "sample.hwp",
            "format": "HWP",
            "storage_path": (
                "/data/documents/LH-TEST-001/sample.hwp"
            ),
        }

        response = _worker_response()

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "get_registered_document_context",
                return_value=context,
            ) as get_context,
            patch(
                "backend.app.services."
                "document_processing_service."
                "document_worker_client.process_document",
                return_value=response,
            ) as process_document,
        ):
            result = process_document_via_worker(
                30
            )

        self.assertIs(
            result,
            response,
        )

        get_context.assert_called_once_with(
            30
        )

        process_document.assert_called_once_with(
            document_id=30,
            announcement_id=20,
            announcement_key="LH-TEST-001",
            filename="sample.hwp",
            document_format="hwp",
            storage_path=(
                "/data/documents/"
                "LH-TEST-001/sample.hwp"
            ),
        )

    def test_invalid_document_id_is_rejected(
        self,
    ):
        for invalid_id in (
            0,
            -1,
            True,
            "30",
        ):
            with self.subTest(
                document_id=invalid_id
            ):
                with self.assertRaises(
                    ValueError
                ):
                    process_document_via_worker(
                        invalid_id
                    )

    def test_missing_storage_path_is_rejected(
        self,
    ):
        context = {
            "announcement_key": "LH-TEST-001",
            "announcement_db_id": 20,
            "document_db_id": 30,
            "filename": "sample.hwp",
            "format": "hwp",
            "storage_path": None,
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "get_registered_document_context",
                return_value=context,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "document_worker_client.process_document",
            ) as process_document,
        ):
            with self.assertRaises(
                RuntimeError
            ):
                process_document_via_worker(
                    30
                )

        process_document.assert_not_called()

    def test_context_document_id_must_match_request(
        self,
    ):
        context = {
            "announcement_key": "LH-TEST-001",
            "announcement_db_id": 20,
            "document_db_id": 31,
            "filename": "sample.hwp",
            "format": "hwp",
            "storage_path": (
                "/data/documents/LH-TEST-001/sample.hwp"
            ),
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "get_registered_document_context",
                return_value=context,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "document_worker_client.process_document",
            ) as process_document,
        ):
            with self.assertRaises(
                RuntimeError
            ):
                process_document_via_worker(
                    30
                )

        process_document.assert_not_called()

    def test_worker_response_context_mismatch_is_rejected(
        self,
    ):
        context = {
            "announcement_key": "LH-TEST-001",
            "announcement_db_id": 20,
            "document_db_id": 30,
            "filename": "sample.hwp",
            "format": "hwp",
            "storage_path": (
                "/data/documents/LH-TEST-001/sample.hwp"
            ),
        }

        invalid_response = _worker_response(
            announcement_id=999,
        )

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "get_registered_document_context",
                return_value=context,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "document_worker_client.process_document",
                return_value=invalid_response,
            ),
        ):
            with self.assertRaises(
                InternalServiceResponseError
            ):
                process_document_via_worker(
                    30
                )


class DocumentWorkerFinalizationTest(
    unittest.TestCase
):
    def _response(
        self,
    ) -> DocumentWorkerResponse:
        return _worker_response()

    def test_successful_worker_result_is_persisted_and_activated(
        self,
    ):
        response = self._response()

        persistence = {
            "processing_run_id": 40,
            "written_chunks": 10,
            "written_embeddings": 10,
        }

        key_information_result = {
            "id": 50,
            "extraction_status": "completed",
        }

        activation = {
            "processing_run_id": 40,
            "document_id": 30,
            "chunk_set_id": 60,
            "chunks": 10,
            "embeddings": 10,
            "deactivated_runs": [],
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "persist_document_outputs",
                return_value=persistence,
            ) as persist_outputs,
            patch(
                "backend.app.services."
                "document_processing_service."
                "upsert_key_information",
                return_value=key_information_result,
            ) as upsert_key_information,
            patch(
                "backend.app.services."
                "document_processing_service."
                "activate_processing_run",
                return_value=activation,
            ) as activate_processing_run,
            patch(
                "backend.app.services."
                "document_processing_service."
                "mark_processing_run_failed",
            ) as mark_failed,
        ):
            from backend.app.services.document_processing_service import (
                finalize_document_worker_result,
            )

            result = finalize_document_worker_result(
                document_id=30,
                response=response,
            )

        persist_outputs.assert_called_once_with(
            30,
            output_root_path=response.output_path,
        )

        upsert_key_information.assert_called_once_with(
            announcement_id=20,
            source_processing_run_id=40,
            application_period={},
            eligibility={},
            supply_information={},
            income_asset_criteria={},
            required_documents={},
            winner_announcement={},
            contact_information={},
            extraction_status="completed",
            is_verified=False,
        )

        activate_processing_run.assert_called_once_with(
            40
        )

        mark_failed.assert_not_called()

        self.assertTrue(
            result["success"]
        )
        self.assertEqual(
            result["processing_run_id"],
            40,
        )
        self.assertEqual(
            result["key_information_id"],
            50,
        )
        self.assertTrue(
            result["is_active"]
        )

    def test_summary_mismatch_marks_processing_run_failed(
        self,
    ):
        response = self._response()

        persistence = {
            "processing_run_id": 40,
            "written_chunks": 9,
            "written_embeddings": 10,
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "persist_document_outputs",
                return_value=persistence,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "upsert_key_information",
            ) as upsert_key_information,
            patch(
                "backend.app.services."
                "document_processing_service."
                "activate_processing_run",
            ) as activate_processing_run,
            patch(
                "backend.app.services."
                "document_processing_service."
                "mark_processing_run_failed",
            ) as mark_failed,
        ):
            from backend.app.services.document_processing_service import (
                finalize_document_worker_result,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "Chunk count",
            ):
                finalize_document_worker_result(
                    document_id=30,
                    response=response,
                )

        mark_failed.assert_called_once()

        failure_call = mark_failed.call_args

        self.assertEqual(
            failure_call.args[0],
            40,
        )
        self.assertEqual(
            failure_call.kwargs["stage"],
            "persistence",
        )
        self.assertEqual(
            failure_call.kwargs["error_code"],
            "WORKER_PERSISTENCE_SUMMARY_MISMATCH",
        )

        upsert_key_information.assert_not_called()
        activate_processing_run.assert_not_called()

    def test_key_information_failure_marks_run_failed(
        self,
    ):
        response = self._response()

        persistence = {
            "processing_run_id": 40,
            "written_chunks": 10,
            "written_embeddings": 10,
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "persist_document_outputs",
                return_value=persistence,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "upsert_key_information",
                side_effect=RuntimeError(
                    "key information DB failure"
                ),
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "activate_processing_run",
            ) as activate_processing_run,
            patch(
                "backend.app.services."
                "document_processing_service."
                "mark_processing_run_failed",
            ) as mark_failed,
        ):
            from backend.app.services.document_processing_service import (
                finalize_document_worker_result,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "key information DB failure",
            ):
                finalize_document_worker_result(
                    document_id=30,
                    response=response,
                )

        mark_failed.assert_called_once_with(
            40,
            stage="key_information",
            error_code=(
                "KEY_INFORMATION_PERSISTENCE_FAILED"
            ),
            error_message=(
                "key information DB failure"
            ),
            exit_code=1,
        )

        activate_processing_run.assert_not_called()

    def test_activation_failure_marks_run_failed(
        self,
    ):
        response = self._response()

        persistence = {
            "processing_run_id": 40,
            "written_chunks": 10,
            "written_embeddings": 10,
        }

        key_information_result = {
            "id": 50,
            "extraction_status": "completed",
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "persist_document_outputs",
                return_value=persistence,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "upsert_key_information",
                return_value=key_information_result,
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "activate_processing_run",
                side_effect=RuntimeError(
                    "activation failure"
                ),
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "mark_processing_run_failed",
            ) as mark_failed,
        ):
            from backend.app.services.document_processing_service import (
                finalize_document_worker_result,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "activation failure",
            ):
                finalize_document_worker_result(
                    document_id=30,
                    response=response,
                )

        mark_failed.assert_called_once_with(
            40,
            stage="activation",
            error_code=(
                "PROCESSING_RUN_ACTIVATION_FAILED"
            ),
            error_message="activation failure",
            exit_code=1,
        )

    def test_persistence_failure_does_not_fake_processing_run_failure(
        self,
    ):
        response = self._response()

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "persist_document_outputs",
                side_effect=RuntimeError(
                    "artifact validation failure"
                ),
            ),
            patch(
                "backend.app.services."
                "document_processing_service."
                "mark_processing_run_failed",
            ) as mark_failed,
        ):
            from backend.app.services.document_processing_service import (
                finalize_document_worker_result,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "artifacts could not be persisted",
            ):
                finalize_document_worker_result(
                    document_id=30,
                    response=response,
                )

        # Persistence transaction 자체가 실패한 경우에는
        # 유효한 새 ProcessingRun ID가 없다고 본다.
        mark_failed.assert_not_called()

    def test_process_document_with_worker_chains_request_and_finalize(
        self,
    ):
        response = self._response()

        completed = {
            "success": True,
            "document_id": 30,
        }

        with (
            patch(
                "backend.app.services."
                "document_processing_service."
                "process_document_via_worker",
                return_value=response,
            ) as process_via_worker,
            patch(
                "backend.app.services."
                "document_processing_service."
                "finalize_document_worker_result",
                return_value=completed,
            ) as finalize,
        ):
            from backend.app.services.document_processing_service import (
                process_document_with_worker,
            )

            result = process_document_with_worker(
                30
            )

        process_via_worker.assert_called_once_with(
            30
        )

        finalize.assert_called_once_with(
            document_id=30,
            response=response,
        )

        self.assertIs(
            result,
            completed,
        )


class DocumentWorkerErrorMappingTest(
    unittest.TestCase
):
    def test_worker_http_errors_map_to_backend_stages(
        self,
    ):
        from backend.app.clients.http_json import (
            InternalServiceHTTPError,
        )
        from backend.app.services.document_processing_service import (
            process_document_with_worker,
        )

        cases = {
            "DOCUMENT_FORMAT_VALIDATION_FAILED": (
                "format_detection"
            ),
            "DOCUMENT_PARSE_FAILED": "parser",
            "DOCUMENT_NORMALIZE_FAILED": "normalizer",
            "DOCUMENT_STRUCTURE_FAILED": "structure",
            "DOCUMENT_VERIFICATION_FAILED": (
                "verification"
            ),
            "DOCUMENT_CHUNKING_FAILED": "chunking",
            "DOCUMENT_EMBEDDING_INPUT_FAILED": (
                "embedding"
            ),
            "DOCUMENT_EMBEDDING_SERVICE_FAILED": (
                "embedding"
            ),
            "DOCUMENT_EMBEDDING_ARTIFACT_FAILED": (
                "embedding"
            ),
            "DOCUMENT_KEY_INFORMATION_FAILED": (
                "key_information_extraction"
            ),
            "INTERNAL_SERVICE_HTTP_ERROR": "integration",
        }

        for error_code, expected_stage in cases.items():
            with self.subTest(error_code=error_code):
                error = InternalServiceHTTPError(
                    status_code=500,
                    error_code=error_code,
                    message="worker failed",
                )

                with (
                    patch(
                        "backend.app.services."
                        "document_processing_service."
                        "process_document_via_worker",
                        side_effect=error,
                    ),
                    patch(
                        "backend.app.services."
                        "document_processing_service."
                        "finalize_document_worker_result",
                    ) as finalize,
                ):
                    result = process_document_with_worker(
                        30
                    )

                self.assertEqual(
                    result,
                    {
                        "success": False,
                        "document_id": 30,
                        "stage": expected_stage,
                        "error_code": error_code,
                        "message": "worker failed",
                    },
                )
                finalize.assert_not_called()

if __name__ == "__main__":
    unittest.main()