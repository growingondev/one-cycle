import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.chat_service import answer_question_via_rag
from backend.app.services.collection_service import (
    VALID_DOCUMENT_FORMATS,
    _validate_collection_result,
    persist_collection_result,
)
from backend.app.services.error_log_service import (
    VALID_ERROR_TYPES,
    _resolve_error_links,
    _validate_error_input,
)
from backend.app.services.pipeline_gateway import (
    PipelineUnavailableError,
    collect_announcements,
)
from backend.app.services.pipeline_persistence import (
    get_registered_document_context,
    mark_processing_run_failed,
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

    def test_collection_persists_notice_type(self):
        result = {
            "execution_id": "notice_type_test",
            "execution_status": "success",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "fatal_error": None,
            "data": [
                {
                    "source_announcement_id": "LH-001",
                    "title": "테스트 공고",
                    "detail_url": "https://example.com/1",
                    "notice_type": "공공임대",
                    "region": "대구광역시",
                    "post_date": "2026-08-14",
                    "publication_status": "공고중",
                    "documents": [],
                }
            ],
        }

        db = MagicMock()
        db.scalar.return_value = None

        def flush_side_effect():
            for call in db.add.call_args_list:
                obj = call.args[0]
                if obj.__class__.__name__ == "CollectionRun":
                    obj.id = 1
                elif obj.__class__.__name__ == "Announcement":
                    obj.id = 2

        db.flush.side_effect = flush_side_effect

        with patch(
            "backend.app.services.collection_service.SessionLocal"
        ) as session_local:
            session_local.begin.return_value.__enter__.return_value = db
            persist_collection_result(result)

        announcements = [
            call.args[0]
            for call in db.add.call_args_list
            if call.args[0].__class__.__name__ == "Announcement"
        ]

        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].notice_type, "공공임대")


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


class PipelinePersistenceContractTest(unittest.TestCase):
    def test_registered_document_context_includes_storage_path(self):
        db = MagicMock()

        announcement = SimpleNamespace(
            id=20,
            source_announcement_id="LH-TEST-001",
        )
        document = SimpleNamespace(
            id=30,
            original_filename="sample.hwp",
            document_format="hwp",
            storage_path="/data/documents/sample.hwp",
        )

        db.execute.return_value.one_or_none.return_value = (
            announcement,
            document,
        )

        with patch(
            "backend.app.services.pipeline_persistence.SessionLocal"
        ) as session_local:
            session_local.return_value.__enter__.return_value = db

            result = get_registered_document_context(
                document_id=30,
            )

        self.assertEqual(
            result["announcement_key"],
            "LH-TEST-001",
        )
        self.assertEqual(
            result["announcement_db_id"],
            20,
        )
        self.assertEqual(
            result["document_db_id"],
            30,
        )
        self.assertEqual(
            result["filename"],
            "sample.hwp",
        )
        self.assertEqual(
            result["format"],
            "hwp",
        )
        self.assertEqual(
            result["storage_path"],
            "/data/documents/sample.hwp",
        )

    def test_mark_processing_run_failed_preserves_verification(self):
        db = MagicMock()

        processing_run = SimpleNamespace(
            id=40,
            document_id=30,
            execution_status="succeeded",
            verification_status="pass",
            current_stage="embedding",
            error_stage=None,
            error_code=None,
            error_message=None,
            exit_code=0,
            finished_at=None,
            is_active=False,
        )

        db.get.return_value = processing_run

        with patch(
            "backend.app.services.pipeline_persistence.SessionLocal"
        ) as session_local:
            session_local.begin.return_value.__enter__.return_value = db

            result = mark_processing_run_failed(
                40,
                stage="key_information",
                error_code="KEY_INFORMATION_EXTRACTION_FAILED",
                error_message="핵심정보 추출 실패",
                exit_code=1,
            )

        self.assertEqual(
            processing_run.execution_status,
            "failed",
        )
        self.assertEqual(
            processing_run.current_stage,
            "key_information",
        )
        self.assertEqual(
            processing_run.error_stage,
            "key_information",
        )
        self.assertEqual(
            processing_run.error_code,
            "KEY_INFORMATION_EXTRACTION_FAILED",
        )
        self.assertEqual(
            processing_run.error_message,
            "핵심정보 추출 실패",
        )
        self.assertEqual(
            processing_run.exit_code,
            1,
        )
        self.assertIsNotNone(
            processing_run.finished_at,
        )
        self.assertFalse(
            processing_run.is_active,
        )

        # Verification 단계가 이미 pass였다면 그대로 유지되어야 한다.
        self.assertEqual(
            processing_run.verification_status,
            "pass",
        )

        self.assertEqual(
            result["execution_status"],
            "failed",
        )
        self.assertEqual(
            result["verification_status"],
            "pass",
        )
        self.assertEqual(
            result["current_stage"],
            "key_information",
        )
        self.assertFalse(
            result["is_active"],
        )

        db.flush.assert_called_once()

    def test_active_processing_run_cannot_be_marked_failed(self):
        db = MagicMock()

        processing_run = SimpleNamespace(
            id=40,
            document_id=30,
            execution_status="succeeded",
            verification_status="pass",
            current_stage="embedding",
            error_stage=None,
            error_code=None,
            error_message=None,
            exit_code=0,
            finished_at=None,
            is_active=True,
        )

        db.get.return_value = processing_run

        with patch(
            "backend.app.services.pipeline_persistence.SessionLocal"
        ) as session_local:
            session_local.begin.return_value.__enter__.return_value = db

            with self.assertRaises(RuntimeError):
                mark_processing_run_failed(
                    40,
                    stage="key_information",
                    error_code="KEY_INFORMATION_EXTRACTION_FAILED",
                    error_message="핵심정보 추출 실패",
                )

        # 기존 active ProcessingRun은 변경되지 않아야 한다.
        self.assertEqual(
            processing_run.execution_status,
            "succeeded",
        )
        self.assertEqual(
            processing_run.verification_status,
            "pass",
        )
        self.assertTrue(
            processing_run.is_active,
        )

        db.flush.assert_not_called()


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