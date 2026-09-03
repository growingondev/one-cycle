import os
import unittest
from unittest.mock import Mock, patch

from backend.app.services import pipeline_gateway
from backend.app.services.pipeline_gateway import (
    PipelineUnavailableError,
)


class PipelineGatewayRuntimeTest(unittest.TestCase):

    def test_legacy_runtime_uses_document_reprocessor(self):
        runner = Mock(
            return_value={
                "success": True,
                "document_id": 10,
            }
        )

        with (
            patch.dict(
                os.environ,
                {
                    "DOCUMENT_PROCESSING_RUNTIME": "legacy",
                },
                clear=False,
            ),
            patch.object(
                pipeline_gateway,
                "_load_callable",
                return_value=runner,
            ) as mock_load_callable,
        ):
            result = pipeline_gateway.reprocess_document(
                10
            )

        self.assertEqual(
            result["document_id"],
            10,
        )

        mock_load_callable.assert_called_once_with(
            "DOCUMENT_REPROCESSOR"
        )

        runner.assert_called_once_with(
            document_id=10
        )

    def test_worker_http_runtime_uses_worker_orchestration(self):
        expected = {
            "success": True,
            "document_id": 20,
            "stage": "completed",
        }

        with (
            patch.dict(
                os.environ,
                {
                    "DOCUMENT_PROCESSING_RUNTIME":
                    "worker_http",
                },
                clear=False,
            ),
            patch.object(
                pipeline_gateway,
                "_load_callable",
            ) as mock_load_callable,
            patch(
                "backend.app.services."
                "document_processing_service."
                "process_document_with_worker",
                return_value=expected,
            ) as mock_worker,
        ):
            result = pipeline_gateway.reprocess_document(
                20
            )

        self.assertEqual(
            result,
            expected,
        )

        mock_load_callable.assert_not_called()

        mock_worker.assert_called_once_with(
            20
        )

    def test_default_runtime_uses_worker_orchestration(self):
        expected = {
            "success": True,
            "document_id": 25,
            "stage": "completed",
        }

        with (
            patch.dict(
                os.environ,
                {},
                clear=False,
            ),
            patch.object(
                pipeline_gateway,
                "_load_callable",
            ) as mock_load_callable,
            patch(
                "backend.app.services."
                "document_processing_service."
                "process_document_with_worker",
                return_value=expected,
            ) as mock_worker,
        ):
            os.environ.pop(
                "DOCUMENT_PROCESSING_RUNTIME",
                None,
            )

            result = pipeline_gateway.reprocess_document(
                25
            )

        self.assertEqual(
            result,
            expected,
        )

        mock_load_callable.assert_not_called()

        mock_worker.assert_called_once_with(
            25
        )

    def test_invalid_runtime_is_rejected(self):
        with patch.dict(
            os.environ,
            {
                "DOCUMENT_PROCESSING_RUNTIME":
                "invalid-mode",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                PipelineUnavailableError,
                "DOCUMENT_PROCESSING_RUNTIME",
            ):
                pipeline_gateway.reprocess_document(
                    30
                )

    def test_legacy_runtime_rejects_stage_resume(self):
        with patch.dict(
            os.environ,
            {"DOCUMENT_PROCESSING_RUNTIME": "legacy"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                PipelineUnavailableError,
                "worker_http",
            ):
                pipeline_gateway.reprocess_document(
                    30,
                    start_stage="embedding",
                )


if __name__ == "__main__":
    unittest.main()
