import unittest
from unittest.mock import MagicMock, patch

from backend.app.services.collection_service import (
    persist_collection_result,
)
from backend.app.services.document_role_service import (
    DOCUMENT_ROLE_PRIMARY,
    DOCUMENT_ROLE_SUPPORTING,
    DOCUMENT_ROLE_UNKNOWN,
    classify_document_role,
)


class DocumentRoleServiceTest(unittest.TestCase):

    def test_primary_korean_notice(self):
        filename = (
            "(260819)목포용해5행복주택"
            "예비입주자공고.hwpx"
        )

        self.assertEqual(
            classify_document_role(filename),
            DOCUMENT_ROLE_PRIMARY,
        )

    def test_primary_main_notice(self):
        self.assertEqual(
            classify_document_role(
                "main_notice.hwpx"
            ),
            DOCUMENT_ROLE_PRIMARY,
        )

    def test_supporting_privacy_document(self):
        self.assertEqual(
            classify_document_role(
                "개인정보수집이용및제3자제공동의서.hwpx"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_qna_document(self):
        self.assertEqual(
            classify_document_role(
                "26년든든전세주택_QnA.hwpx"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_qa_even_when_filename_contains_notice(self):
        filename = (
            "여기가_입주자모집공고문_"
            "QA_최종(20260513공고용)_프리웰.hwpx"
        )

        self.assertEqual(
            classify_document_role(filename),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_confirmation_document(self):
        self.assertEqual(
            classify_document_role(
                "붙임5.입주자격완화확약서.hwpx"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_written_form_document(self):
        filename = (
            "(필수양식)고창율계예비자모집"
            "공급신청서등작성서류.hwpx"
        )

        self.assertEqual(
            classify_document_role(filename),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_generic_submission_documents(self):
        self.assertEqual(
            classify_document_role(
                "붙임_제출서류양식.hwpx"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_english_required_documents(self):
        self.assertEqual(
            classify_document_role(
                "required_documents.hwpx"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_supporting_english_supplement(self):
        self.assertEqual(
            classify_document_role(
                "supplement.hwp"
            ),
            DOCUMENT_ROLE_SUPPORTING,
        )

    def test_unknown_document(self):
        self.assertEqual(
            classify_document_role(
                "random_attachment.hwpx"
            ),
            DOCUMENT_ROLE_UNKNOWN,
        )


class CollectionDocumentRolePersistenceTest(
    unittest.TestCase
):

    def test_collection_persists_roles_and_analysis_ids(
        self,
    ):
        crawler_result = {
            "execution_id": "role-persistence-test",
            "execution_status": "success",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "fatal_error": None,
            "data": [
                {
                    "source_announcement_id": "LH-ROLE-001",
                    "title": "테스트 행복주택 모집공고",
                    "detail_url": (
                        "https://example.com/notices/1"
                    ),
                    "notice_type": "행복주택",
                    "region": "서울특별시",
                    "post_date": "2026-08-19",
                    "publication_status": "공고중",
                    "documents": [
                        {
                            "file_name": (
                                "행복주택예비입주자"
                                "모집공고문.hwpx"
                            ),
                            "file_format": "hwpx",
                            "storage_path": (
                                "/data/main.hwpx"
                            ),
                            "file_size_bytes": 100,
                            "checksum_sha256": "primary-hash",
                            "download_status": "completed",
                            "error_message": None,
                        },
                        {
                            "file_name": (
                                "개인정보수집이용"
                                "동의서.hwpx"
                            ),
                            "file_format": "hwpx",
                            "storage_path": (
                                "/data/privacy.hwpx"
                            ),
                            "file_size_bytes": 50,
                            "checksum_sha256": (
                                "supporting-hash"
                            ),
                            "download_status": "completed",
                            "error_message": None,
                        },
                    ],
                }
            ],
        }

        db = MagicMock()
        db.scalar.return_value = None

        next_document_id = [10]

        def flush_side_effect():
            for call in db.add.call_args_list:
                obj = call.args[0]

                if (
                    obj.__class__.__name__
                    == "CollectionRun"
                    and obj.id is None
                ):
                    obj.id = 1

                elif (
                    obj.__class__.__name__
                    == "Announcement"
                    and obj.id is None
                ):
                    obj.id = 2

                elif (
                    obj.__class__.__name__
                    == "Document"
                    and obj.id is None
                ):
                    obj.id = next_document_id[0]
                    next_document_id[0] += 1

        db.flush.side_effect = flush_side_effect

        with patch(
            "backend.app.services.collection_service."
            "SessionLocal"
        ) as session_local:
            (
                session_local.begin.return_value
                .__enter__.return_value
            ) = db

            result = persist_collection_result(
                crawler_result
            )

        documents = [
            call.args[0]
            for call in db.add.call_args_list
            if (
                call.args[0].__class__.__name__
                == "Document"
            )
        ]

        self.assertEqual(
            len(documents),
            2,
        )

        self.assertEqual(
            documents[0].document_role,
            DOCUMENT_ROLE_PRIMARY,
        )

        self.assertEqual(
            documents[1].document_role,
            DOCUMENT_ROLE_SUPPORTING,
        )

        self.assertEqual(
            result["document_ids"],
            [10, 11],
        )

        self.assertEqual(
            result["analysis_document_ids"],
            [10],
        )

        self.assertEqual(
            result["document_count"],
            2,
        )

        self.assertEqual(
            result["analysis_document_count"],
            1,
        )


class ApplicationFormRoleTest(
    unittest.TestCase
):
    def test_application_form_is_supporting(
        self,
    ):
        from backend.app.services.document_role_service import (
            classify_document_role,
        )

        self.assertEqual(
            classify_document_role(
                "\uad6d\ubbfc\uc784\ub300_"
                "\uc2e0\uccad\uc591\uc2dd.hwpx"
            ),
            "supporting",
        )

if __name__ == "__main__":
    unittest.main()