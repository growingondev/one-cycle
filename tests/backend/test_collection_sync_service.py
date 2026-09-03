import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.system_state import SystemState
from backend.app.services import collection_sync_service
from backend.app.services.collection_sync_service import (
    _run_incremental_sync_locked,
    calculate_metadata_hash,
    classify_notice_change,
    is_correction_title,
    normalize_notice_title,
)


def _notice(**overrides):
    values = {
        "source_announcement_id": "LH-002",
        "title": "2026년 청년 매입임대 모집",
        "notice_number": "2",
        "notice_type": "매입임대",
        "region": "서울",
        "announcement_date": None,
        "deadline_date": None,
        "publication_status": "접수중",
        "detail_url": "https://example.com/LH-002",
    }
    values.update(overrides)
    return values


def _existing(values, **overrides):
    defaults = {
        **values,
        "id": 10,
        "metadata_hash": calculate_metadata_hash(values),
        "normalized_title": normalize_notice_title(values["title"]),
        "change_type": "initial",
        "is_visible": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class CollectionSyncPolicyTest(unittest.TestCase):
    def test_normalize_title_removes_correction_prefixes(self):
        self.assertEqual(
            normalize_notice_title(
                "[정정공고] [수정] 2026년  청년 매입임대 모집"
            ),
            "2026년 청년 매입임대 모집",
        )
        self.assertTrue(is_correction_title("[변경공고] 모집 공고"))

    def test_new_source_id_is_classified_as_new(self):
        notice = _notice()
        self.assertEqual(
            classify_notice_change(
                None,
                notice,
                calculate_metadata_hash(notice),
            ),
            "new",
        )

    def test_new_correction_title_is_classified_as_correction(self):
        notice = _notice(title="[정정공고] 2026년 청년 매입임대 모집")
        self.assertEqual(
            classify_notice_change(
                None,
                notice,
                calculate_metadata_hash(notice),
            ),
            "correction",
        )


class IncrementalSyncFlowTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        CollectionRun.__table__.create(self.engine)
        Announcement.__table__.create(self.engine)
        Document.__table__.create(self.engine)
        SystemState.__table__.create(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

        with self.session_factory.begin() as db:
            run = CollectionRun(
                execution_id="initial-1",
                status="success",
                total_announcement_count=1,
                successful_announcement_count=1,
                failed_announcement_count=0,
            )
            db.add(run)
            db.flush()
            db.add(
                SystemState(
                    id=1,
                    active_collection_run_id=run.id,
                )
            )
            original = _notice(
                source_announcement_id="LH-001",
                detail_url="https://example.com/LH-001",
            )
            db.add(
                Announcement(
                    collection_run_id=run.id,
                    source_announcement_id="LH-001",
                    title=original["title"],
                    detail_url=original["detail_url"],
                    notice_number=original["notice_number"],
                    notice_type=original["notice_type"],
                    region=original["region"],
                    publication_status=original[
                        "publication_status"
                    ],
                    metadata_hash=calculate_metadata_hash(original),
                    normalized_title=normalize_notice_title(
                        original["title"]
                    ),
                    is_visible=True,
                )
            )

    def tearDown(self):
        self.engine.dispose()

    def _scan_result(self, notices):
        converted = []
        for notice in notices:
            converted.append(
                {
                    "source_announcement_id": notice[
                        "source_announcement_id"
                    ],
                    "title": notice["title"],
                    "notice_number": notice["notice_number"],
                    "notice_type": notice["notice_type"],
                    "region": notice["region"],
                    "post_date": notice.get("announcement_date"),
                    "deadline_date": notice.get("deadline_date"),
                    "publication_status": notice[
                        "publication_status"
                    ],
                    "detail_url": notice["detail_url"],
                }
            )
        return {
            "execution_id": "scan-test-1",
            "execution_status": "success",
            "notices": converted,
        }

    def test_unchanged_scan_does_not_run_document_pipeline(self):
        notice = _notice(
            source_announcement_id="LH-001",
            detail_url="https://example.com/LH-001",
        )

        with (
            patch.object(
                collection_sync_service,
                "SessionLocal",
                self.session_factory,
            ),
            patch.object(
                collection_sync_service.crawler_client,
                "scan_announcements",
                return_value=self._scan_result([notice]),
            ),
            patch.object(
                collection_sync_service,
                "recollect_persist_and_process",
            ) as process,
            patch.object(
                collection_sync_service,
                "_write_sync_log",
                return_value=None,
            ),
        ):
            result = _run_incremental_sync_locked()

        self.assertEqual(result["unchanged_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        process.assert_not_called()

    def test_new_notice_is_hidden_until_pipeline_succeeds(self):
        new_notice = _notice()

        def successful_processing(
            *,
            announcement_id,
            source_announcement_id_override,
            detail_url_override,
        ):
            self.assertEqual(source_announcement_id_override, "LH-002")
            self.assertEqual(
                detail_url_override,
                "https://example.com/LH-002",
            )
            with self.session_factory() as db:
                pending = db.get(Announcement, announcement_id)
                self.assertFalse(pending.is_visible)
            return {
                "status": "success",
                "new_analysis_document_count": 1,
                "document_processing": {"failed_count": 0},
            }

        with (
            patch.object(
                collection_sync_service,
                "SessionLocal",
                self.session_factory,
            ),
            patch.object(
                collection_sync_service.crawler_client,
                "scan_announcements",
                return_value=self._scan_result([new_notice]),
            ),
            patch.object(
                collection_sync_service,
                "recollect_persist_and_process",
                side_effect=successful_processing,
            ),
            patch.object(
                collection_sync_service,
                "_write_sync_log",
                return_value=None,
            ),
        ):
            result = _run_incremental_sync_locked()

        self.assertEqual(result["new_count"], 1)
        with self.session_factory() as db:
            stored = db.scalar(
                select(Announcement).where(
                    Announcement.source_announcement_id == "LH-002"
                )
            )
            self.assertTrue(stored.is_visible)

    def test_failed_new_notice_is_not_exposed_or_kept(self):
        new_notice = _notice()

        with (
            patch.object(
                collection_sync_service,
                "SessionLocal",
                self.session_factory,
            ),
            patch.object(
                collection_sync_service.crawler_client,
                "scan_announcements",
                return_value=self._scan_result([new_notice]),
            ),
            patch.object(
                collection_sync_service,
                "recollect_persist_and_process",
                return_value={
                    "status": "failed",
                    "document_processing": {"failed_count": 1},
                },
            ),
            patch.object(
                collection_sync_service,
                "_write_sync_log",
                return_value=None,
            ),
        ):
            result = _run_incremental_sync_locked()

        self.assertEqual(result["failed_count"], 1)
        with self.session_factory() as db:
            stored = db.scalar(
                select(Announcement).where(
                    Announcement.source_announcement_id == "LH-002"
                )
            )
            self.assertIsNone(stored)

    def test_updated_notice_uses_scanned_detail_url(self):
        updated = _notice(
            source_announcement_id="LH-001",
            detail_url="https://example.com/LH-001-revised",
        )

        with (
            patch.object(
                collection_sync_service,
                "SessionLocal",
                self.session_factory,
            ),
            patch.object(
                collection_sync_service.crawler_client,
                "scan_announcements",
                return_value=self._scan_result([updated]),
            ),
            patch.object(
                collection_sync_service,
                "recollect_persist_and_process",
                return_value={
                    "status": "success",
                    "new_analysis_document_count": 1,
                    "document_processing": {"failed_count": 0},
                },
            ) as process,
            patch.object(
                collection_sync_service,
                "_write_sync_log",
                return_value=None,
            ),
        ):
            result = _run_incremental_sync_locked()

        self.assertEqual(result["updated_count"], 1)
        process.assert_called_once_with(
            announcement_id=1,
            source_announcement_id_override="LH-001",
            detail_url_override="https://example.com/LH-001-revised",
        )
        with self.session_factory() as db:
            stored = db.get(Announcement, 1)
            self.assertEqual(stored.detail_url, updated["detail_url"])

    def test_successful_correction_replaces_visible_notice(self):
        correction = _notice(
            title="[정정공고] 2026년 청년 매입임대 모집"
        )

        with (
            patch.object(
                collection_sync_service,
                "SessionLocal",
                self.session_factory,
            ),
            patch.object(
                collection_sync_service.crawler_client,
                "scan_announcements",
                return_value=self._scan_result([correction]),
            ),
            patch.object(
                collection_sync_service,
                "recollect_persist_and_process",
                return_value={
                    "status": "success",
                    "new_analysis_document_count": 1,
                    "document_processing": {"failed_count": 0},
                },
            ),
            patch.object(
                collection_sync_service,
                "_write_sync_log",
                return_value=None,
            ),
        ):
            result = _run_incremental_sync_locked()

        self.assertEqual(result["correction_count"], 1)
        with self.session_factory() as db:
            original = db.scalar(
                select(Announcement).where(
                    Announcement.source_announcement_id == "LH-001"
                )
            )
            corrected = db.scalar(
                select(Announcement).where(
                    Announcement.source_announcement_id == "LH-002"
                )
            )
            self.assertFalse(original.is_visible)
            self.assertTrue(corrected.is_visible)
            self.assertEqual(
                corrected.supersedes_announcement_id,
                original.id,
            )

    def test_same_source_and_metadata_are_unchanged(self):
        notice = _notice(source_announcement_id="LH-001")
        existing = _existing(notice)
        self.assertEqual(
            classify_notice_change(
                existing,
                notice,
                calculate_metadata_hash(notice),
            ),
            "unchanged",
        )

    def test_same_source_with_changed_deadline_is_updated(self):
        original = _notice(source_announcement_id="LH-001")
        changed = {**original, "deadline_date": "2026-09-30"}
        existing = _existing(original)
        self.assertEqual(
            classify_notice_change(
                existing,
                changed,
                calculate_metadata_hash(changed),
            ),
            "updated",
        )

    def test_hidden_pending_notice_is_retried(self):
        notice = _notice(source_announcement_id="LH-001")
        existing = _existing(
            notice,
            is_visible=False,
            change_type="correction",
        )
        self.assertEqual(
            classify_notice_change(
                existing,
                notice,
                calculate_metadata_hash(notice),
            ),
            "correction",
        )


if __name__ == "__main__":
    unittest.main()
