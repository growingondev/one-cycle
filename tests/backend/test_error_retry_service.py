from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.services.error_retry_service import (
    ErrorRetryExecutionError,
    RetryTarget,
    _infer_legacy_target_filename,
    retry_error_from_stage,
)


class ErrorRetryServiceTest(unittest.TestCase):

    def test_legacy_download_error_recovers_target_filename(self):
        self.assertEqual(
            _infer_legacy_target_filename(
                "다운로드 시작 대기 실패: 공고문.hwpx"
            ),
            "공고문.hwpx",
        )

    @patch(
        "backend.app.services.error_retry_service._finish_retry"
    )
    @patch(
        "backend.app.services.error_retry_service."
        "_retry_download_document"
    )
    @patch(
        "backend.app.services.error_retry_service._claim_retry"
    )
    def test_download_error_retries_only_linked_document(
        self,
        mock_claim_retry,
        mock_retry_download_document,
        mock_finish_retry,
    ):
        target = RetryTarget(
            error_id=7,
            announcement_id=31,
            document_id=None,
            error_type="download",
            stage="download",
            target_filename="notice.hwpx",
        )
        mock_claim_retry.return_value = target
        mock_retry_download_document.return_value = {
            "success": True,
            "retry_scope": "document",
            "announcement_id": 31,
            "target_filename": "notice.hwpx",
            "start_stage": "download",
        }

        result = retry_error_from_stage(error_id=7)

        mock_retry_download_document.assert_called_once_with(target)
        mock_finish_retry.assert_called_once_with(
            7,
            succeeded=True,
            message="download 단계 재시도 성공 (document 단위)",
        )
        self.assertEqual(result["announcement_id"], 31)

    @patch(
        "backend.app.services.error_retry_service._finish_retry"
    )
    @patch(
        "backend.app.services.error_retry_service._retry_document"
    )
    @patch(
        "backend.app.services.error_retry_service._claim_retry"
    )
    def test_processing_error_retries_only_linked_document(
        self,
        mock_claim_retry,
        mock_retry_document,
        mock_finish_retry,
    ):
        target = RetryTarget(
            error_id=8,
            announcement_id=31,
            document_id=52,
            error_type="embedding",
            stage="embedding",
            target_filename="notice.hwpx",
        )
        mock_claim_retry.return_value = target
        mock_retry_document.return_value = {
            "success": True,
            "retry_scope": "document",
            "announcement_id": 31,
            "document_id": 52,
            "start_stage": "embedding",
        }

        result = retry_error_from_stage(error_id=8)

        mock_retry_document.assert_called_once_with(target)
        mock_finish_retry.assert_called_once_with(
            8,
            succeeded=True,
            message="embedding 단계 재시도 성공 (document 단위)",
        )
        self.assertEqual(result["document_id"], 52)

    @patch(
        "backend.app.services.error_retry_service._finish_retry"
    )
    @patch(
        "backend.app.services.error_retry_service."
        "_retry_download_document"
    )
    @patch(
        "backend.app.services.error_retry_service._claim_retry"
    )
    def test_failed_retry_returns_original_error_to_unresolved(
        self,
        mock_claim_retry,
        mock_retry_download_document,
        mock_finish_retry,
    ):
        target = RetryTarget(
            error_id=9,
            announcement_id=33,
            document_id=None,
            error_type="download",
            stage="download",
            target_filename="notice.hwpx",
        )
        mock_claim_retry.return_value = target
        mock_retry_download_document.side_effect = ErrorRetryExecutionError(
            "download failed again"
        )

        with self.assertRaises(ErrorRetryExecutionError):
            retry_error_from_stage(error_id=9)

        mock_finish_retry.assert_called_once_with(
            9,
            succeeded=False,
            message=(
                "download 단계 재시도 실패: "
                "download failed again"
            ),
        )


if __name__ == "__main__":
    unittest.main()
