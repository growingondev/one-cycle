import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.collection_publish_service import (
    _validate_collection_run_for_publish,
    _validate_primary_document_for_publish,
)
from backend.app.services.document_role_service import (
    DOCUMENT_ROLE_PRIMARY,
    DOCUMENT_ROLE_SUPPORTING,
    DOCUMENT_ROLE_UNKNOWN,
)


class CollectionPublishServiceTest(unittest.TestCase):

    def test_publish_validates_only_primary_documents(self):
        """
        primary만 AI 처리 결과를 검증하고,
        supporting은 처리 대상에서 제외한다.

        primary가 없는 공고는 metadata-only 공고로 허용한다.

        한 Announcement에 primary가 여러 개 존재할 수도 있다.
        """

        db = MagicMock()

        collection_run = SimpleNamespace(
            id=1,
            status="success",
            failed_announcement_count=0,
            successful_announcement_count=3,
            total_announcement_count=3,
        )

        announcement_1 = SimpleNamespace(id=101)
        announcement_2 = SimpleNamespace(id=102)
        announcement_3 = SimpleNamespace(id=103)

        primary_1 = SimpleNamespace(
            id=201,
            document_role=DOCUMENT_ROLE_PRIMARY,
            original_filename="공고문1.hwpx",
        )

        supporting_1 = SimpleNamespace(
            id=202,
            document_role=DOCUMENT_ROLE_SUPPORTING,
            original_filename="개인정보동의서.hwpx",
        )

        primary_2 = SimpleNamespace(
            id=203,
            document_role=DOCUMENT_ROLE_PRIMARY,
            original_filename="공고문2.hwpx",
        )

        primary_3 = SimpleNamespace(
            id=204,
            document_role=DOCUMENT_ROLE_PRIMARY,
            original_filename="공고문3.hwpx",
        )

        db.get.return_value = collection_run

        # 호출 순서:
        # 1. CollectionRun의 Announcement 목록
        # 2. announcement_1 Document 목록
        # 3. announcement_2 Document 목록
        # 4. announcement_3 Document 목록
        db.scalars.side_effect = [
            [
                announcement_1,
                announcement_2,
                announcement_3,
            ],
            [
                primary_1,
                supporting_1,
            ],
            [],
            [
                primary_2,
                primary_3,
            ],
        ]

        with patch(
            "backend.app.services.collection_publish_service."
            "_validate_primary_document_for_publish"
        ) as validate_primary:
            validate_primary.side_effect = [
                (5, 5),
                (7, 7),
                (3, 3),
            ]

            result = _validate_collection_run_for_publish(
                db,
                collection_run_id=1,
            )

        validated_document_ids = [
            call.args[1].id
            for call in validate_primary.call_args_list
        ]

        self.assertEqual(
            validated_document_ids,
            [201, 203, 204],
        )

        self.assertEqual(
            validate_primary.call_count,
            3,
        )

        self.assertEqual(
            result["collection_run_id"],
            1,
        )

        self.assertEqual(
            result["announcement_count"],
            3,
        )

        self.assertEqual(
            result["document_count"],
            4,
        )

        self.assertEqual(
            result["analysis_document_count"],
            3,
        )

        self.assertEqual(
            result["supporting_document_count"],
            1,
        )

        self.assertEqual(
            result["metadata_only_announcement_count"],
            1,
        )

        self.assertEqual(
            result["chunk_count"],
            15,
        )

        self.assertEqual(
            result["embedding_chunk_count"],
            15,
        )

    def test_supporting_only_announcement_is_metadata_only(self):
        """
        supporting 문서만 있고 primary가 없는 공고도
        metadata-only 공고로 publish할 수 있다.
        """

        db = MagicMock()

        collection_run = SimpleNamespace(
            id=1,
            status="success",
            failed_announcement_count=0,
            successful_announcement_count=1,
            total_announcement_count=1,
        )

        announcement = SimpleNamespace(
            id=101,
        )

        supporting_document = SimpleNamespace(
            id=201,
            document_role=DOCUMENT_ROLE_SUPPORTING,
            original_filename="위임장.hwpx",
        )

        db.get.return_value = collection_run

        db.scalars.side_effect = [
            [announcement],
            [supporting_document],
        ]

        with patch(
            "backend.app.services.collection_publish_service."
            "_validate_primary_document_for_publish"
        ) as validate_primary:
            result = _validate_collection_run_for_publish(
                db,
                collection_run_id=1,
            )

        validate_primary.assert_not_called()

        self.assertEqual(
            result["announcement_count"],
            1,
        )

        self.assertEqual(
            result["document_count"],
            1,
        )

        self.assertEqual(
            result["analysis_document_count"],
            0,
        )

        self.assertEqual(
            result["supporting_document_count"],
            1,
        )

        self.assertEqual(
            result["metadata_only_announcement_count"],
            1,
        )

        self.assertEqual(
            result["chunk_count"],
            0,
        )

        self.assertEqual(
            result["embedding_chunk_count"],
            0,
        )

    def test_documentless_announcement_is_metadata_only(self):
        """
        HWP/HWPX Document 자체가 없는 공고도
        metadata-only 공고로 publish할 수 있다.
        """

        db = MagicMock()

        collection_run = SimpleNamespace(
            id=1,
            status="success",
            failed_announcement_count=0,
            successful_announcement_count=1,
            total_announcement_count=1,
        )

        announcement = SimpleNamespace(
            id=101,
        )

        db.get.return_value = collection_run

        db.scalars.side_effect = [
            [announcement],
            [],
        ]

        with patch(
            "backend.app.services.collection_publish_service."
            "_validate_primary_document_for_publish"
        ) as validate_primary:
            result = _validate_collection_run_for_publish(
                db,
                collection_run_id=1,
            )

        validate_primary.assert_not_called()

        self.assertEqual(
            result["document_count"],
            0,
        )

        self.assertEqual(
            result["analysis_document_count"],
            0,
        )

        self.assertEqual(
            result["supporting_document_count"],
            0,
        )

        self.assertEqual(
            result["metadata_only_announcement_count"],
            1,
        )

    def test_unknown_document_blocks_publish(self):
        """
        document_role을 판별하지 못한 문서가 있으면
        publish하지 않는다.
        """

        db = MagicMock()

        collection_run = SimpleNamespace(
            id=1,
            status="success",
            failed_announcement_count=0,
            successful_announcement_count=1,
            total_announcement_count=1,
        )

        announcement = SimpleNamespace(
            id=101,
        )

        unknown_document = SimpleNamespace(
            id=201,
            document_role=DOCUMENT_ROLE_UNKNOWN,
            original_filename="unknown.hwpx",
        )

        db.get.return_value = collection_run

        db.scalars.side_effect = [
            [announcement],
            [unknown_document],
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "역할을 판별하지 못한 Document",
        ):
            _validate_collection_run_for_publish(
                db,
                collection_run_id=1,
            )

    def test_primary_document_requires_completed_download(self):
        """
        primary 문서는 download completed가 아니면
        publish할 수 없다.
        """

        db = MagicMock()

        document = SimpleNamespace(
            id=201,
            download_status="failed",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "다운로드가 완료되지 않은 primary Document",
        ):
            _validate_primary_document_for_publish(
                db,
                document,
            )

    def test_primary_document_requires_active_processing_run(self):
        """
        primary 문서는 active ProcessingRun이 반드시 필요하다.
        """

        db = MagicMock()

        document = SimpleNamespace(
            id=201,
            download_status="completed",
        )

        db.scalar.return_value = None

        with self.assertRaisesRegex(
            RuntimeError,
            "active ProcessingRun이 없는 primary Document",
        ):
            _validate_primary_document_for_publish(
                db,
                document,
            )


if __name__ == "__main__":
    unittest.main()