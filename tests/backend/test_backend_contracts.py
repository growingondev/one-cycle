import os
import sys
import unittest
from types import ModuleType
from unittest.mock import patch

from backend.app.services.chat_service import answer_question_via_rag
from backend.app.services.collection_service import (
    VALID_DOCUMENT_FORMATS,
    _validate_collection_result,
)
from backend.app.services.pipeline_gateway import (
    PipelineUnavailableError,
    collect_announcements,
)

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.app.services.error_log_service import (
    VALID_ERROR_TYPES,
    _resolve_error_links,
    _validate_error_input,
)

class CollectionContractTest(unittest.TestCase):
    def test_valid_collection_result_is_accepted(self):
        result = {
            "execution_id": "test_execution_001",
            "execution_status": "success",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "fatal_error": None,
            "data": [],
        }

        _validate_collection_result(result)

    def test_collection_result_requires_execution_id(self):
        result = {
            "execution_status": "success",
            "data": [],
        }

        with self.assertRaises(ValueError):
            _validate_collection_result(result)

    def test_collection_result_requires_supported_status(self):
        result = {
            "execution_id": "test_execution_001",
            "execution_status": "invalid_status",
            "data": [],
        }

        with self.assertRaises(ValueError):
            _validate_collection_result(result)

    def test_collection_result_data_must_be_list(self):
        result = {
            "execution_id": "test_execution_001",
            "execution_status": "success",
            "data": {},
        }

        with self.assertRaises(ValueError):
            _validate_collection_result(result)

    def test_document_format_contract(self):
        self.assertEqual(
            VALID_DOCUMENT_FORMATS,
            {"hwp", "hwpx"},
        )

        self.assertNotIn(
            "unknown",
            VALID_DOCUMENT_FORMATS,
        )


class PipelineGatewayContractTest(unittest.TestCase):
    def test_collection_runner_requires_environment_variable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PipelineUnavailableError):
                collect_announcements()

    def test_collection_runner_calls_configured_callable(self):
        module_name = "_backend_contract_test_runner"
        module = ModuleType(module_name)

        def collect():
            return {
                "status": "success",
                "source": "contract-test",
            }

        module.collect = collect

        with patch.dict(
            sys.modules,
            {module_name: module},
        ):
            with patch.dict(
                os.environ,
                {
                    "COLLECTION_RUNNER":
                        f"{module_name}:collect"
                },
                clear=False,
            ):
                result = collect_announcements()

        self.assertEqual(
            result["status"],
            "success",
        )
        self.assertEqual(
            result["source"],
            "contract-test",
        )


class ChatContractTest(unittest.TestCase):
    def test_rag_dict_is_converted_to_chat_response(self):
        def fake_answer_question(
            announcement_id: int,
            question: str,
        ):
            self.assertEqual(announcement_id, 10)
            self.assertEqual(question, "신청 자격이 뭐야?")

            return {
                "answer": "테스트 답변",
                "grounded": True,
                "evidence": [
                    {
                        "chunkId": "chunk-001",
                        "sectionTitle": "신청 자격",
                        "content": "테스트 근거",
                        "score": 0.9,
                    }
                ],
            }

        with patch(
            "backend.app.services.chat_service."
            "_load_answer_question",
            return_value=fake_answer_question,
        ):
            response = answer_question_via_rag(
                announcement_id=10,
                question="신청 자격이 뭐야?",
            )

        self.assertEqual(
            response.answer,
            "테스트 답변",
        )
        self.assertTrue(response.grounded)
        self.assertEqual(
            len(response.evidence),
            1,
        )
        self.assertEqual(
            response.evidence[0].chunk_id,
            "chunk-001",
        )

    def test_invalid_rag_result_is_rejected(self):
        with patch(
            "backend.app.services.chat_service."
            "_load_answer_question",
            return_value=lambda **kwargs: "invalid-result",
        ):
            with self.assertRaises(Exception):
                answer_question_via_rag(
                    announcement_id=10,
                    question="테스트",
                )

class ErrorLogContractTest(unittest.TestCase):
    def test_supported_error_types_match_backend_contract(self):
        self.assertIn("collection", VALID_ERROR_TYPES)
        self.assertIn("parsing", VALID_ERROR_TYPES)
        self.assertIn("embedding", VALID_ERROR_TYPES)
        self.assertIn("rag", VALID_ERROR_TYPES)

    def test_invalid_error_type_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_error_input(
                error_type="invalid",
                stage="parsing",
                message="test error",
            )

    def test_empty_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_error_input(
                error_type="parsing",
                stage=" ",
                message="test error",
            )

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_error_input(
                error_type="parsing",
                stage="parsing",
                message=" ",
            )

    def test_processing_run_resolves_parent_links(self):
        db = MagicMock()

        processing_run = SimpleNamespace(
            id=40,
            document_id=30,
        )
        document = SimpleNamespace(
            id=30,
            announcement_id=20,
        )
        announcement = SimpleNamespace(
            id=20,
            collection_run_id=10,
        )
        collection_run = SimpleNamespace(
            id=10,
        )

        def fake_get(model, object_id):
            model_name = model.__name__

            mapping = {
                ("ProcessingRun", 40): processing_run,
                ("Document", 30): document,
                ("Announcement", 20): announcement,
                ("CollectionRun", 10): collection_run,
            }

            return mapping.get(
                (model_name, object_id)
            )

        db.get.side_effect = fake_get

        result = _resolve_error_links(
            db,
            collection_run_id=None,
            announcement_id=None,
            document_id=None,
            processing_run_id=40,
        )

        self.assertEqual(
            result,
            {
                "collection_run_id": 10,
                "announcement_id": 20,
                "document_id": 30,
                "processing_run_id": 40,
            },
        )

    def test_mismatched_document_is_rejected(self):
        db = MagicMock()

        processing_run = SimpleNamespace(
            id=40,
            document_id=30,
        )

        db.get.return_value = processing_run

        with self.assertRaises(ValueError):
            _resolve_error_links(
                db,
                collection_run_id=None,
                announcement_id=None,
                document_id=999,
                processing_run_id=40,
            )

if __name__ == "__main__":
    unittest.main()