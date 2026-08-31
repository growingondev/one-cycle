from datetime import date
import unittest
from unittest.mock import MagicMock, patch

from backend.app.services.announcement_service import (
    list_active_announcements,
)
from backend.app.services.collection_service import (
    persist_collection_result,
)


class CollectionDeadlineContractTest(unittest.TestCase):
    def test_collection_persists_deadline_date(self):
        result = {
            "execution_id": "deadline_date_test",
            "execution_status": "success",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "fatal_error": None,
            "data": [
                {
                    "source_announcement_id": "LH-DEADLINE-001",
                    "title": "Deadline persistence test",
                    "detail_url": "https://example.com/deadline",
                    "notice_type": "public-rental",
                    "region": "seoul",
                    "post_date": "2026-08-31",
                    "deadline_date": "2026.09.18",
                    "publication_status": "open",
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
            announcements[0].deadline_date,
            date(2026, 9, 18),
        )


class AnnouncementListDeadlineContractTest(unittest.TestCase):
    def test_deadline_prefers_announcement_and_keeps_key_info_fallback(
        self,
    ):
        db = MagicMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            {
                "id": 10,
                "title": "Deadline list test",
                "notice_type": "public-rental",
                "region": "seoul",
                "announcement_date": date(2026, 8, 31),
                "publication_status": "open",
                "deadline_date": "2026-09-18",
            }
        ]

        db.execute.side_effect = [
            count_result,
            rows_result,
        ]

        response = list_active_announcements(
            db=db,
            page=1,
            size=10,
            search=None,
            region=None,
            status_filter=None,
        )

        self.assertEqual(
            response.items[0].deadlineDate,
            "2026-09-18",
        )

        list_query = str(
            db.execute.call_args_list[1].args[0]
        )

        self.assertIn("COALESCE(", list_query)
        self.assertIn("a.deadline_date::text", list_query)
        self.assertIn(
            "ki.application_period ->> 'end'",
            list_query,
        )

        self.assertLess(
            list_query.index("a.deadline_date::text"),
            list_query.index(
                "ki.application_period ->> 'end'"
            ),
        )


if __name__ == "__main__":
    unittest.main()
