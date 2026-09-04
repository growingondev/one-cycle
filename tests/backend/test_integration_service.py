import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from backend.app.services import integration_service
from backend.app.services.collection_service import (
    recollect_and_persist,
)
from backend.app.services.integration_service import (
    collect_persist_and_process,
    process_document_ids,
    recollect_persist_and_process,
)


class IntegrationServiceTest(unittest.TestCase):

    @patch(
        "backend.app.services.integration_service."
        "settings.collection_retention_mode",
        "dry_run",
    )
    @patch(
        "backend.app.services.integration_service."
        "apply_collection_run_retention"
    )
    def test_retention_dry_run_mode_is_applied_after_publish(
        self,
        mock_apply_retention,
    ):
        mock_apply_retention.return_value = {
            "status": "dry_run",
        }

        result = integration_service._apply_retention_after_publish(7)

        self.assertEqual(result["status"], "dry_run")
        mock_apply_retention.assert_called_once_with(dry_run=True)

    @patch(
        "backend.app.services.integration_service."
        "settings.collection_retention_mode",
        "delete",
    )
    @patch(
        "backend.app.services.integration_service."
        "apply_collection_run_retention"
    )
    def test_retention_delete_mode_is_applied_after_publish(
        self,
        mock_apply_retention,
    ):
        mock_apply_retention.return_value = {
            "status": "completed",
        }

        result = integration_service._apply_retention_after_publish(8)

        self.assertEqual(result["status"], "completed")
        mock_apply_retention.assert_called_once_with(dry_run=False)

    @patch(
        "backend.app.services.collection_service.record_error"
    )
    @patch(
        "backend.app.services.collection_service."
        "_validate_recollection_result"
    )
    @patch(
        "backend.app.services.collection_service."
        "crawler_client.recollect_announcement"
    )
    @patch(
        "backend.app.services.collection_service.SessionLocal"
    )
    def test_recollect_and_persist_uses_error_id_contract(
        self,
        mock_session_local,
        mock_recollect_lh_notice,
        mock_validate_recollection_result,
        mock_record_error,
    ):
        announcement = SimpleNamespace(
            source_announcement_id="NOTICE-001",
            detail_url="https://example.com/notice/1",
            collection_run_id=7,
        )

        read_db = (
            mock_session_local.return_value
            .__enter__.return_value
        )
        read_db.get.return_value = announcement

        write_db = (
            mock_session_local.begin.return_value
            .__enter__.return_value
        )
        write_db.get.return_value = announcement

        mock_recollect_lh_notice.return_value = {
            "execution_id": "recollect-test-1",
            "status": "partial_success",
            "data": {
                "documents": [],
            },
            "errors": [
                {
                    "error_type": "collection",
                    "stage": "recollect",
                    "error_code": "DOWNLOAD_FAILED",
                    "message": "download failed",
                    "file_name": "notice.hwp",
                }
            ],
        }

        mock_record_error.return_value = {
            "error_id": 555,
        }

        result = recollect_and_persist(
            announcement_id=9
        )

        self.assertEqual(
            result["error_ids"],
            [555],
        )
        self.assertEqual(
            result["error_count"],
            1,
        )

        mock_recollect_lh_notice.assert_called_once_with(
            source_announcement_id="NOTICE-001",
            detail_url="https://example.com/notice/1",
        )

        mock_record_error.assert_called_once()

    @patch(
        "backend.app.services.integration_service.record_error"
    )
    @patch(
        "backend.app.services.integration_service."
        "reprocess_document"
    )
    def test_process_document_success(
        self,
        mock_reprocess_document,
        mock_record_error,
    ):
        mock_reprocess_document.return_value = {
            "success": True,
            "stage": "completed",
            "document_id": 10,
        }

        result = process_document_ids([10])

        self.assertEqual(
            result["requested_count"],
            1,
        )
        self.assertEqual(
            result["success_count"],
            1,
        )
        self.assertEqual(
            result["failed_count"],
            0,
        )
        self.assertEqual(
            result["error_ids"],
            [],
        )

        mock_reprocess_document.assert_called_once_with(10)
        mock_record_error.assert_not_called()

    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_retry_delay_seconds",
        0.0,
    )
    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_max_attempts",
        3,
    )
    @patch(
        "backend.app.services.integration_service.record_error"
    )
    @patch(
        "backend.app.services.integration_service."
        "reprocess_document"
    )
    def test_process_document_failure_records_error(
        self,
        mock_reprocess_document,
        mock_record_error,
    ):
        mock_reprocess_document.return_value = {
            "success": False,
            "document_id": 11,
            "stage": "embedding",
            "error_code": "EMBEDDING_FAILED",
            "message": "embedding failed",
        }

        mock_record_error.return_value = {
            "error_id": 100,
        }

        result = process_document_ids([11])

        self.assertEqual(
            result["success_count"],
            0,
        )
        self.assertEqual(
            result["failed_count"],
            1,
        )
        self.assertEqual(
            result["error_ids"],
            [100],
        )

        self.assertEqual(
            mock_reprocess_document.call_args_list,
            [
                call(11),
                call(
                    11,
                    start_stage="embedding",
                ),
                call(
                    11,
                    start_stage="embedding",
                ),
            ],
        )
        mock_record_error.assert_called_once_with(
            error_type="embedding",
            stage="embedding",
            error_code="EMBEDDING_FAILED",
            message="embedding failed",
            document_id=11,
        )

    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_retry_delay_seconds",
        0.0,
    )
    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_max_attempts",
        3,
    )
    @patch(
        "backend.app.services.integration_service.record_error"
    )
    @patch(
        "backend.app.services.integration_service."
        "reprocess_document"
    )
    def test_process_document_retries_failed_stage(
        self,
        mock_reprocess_document,
        mock_record_error,
    ):
        mock_reprocess_document.side_effect = [
            {
                "success": False,
                "document_id": 12,
                "stage": "embedding",
                "error_code": "EMBEDDING_FAILED",
                "message": "temporary failure",
            },
            {
                "success": True,
                "document_id": 12,
                "stage": "completed",
            },
        ]

        result = process_document_ids([12])

        self.assertEqual(
            result["success_count"],
            1,
        )
        self.assertEqual(
            result["failed_count"],
            0,
        )
        self.assertEqual(
            result["error_ids"],
            [],
        )
        self.assertEqual(
            mock_reprocess_document.call_args_list,
            [
                call(12),
                call(
                    12,
                    start_stage="embedding",
                ),
            ],
        )
        mock_record_error.assert_not_called()

    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_retry_delay_seconds",
        0.0,
    )
    @patch(
        "backend.app.services.integration_service."
        "settings.document_processing_max_attempts",
        3,
    )
    @patch(
        "backend.app.services.integration_service.record_error"
    )
    @patch(
        "backend.app.services.integration_service."
        "reprocess_document"
    )
    def test_process_document_retries_unexpected_error_from_start(
        self,
        mock_reprocess_document,
        mock_record_error,
    ):
        mock_reprocess_document.side_effect = [
            RuntimeError("temporary connection failure"),
            {
                "success": True,
                "document_id": 13,
                "stage": "completed",
            },
        ]

        result = process_document_ids([13])

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(
            mock_reprocess_document.call_args_list,
            [call(13), call(13)],
        )
        mock_record_error.assert_not_called()

    @patch(
        "backend.app.services.integration_service."
        "publish_collection_run"
    )
    @patch(
        "backend.app.services.integration_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.integration_service."
        "collect_and_persist"
    )
    def test_collection_processes_analysis_documents_and_publishes_on_success(
        self,
        mock_collect_and_persist,
        mock_process_document_ids,
        mock_publish_collection_run,
    ):
        mock_collect_and_persist.return_value = {
            "collection_run_id": 1,
            "status": "success",
            "document_ids": [21, 22, 23],
            "analysis_document_ids": [21, 22],
        }

        mock_process_document_ids.return_value = {
            "requested_count": 2,
            "success_count": 2,
            "failed_count": 0,
            "error_ids": [],
            "results": [],
        }

        mock_publish_collection_run.return_value = {
            "status": "published",
            "active_collection_run_id": 1,
        }

        result = collect_persist_and_process()

        mock_process_document_ids.assert_called_once_with(
            [21, 22]
        )
        mock_publish_collection_run.assert_called_once_with(
            1
        )

        self.assertEqual(
            result["document_processing"]["requested_count"],
            2,
        )
        self.assertEqual(
            result["status"],
            "success",
        )
        self.assertEqual(
            result["publish"]["status"],
            "published",
        )

    @patch(
        "backend.app.services.integration_service."
        "publish_collection_run"
    )
    @patch(
        "backend.app.services.integration_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.integration_service."
        "collect_and_persist"
    )
    def test_collection_does_not_publish_when_document_processing_fails(
        self,
        mock_collect_and_persist,
        mock_process_document_ids,
        mock_publish_collection_run,
    ):
        mock_collect_and_persist.return_value = {
            "collection_run_id": 2,
            "status": "success",
            "document_ids": [31, 32],
            "analysis_document_ids": [31, 32],
        }

        mock_process_document_ids.return_value = {
            "requested_count": 2,
            "success_count": 1,
            "failed_count": 1,
            "error_ids": [500],
            "results": [],
        }

        result = collect_persist_and_process()

        mock_publish_collection_run.assert_not_called()

        self.assertEqual(
            result["status"],
            "failed",
        )
        self.assertEqual(
            result["publish"]["status"],
            "skipped",
        )
        self.assertEqual(
            result["publish"]["reason"],
            "document_processing_failed",
        )

    @patch(
        "backend.app.services.integration_service.record_error"
    )
    @patch(
        "backend.app.services.integration_service."
        "publish_collection_run"
    )
    @patch(
        "backend.app.services.integration_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.integration_service."
        "collect_and_persist"
    )
    def test_collection_records_error_when_publish_fails(
        self,
        mock_collect_and_persist,
        mock_process_document_ids,
        mock_publish_collection_run,
        mock_record_error,
    ):
        mock_collect_and_persist.return_value = {
            "collection_run_id": 3,
            "status": "success",
            "document_ids": [41],
            "analysis_document_ids": [41],
        }

        mock_process_document_ids.return_value = {
            "requested_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_ids": [],
            "results": [],
        }

        mock_publish_collection_run.side_effect = RuntimeError(
            "publish validation failed"
        )

        mock_record_error.return_value = {
            "error_id": 777,
        }

        result = collect_persist_and_process()

        mock_publish_collection_run.assert_called_once_with(
            3
        )

        mock_record_error.assert_called_once_with(
            error_type="database",
            stage="publish",
            error_code="COLLECTION_PUBLISH_FAILED",
            message="publish validation failed",
            collection_run_id=3,
        )

        self.assertEqual(
            result["status"],
            "failed",
        )
        self.assertEqual(
            result["publish"]["status"],
            "failed",
        )
        self.assertEqual(
            result["publish"]["error_id"],
            777,
        )

    @patch(
        "backend.app.services.integration_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.integration_service."
        "recollect_and_persist"
    )
    def test_recollection_processes_only_new_analysis_documents(
        self,
        mock_recollect_and_persist,
        mock_process_document_ids,
    ):
        mock_recollect_and_persist.return_value = {
            "announcement_id": 9,
            "status": "success",

            # 새로 저장된 문서
            "new_document_ids": [31, 32],

            # 이 중 primary인 31만 분석
            "new_analysis_document_ids": [31],

            # 기존 동일 문서는 재사용
            "reused_document_ids": [30],

            "document_ids": [31, 32, 30],
        }

        mock_process_document_ids.return_value = {
            "requested_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_ids": [],
            "results": [],
        }

        result = recollect_persist_and_process(
            announcement_id=9
        )

        mock_recollect_and_persist.assert_called_once_with(
            announcement_id=9
        )

        mock_process_document_ids.assert_called_once_with(
            [31]
        )

        self.assertEqual(
            result[
                "document_processing"
            ]["requested_count"],
            1,
        )


class KeyInformationStageMappingTest(
    unittest.TestCase
):
    def test_extraction_stage_is_structuring_error(
        self,
    ):
        from backend.app.services.integration_service import (
            _error_type_for_stage,
        )

        self.assertEqual(
            _error_type_for_stage(
                "key_information_extraction"
            ),
            "structuring",
        )

if __name__ == "__main__":
    unittest.main()
