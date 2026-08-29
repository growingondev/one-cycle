import os
import unittest
from unittest.mock import Mock, patch

from backend.app.clients.http_json import (
    InternalServiceUnavailableError,
)
from backend.app.clients.rag_client import (
    RagAnswerResponse,
    RagEvidence,
)
from backend.app.services import chat_service
from backend.app.services.chat_service import (
    RagServiceUnavailableError,
)


class ChatServiceRuntimeTest(unittest.TestCase):

    def test_legacy_runtime_uses_direct_callable(self):
        runner = Mock(
            return_value={
                "answer": "legacy answer",
                "grounded": True,
                "evidence": [],
            }
        )

        with (
            patch.dict(
                os.environ,
                {
                    "RAG_RUNTIME": "legacy",
                },
                clear=False,
            ),
            patch.object(
                chat_service,
                "_load_answer_question",
                return_value=runner,
            ) as mock_load,
        ):
            result = chat_service.answer_question_via_rag(
                announcement_id=10,
                question="test question",
            )

        self.assertEqual(
            result.answer,
            "legacy answer",
        )

        mock_load.assert_called_once_with()

        runner.assert_called_once_with(
            announcement_id=10,
            question="test question",
        )

    def test_default_runtime_uses_http_client(self):
        http_response = RagAnswerResponse(
            result="grounded",
            answer="default http answer",
            grounded=True,
            evidence=[],
        )

        with (
            patch.dict(
                os.environ,
                {},
                clear=False,
            ),
            patch.object(
                chat_service,
                "_load_answer_question",
            ) as mock_load,
            patch(
                "backend.app.clients.rag_client."
                "answer_question",
                return_value=http_response,
            ) as mock_http,
        ):
            os.environ.pop("RAG_RUNTIME", None)

            result = chat_service.answer_question_via_rag(
                announcement_id=15,
                question="default runtime question",
            )

        self.assertEqual(
            result.answer,
            "default http answer",
        )
        self.assertTrue(result.grounded)

        mock_load.assert_not_called()

        mock_http.assert_called_once_with(
            announcement_id=15,
            question="default runtime question",
        )

    def test_rag_http_runtime_uses_http_client(self):
        http_response = RagAnswerResponse(
            result="grounded",
            answer="http answer",
            grounded=True,
            evidence=[
                RagEvidence(
                    chunk_id="chunk-001",
                    section_title="Eligibility",
                    content="evidence text",
                    score=0.95,
                )
            ],
        )

        with (
            patch.dict(
                os.environ,
                {
                    "RAG_RUNTIME": "rag_http",
                },
                clear=False,
            ),
            patch.object(
                chat_service,
                "_load_answer_question",
            ) as mock_load,
            patch(
                "backend.app.clients.rag_client."
                "answer_question",
                return_value=http_response,
            ) as mock_http,
        ):
            result = chat_service.answer_question_via_rag(
                announcement_id=20,
                question="http question",
            )

        self.assertEqual(
            result.answer,
            "http answer",
        )
        self.assertTrue(
            result.grounded
        )
        self.assertEqual(
            len(result.evidence),
            1,
        )
        self.assertEqual(
            result.evidence[0].chunk_id,
            "chunk-001",
        )

        mock_load.assert_not_called()

        mock_http.assert_called_once_with(
            announcement_id=20,
            question="http question",
        )

    def test_rag_http_client_error_is_mapped_to_service_unavailable(
        self,
    ):
        with (
            patch.dict(
                os.environ,
                {
                    "RAG_RUNTIME": "rag_http",
                },
                clear=False,
            ),
            patch.object(
                chat_service,
                "_load_answer_question",
            ) as mock_load,
            patch(
                "backend.app.clients.rag_client."
                "answer_question",
                side_effect=InternalServiceUnavailableError(
                    "RAG unavailable"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                RagServiceUnavailableError,
                "RAG unavailable",
            ):
                chat_service.answer_question_via_rag(
                    announcement_id=25,
                    question="service failure",
                )

        mock_load.assert_not_called()

    def test_invalid_runtime_is_rejected(self):
        runner = Mock(
            return_value={
                "answer": "legacy answer",
                "grounded": False,
                "evidence": [],
            }
        )

        with (
            patch.dict(
                os.environ,
                {
                    "RAG_RUNTIME": "invalid-mode",
                },
                clear=False,
            ),
            patch.object(
                chat_service,
                "_load_answer_question",
                return_value=runner,
            ),
        ):
            with self.assertRaisesRegex(
                RagServiceUnavailableError,
                "RAG_RUNTIME",
            ):
                chat_service.answer_question_via_rag(
                    announcement_id=30,
                    question="invalid runtime",
                )


if __name__ == "__main__":
    unittest.main()
