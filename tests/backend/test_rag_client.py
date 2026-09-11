import unittest
from unittest.mock import patch

from backend.app.clients.http_json import (
    InternalServiceResponseError,
)
from backend.app.clients.rag_client import (
    answer_question,
)


class RagClientTest(unittest.TestCase):
    @patch(
        "backend.app.clients.rag_client.post_json"
    )
    def test_answer_question_sends_expected_request(
        self,
        post_json,
    ):
        post_json.return_value = {
            "result": "grounded",
            "answer": "The application period is in September.",
            "grounded": True,
            "evidence": [
                {
                    "chunk_id": "chunk-001",
                    "section_title": "Application schedule",
                    "content": (
                        "The application period is in September."
                    ),
                    "score": 0.84,
                }
            ],
        }

        result = answer_question(
            announcement_id=1,
            question="  When is the application period?  ",
            base_url="http://rag:8000/",
            timeout_seconds=30,
        )

        post_json.assert_called_once_with(
            url="http://rag:8000/v1/rag/answer",
            payload={
                "announcement_id": 1,
                "question": "When is the application period?",
            },
            timeout_seconds=30,
        )

        self.assertEqual(
            result.result,
            "grounded",
        )
        self.assertTrue(result.grounded)
        self.assertEqual(
            result.evidence[0].chunk_id,
            "chunk-001",
        )

    @patch(
        "backend.app.clients.rag_client.post_json"
    )
    def test_answer_question_accepts_no_evidence(
        self,
        post_json,
    ):
        post_json.return_value = {
            "result": "no_evidence",
            "answer": (
                "The provided announcement does not "
                "contain supporting evidence."
            ),
            "grounded": False,
            "evidence": [],
        }

        result = answer_question(
            announcement_id=1,
            question="Unknown question",
            base_url="http://rag:8000",
            timeout_seconds=30,
        )

        self.assertEqual(
            result.result,
            "no_evidence",
        )
        self.assertFalse(result.grounded)
        self.assertEqual(result.evidence, [])

    @patch(
        "backend.app.clients.rag_client.post_json"
    )
    def test_answer_question_accepts_unsupported(
        self,
        post_json,
    ):
        post_json.return_value = {
            "result": "unsupported",
            "answer": (
                "This announcement is not supported "
                "by the current MVP."
            ),
            "grounded": False,
            "evidence": [],
        }

        result = answer_question(
            announcement_id=2,
            question="When is the application period?",
            base_url="http://rag:8000",
            timeout_seconds=30,
        )

        self.assertEqual(
            result.result,
            "unsupported",
        )
        self.assertFalse(result.grounded)

    @patch(
        "backend.app.clients.rag_client.post_json"
    )
    def test_answer_question_rejects_invalid_response(
        self,
        post_json,
    ):
        post_json.return_value = {
            "answer": "Invalid response",
            "grounded": True,
            "evidence": [],
        }

        with self.assertRaises(
            InternalServiceResponseError
        ):
            answer_question(
                announcement_id=1,
                question="When is the application period?",
                base_url="http://rag:8000",
                timeout_seconds=30,
            )


if __name__ == "__main__":
    unittest.main()
