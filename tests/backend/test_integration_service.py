import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
        "backend.app.services.collection_service.record_error"
    )
    @patch(
        "backend.app.services.collection_service."
        "_validate_recollection_result"
    )
    @patch(
        "crawler.crawler.recollect_lh_notice"
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

        mock_record_error.assert_called_once_with(
            error_type="embedding",
            stage="embedding",
            error_code="EMBEDDING_FAILED",
            message="embedding failed",
            document_id=11,
        )

    @patch(
        "backend.app.services.integration_service."
        "process_document_ids"
    )
    @patch(
        "backend.app.services.integration_service."
        "collect_and_persist"
    )
    def test_collection_processes_only_analysis_documents(
        self,
        mock_collect_and_persist,
        mock_process_document_ids,
    ):
        mock_collect_and_persist.return_value = {
            "collection_run_id": 1,
            "status": "success",

            # DB에는 두 문서 모두 저장
            "document_ids": [21, 22],

            # 실제 분석 대상은 primary 문서 21만
            "analysis_document_ids": [21],
        }

        mock_process_document_ids.return_value = {
            "requested_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_ids": [],
            "results": [],
        }

        result = collect_persist_and_process()

        mock_process_document_ids.assert_called_once_with(
            [21]
        )

        self.assertEqual(
            result[
                "document_processing"
            ]["requested_count"],
            1,
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


if __name__ == "__main__":
    unittest.main()