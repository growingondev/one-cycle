import hashlib
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.services import collection_service, integration_service


@pytest.fixture
def storage_db(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (CollectionRun, Announcement, Document):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(collection_service, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "crawler_staging_dir", str(tmp_path))
    with sessions.begin() as db:
        run = CollectionRun(execution_id="old", status="success")
        db.add(run)
        db.flush()
        for source in ("A", "B"):
            db.add(
                Announcement(
                    collection_run_id=run.id,
                    source_announcement_id=source,
                    title=source,
                    detail_url=f"https://example.test/{source}",
                )
            )
    yield sessions, tmp_path
    engine.dispose()


def add_old(sessions, root, *, source="A", missing=False, legacy=False, content=b"old"):
    path = (
        root
        / ("notices/A/versions/legacy" if legacy else f"execution_old/{source}")
        / "공고문.hwpx"
    )
    if not missing:
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
    with sessions.begin() as db:
        announcement = db.scalar(
            select(Announcement).where(Announcement.source_announcement_id == source)
        )
        document = Document(
            announcement_id=announcement.id,
            original_filename=path.name,
            document_format="hwpx",
            document_role="primary",
            storage_path=str(path),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            download_status="completed",
        )
        db.add(document)
        db.flush()
        return announcement.id, document.id, path


def new_result(root, *, source="A", content=b"old", execution="recollect_new"):
    path = root / execution / source / "공고문.hwpx"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path, {
        "execution_id": execution,
        "status": "success",
        "source_announcement_id": source,
        "data": {
            "documents": [
                {
                    "file_name": path.name,
                    "file_format": "hwpx",
                    "download_status": "completed",
                    "checksum_sha256": hashlib.sha256(content).hexdigest(),
                    "storage_path": str(path),
                    "file_size_bytes": len(content),
                }
            ]
        },
        "errors": [],
    }


@pytest.mark.parametrize("legacy", [False, True])
def test_identical_recollection_deletes_only_new_duplicate(storage_db, legacy):
    sessions, root = storage_db
    announcement_id, document_id, old = add_old(sessions, root, legacy=legacy)
    new, response = new_result(root)
    with patch.object(
        collection_service.crawler_client,
        "recollect_announcement",
        return_value=response,
    ):
        result = collection_service.recollect_and_persist(
            announcement_id=announcement_id
        )
    assert result["reused_document_ids"] == [document_id]
    assert result["new_document_ids"] == []
    assert result["duplicate_cleanup_errors"] == []
    assert old.read_bytes() == b"old"
    assert not new.exists()
    with sessions() as db:
        assert db.get(Document, document_id).storage_path == str(old)
        assert db.scalar(select(func.count(Document.id))) == 1


def test_missing_original_restores_path_and_reprocesses_primary(storage_db):
    sessions, root = storage_db
    announcement_id, document_id, old = add_old(
        sessions, root, missing=True, legacy=True
    )
    new, response = new_result(root)
    with (
        patch.object(
            collection_service.crawler_client,
            "recollect_announcement",
            return_value=response,
        ),
        patch.object(
            integration_service,
            "process_document_ids",
            return_value={"failed_count": 0},
        ) as process,
    ):
        result = integration_service.recollect_persist_and_process(
            announcement_id=announcement_id
        )
    assert result["reused_document_ids"] == [document_id]
    process.assert_called_once_with([document_id])
    assert new.exists() and not old.exists()
    with sessions() as db:
        assert db.get(Document, document_id).storage_path == str(new)


def test_changed_checksum_creates_new_document_and_processes_it(storage_db):
    sessions, root = storage_db
    announcement_id, old_id, old = add_old(sessions, root)
    new, response = new_result(root, content=b"changed")
    with (
        patch.object(
            collection_service.crawler_client,
            "recollect_announcement",
            return_value=response,
        ),
        patch.object(
            integration_service,
            "process_document_ids",
            return_value={"failed_count": 0},
        ) as process,
    ):
        result = integration_service.recollect_persist_and_process(
            announcement_id=announcement_id
        )
    assert len(result["new_document_ids"]) == 1
    assert old_id not in result["new_document_ids"]
    process.assert_called_once_with(result["new_document_ids"])
    assert old.read_bytes() == b"old" and new.read_bytes() == b"changed"


def test_same_filename_on_different_notice_is_not_reused(storage_db):
    sessions, root = storage_db
    _, old_id, old = add_old(sessions, root, source="B")
    with sessions() as db:
        target_id = db.scalar(
            select(Announcement.id).where(Announcement.source_announcement_id == "A")
        )
    new, response = new_result(root)
    with patch.object(
        collection_service.crawler_client,
        "recollect_announcement",
        return_value=response,
    ):
        result = collection_service.recollect_and_persist(announcement_id=target_id)
    assert result["reused_document_ids"] == []
    assert old_id not in result["new_document_ids"]
    assert old.exists() and new.exists()


@pytest.mark.parametrize(
    "bad", ["outside_run", "other_notice", "checksum", "execution_traversal"]
)
def test_duplicate_cleanup_rejects_untrusted_path_or_checksum(storage_db, bad):
    sessions, root = storage_db
    announcement_id, _, old = add_old(sessions, root)
    new, response = new_result(root)
    raw = response["data"]["documents"][0]
    if bad == "outside_run":
        raw["storage_path"] = str(old)
    elif bad == "other_notice":
        raw["storage_path"] = str(root / "recollect_new/B/공고문.hwpx")
    elif bad == "checksum":
        new.write_bytes(b"corrupt")
    else:
        response["execution_id"] = "../execution_old"
    with patch.object(
        collection_service.crawler_client,
        "recollect_announcement",
        return_value=response,
    ), pytest.raises(ValueError):
        collection_service.recollect_and_persist(announcement_id=announcement_id)
    assert old.exists() and new.exists()


def test_failed_db_commit_does_not_delete_new_duplicate(storage_db):
    sessions, root = storage_db
    announcement_id, _, old = add_old(sessions, root)
    new, response = new_result(root)
    from sqlalchemy import event

    def reject_commit(session):
        raise RuntimeError("commit failed")

    event.listen(sessions, "before_commit", reject_commit)
    try:
        with patch.object(
            collection_service.crawler_client,
            "recollect_announcement",
            return_value=response,
        ), pytest.raises(RuntimeError, match="commit failed"):
            collection_service.recollect_and_persist(
                announcement_id=announcement_id
            )
    finally:
        event.remove(sessions, "before_commit", reject_commit)
    assert old.exists() and new.exists()


def test_file_referenced_by_another_document_is_not_removed(storage_db):
    sessions, root = storage_db
    announcement_id, _, old = add_old(sessions, root)
    new, response = new_result(root)
    with sessions.begin() as db:
        db.add(
            Document(
                announcement_id=announcement_id,
                original_filename="other.hwpx",
                document_format="hwpx",
                document_role="primary",
                download_status="completed",
                storage_path=str(new),
                checksum_sha256="another-checksum",
            )
        )
    with patch.object(
        collection_service.crawler_client,
        "recollect_announcement",
        return_value=response,
    ):
        collection_service.recollect_and_persist(announcement_id=announcement_id)
    assert old.exists() and new.exists()


def test_full_collection_download_failure_is_available_for_targeted_admin_retry(
    storage_db,
):
    _, root = storage_db
    _, response = new_result(root)
    document = response["data"]["documents"][0]
    document.update(download_status="failed", storage_path=None, checksum_sha256=None)
    response = {
        "execution_id": "execution_failed",
        "execution_status": "partial",
        "total_count": 1,
        "success_count": 0,
        "failed_count": 1,
        "data": [
            {
                "source_announcement_id": "NEW",
                "title": "새 공고",
                "detail_url": "https://example.test/NEW",
                "documents": [document],
            }
        ],
        "errors": [
            {
                "source_announcement_id": "NEW",
                "file_name": "공고문.hwpx",
                "error_type": "download",
                "stage": "download",
                "error_code": "DOWNLOAD_TIMEOUT",
                "message": "download failed",
            }
        ],
    }
    with (
        patch.object(
            collection_service.crawler_client,
            "crawl_announcements",
            return_value=response,
        ),
        patch.object(
            collection_service, "record_error", return_value={"error_id": 9}
        ) as record,
    ):
        result = collection_service.collect_and_persist()
    assert result["analysis_document_ids"] == []
    assert result["error_ids"] == [9]
    assert record.call_args.kwargs["announcement_id"] == result["announcement_ids"][0]
    assert record.call_args.kwargs["document_id"] == result["document_ids"][0]
    assert record.call_args.kwargs["target_filename"] == "공고문.hwpx"
