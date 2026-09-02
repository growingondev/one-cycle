from datetime import date
import unittest
from unittest.mock import MagicMock, patch

from backend.app.services.announcement_service import (
    list_active_announcements,
)
from backend.app.services.collection_service import (
    persist_collection_result,
)


class CollectionNoticeNumberContractTest(unittest.TestCase):
    def test_collection_persists_notice_number(self):
        result = {
            "execution_id": "notice_number_test",
            "execution_status": "success",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "fatal_error": None,
            "data": [
                {
                    "source_announcement_id": "LH-NOTICE-001",
                    "notice_number": "77",
                    "title": "Notice number persistence test",
                    "detail_url": "https://example.com/notice",
                    "notice_type": "국민임대",
                    "region": "경기도",
                    "post_date": "2026-09-01",
                    "deadline_date": "2026-09-10",
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
        self.assertEqual(
            announcements[0].notice_number,
            "77",
        )


class AnnouncementListNoticeNumberContractTest(unittest.TestCase):
    def _make_db(self):
        db = MagicMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            {
                "id": 153,
                "notice_number": "77",
                "title": "LH notice number API test",
                "notice_type": "국민임대",
                "region": "경기도",
                "announcement_date": date(2026, 9, 1),
                "publication_status": "공고중",
                "deadline_date": "2026-09-10",
            }
        ]

        db.execute.side_effect = [
            count_result,
            rows_result,
        ]

        return db

    def test_list_returns_lh_notice_number(self):
        db = self._make_db()

        response = list_active_announcements(
            db=db,
            page=1,
            size=10,
            search=None,
            region=None,
            status_filter=None,
            sort_order="latest",
        )

        self.assertEqual(
            response.items[0].id,
            153,
        )
        self.assertEqual(
            response.items[0].notice_number,
            "77",
        )

    def test_latest_sort_uses_numeric_notice_number_desc(self):
        db = self._make_db()

        list_active_announcements(
            db=db,
            page=1,
            size=10,
            search=None,
            region=None,
            status_filter=None,
            sort_order="latest",
        )

        list_query = str(
            db.execute.call_args_list[1].args[0]
        )

        self.assertIn(
            "a.notice_number ~ '^[0-9]+$'",
            list_query,
        )
        self.assertIn(
            "a.notice_number::integer",
            list_query,
        )
        self.assertLess(
            list_query.index(
                "a.announcement_date DESC NULLS LAST"
            ),
            list_query.index(
                "a.notice_number::integer"
            ),
        )

    def test_oldest_sort_uses_numeric_notice_number_asc(self):
        db = self._make_db()

        list_active_announcements(
            db=db,
            page=1,
            size=10,
            search=None,
            region=None,
            status_filter=None,
            sort_order="oldest",
        )

        list_query = str(
            db.execute.call_args_list[1].args[0]
        )

        self.assertIn(
            "a.notice_number::integer",
            list_query,
        )
        self.assertLess(
            list_query.index(
                "a.announcement_date ASC NULLS LAST"
            ),
            list_query.index(
                "a.notice_number::integer"
            ),
        )


if __name__ == "__main__":
    unittest.main()
