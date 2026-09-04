"""Full-collection orchestration, retirement and dataset-switch regression tests.

PostgreSQL session locks and external workers are mocked. Dataset persistence and
publication transactions run against isolated SQLite (no production connections).
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.dependencies import get_current_admin
from backend.app.api.routes import admin
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.system_state import SystemState
from backend.app.services import collection_publish_service as publisher
from backend.app.services import (
    collection_retention_service,
    collection_service,
    integration_service,
    pipeline_gateway,
)


@pytest.fixture
def locked_runner():
    with (
        patch.object(pipeline_gateway, "engine") as engine,
        patch.object(pipeline_gateway, "_load_callable") as loader,
    ):
        connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
        connection.scalar.side_effect = [True, True]
        runner = loader.return_value
        runner.return_value = {"status": "success"}
        yield engine, connection, runner


def test_full_runner_holds_shared_lock_through_completion(locked_runner):
    engine, connection, runner = locked_runner

    def complete():
        assert connection.scalar.call_count == 1  # not released during processing
        return {"status": "success"}

    runner.side_effect = complete
    assert pipeline_gateway.collect_announcements() == {"status": "success"}
    engine.connect.return_value.execution_options.assert_called_once_with(
        isolation_level="AUTOCOMMIT"
    )
    assert [str(call.args[0]) for call in connection.scalar.call_args_list] == [
        "SELECT pg_try_advisory_lock(:lock_id)",
        "SELECT pg_advisory_unlock(:lock_id)",
    ]
    for call in connection.scalar.call_args_list:
        assert call.args[1] == {"lock_id": 615_120_315}


def test_busy_lock_never_starts_or_unlocks_other_collection(locked_runner):
    _, connection, runner = locked_runner
    connection.scalar.side_effect = [False]
    with pytest.raises(pipeline_gateway.CollectionAlreadyRunningError):
        pipeline_gateway.collect_announcements()
    runner.assert_not_called()
    assert connection.scalar.call_count == 1


def test_runner_failure_releases_lock_and_preserves_exception(locked_runner):
    _, connection, runner = locked_runner
    runner.side_effect = RuntimeError("processing failed")
    with pytest.raises(RuntimeError, match="processing failed"):
        pipeline_gateway.collect_announcements()
    assert connection.scalar.call_count == 2


def test_uncertain_lock_acquisition_discards_connection(locked_runner):
    _, connection, runner = locked_runner
    connection.scalar.side_effect = RuntimeError("connection lost")
    with pytest.raises(RuntimeError, match="connection lost"):
        pipeline_gateway.collect_announcements()
    runner.assert_not_called()
    connection.invalidate.assert_called_once_with()


@pytest.mark.parametrize("release_result", [RuntimeError("connection lost"), False])
def test_unlock_failure_discards_connection_without_losing_result(
    locked_runner, release_result
):
    _, connection, _ = locked_runner
    connection.scalar.side_effect = [True, release_result]
    assert pipeline_gateway.collect_announcements() == {"status": "success"}
    connection.invalidate.assert_called_once_with()


def test_runner_and_unlock_failures_preserve_original_error(locked_runner):
    _, connection, runner = locked_runner
    runner.side_effect = ValueError("original failure")
    connection.scalar.side_effect = [True, RuntimeError("unlock failed")]
    with pytest.raises(ValueError, match="original failure"):
        pipeline_gateway.collect_announcements()
    connection.invalidate.assert_called_once_with()


@pytest.fixture
def admin_client():
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_current_admin] = lambda: object()
    with TestClient(app) as client:
        yield client


def test_sync_route_is_absent_without_collecting(admin_client):
    with patch.object(admin, "collect_announcements") as collect:
        response = admin_client.post("/api/admin/announcements/sync")
    assert response.status_code in {404, 405}
    # GET /announcements/{announcement_id} can make this POST return 405, not 404.
    assert "/api/admin/announcements/sync" not in admin_client.app.openapi()["paths"]
    collect.assert_not_called()


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [({"status": "success"}, 201), ({"status": "failed"}, 500)],
)
def test_manual_full_collection_response(admin_client, result, expected_status):
    with patch.object(admin, "collect_announcements", return_value=result) as collect:
        response = admin_client.post("/api/admin/announcements/collect")
    assert response.status_code == expected_status
    collect.assert_called_once_with()


def test_manual_full_collection_conflict_returns_409(admin_client):
    with patch.object(
        admin,
        "collect_announcements",
        side_effect=pipeline_gateway.CollectionAlreadyRunningError("busy"),
    ):
        response = admin_client.post("/api/admin/announcements/collect")
    assert response.status_code == 409


def crawl_result(execution_id, source_ids, *, status="success"):
    return {
        "execution_id": execution_id,
        "execution_status": status,
        "total_count": len(source_ids),
        "success_count": len(source_ids),
        "failed_count": 0,
        "data": [
            {
                "source_announcement_id": source_id,
                "title": f"{source_id} 공고",
                "detail_url": f"https://example.test/{source_id}",
                "region": "서울",
                "documents": [
                    {
                        "file_name": "공고문.hwpx",
                        "file_format": "hwpx",
                        "download_status": "completed",
                        "checksum_sha256": "a" * 64,
                        "storage_path": f"/data/documents/{source_id}/공고문.hwpx",
                    }
                ],
            }
            for source_id in source_ids
        ],
    }


@pytest.fixture
def dataset(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (CollectionRun, Announcement, Document, SystemState):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(collection_service, "SessionLocal", sessions)
    monkeypatch.setattr(publisher, "SessionLocal", sessions)
    monkeypatch.setattr(collection_retention_service, "SessionLocal", sessions)
    monkeypatch.setattr(
        integration_service, "record_error", Mock(return_value={"error_id": 1})
    )
    # Seed a currently served dataset, including a notice absent from the next page.
    old = collection_service.persist_collection_result(crawl_result("old", ["A", "B"]))
    with sessions.begin() as db:
        db.add(SystemState(id=1, active_collection_run_id=old["collection_run_id"]))
    yield sessions, old
    engine.dispose()


def active_sources(sessions):
    with sessions() as db:
        return list(
            db.scalars(
                select(Announcement.source_announcement_id)
                .join(
                    SystemState,
                    SystemState.active_collection_run_id
                    == Announcement.collection_run_id,
                )
                .where(SystemState.id == 1)
                .order_by(Announcement.source_announcement_id)
            )
        )


def test_full_collection_reprocesses_unchanged_documents_then_replaces_dataset(
    dataset, locked_runner
):
    sessions, old = dataset
    _, connection, runner = locked_runner
    runner.side_effect = integration_service.collect_persist_and_process
    processed = []

    def process(document_ids):
        assert active_sources(sessions) == ["A", "B"]
        assert len(document_ids) == 2
        assert set(document_ids).isdisjoint(old["document_ids"])
        processed.extend(document_ids)
        return {"failed_count": 0}

    def validate_document(db, document):
        assert document.id in processed  # publish must be AFTER document processing
        assert active_sources(sessions) == ["A", "B"]
        return 1, 1

    with (
        patch.object(
            collection_service.crawler_client,
            "crawl_announcements",
            return_value=crawl_result("new", ["A", "C"]),
        ) as crawl,
        patch.object(integration_service, "process_document_ids", side_effect=process),
        patch.object(
            publisher,
            "_validate_primary_document_for_publish",
            side_effect=validate_document,
        ),
    ):
        result = pipeline_gateway.collect_announcements()
    crawl.assert_called_once_with()
    assert result["status"] == "success"
    assert result["publish"]["previous_collection_run_id"] == old["collection_run_id"]
    assert active_sources(sessions) == [
        "A",
        "C",
    ]  # B is no longer served, no accumulation
    assert connection.scalar.call_count == 2
    with sessions() as db:
        assert db.scalar(select(func.count(CollectionRun.id))) == 2
        assert db.scalar(select(func.count(Announcement.id))) == 4
        assert (
            db.scalar(select(func.count(Document.id))) == 4
        )  # physical cleanup deferred
        state = db.get(SystemState, 1)
        assert state.previous_collection_run_id == old["collection_run_id"]


@pytest.mark.parametrize(
    "failure", ["partial_crawl", "processing", "embedding", "empty_page"]
)
def test_failed_new_dataset_never_replaces_existing_dataset(dataset, failure):
    sessions, old = dataset
    new = crawl_result(
        "failed-new",
        [] if failure == "empty_page" else ["A", "C"],
        status="partial" if failure == "partial_crawl" else "success",
    )
    with (
        patch.object(
            collection_service.crawler_client, "crawl_announcements", return_value=new
        ),
        patch.object(
            integration_service,
            "process_document_ids",
            return_value={"failed_count": 1 if failure == "processing" else 0},
        ),
        patch.object(
            publisher,
            "_validate_primary_document_for_publish",
            side_effect=RuntimeError("embedding incomplete"),
        ) as validate,
    ):
        result = integration_service.collect_persist_and_process()
    assert result["status"] == "failed"
    assert active_sources(sessions) == ["A", "B"]
    with sessions() as db:
        assert (
            db.get(SystemState, 1).active_collection_run_id == old["collection_run_id"]
        )
    assert validate.call_count == (1 if failure == "embedding" else 0)


def test_full_collection_keeps_automatic_failed_stage_retry(dataset, monkeypatch):
    sessions, _ = dataset
    monkeypatch.setattr(
        integration_service.settings, "document_processing_max_attempts", 3
    )
    monkeypatch.setattr(
        integration_service.settings, "document_processing_retry_delay_seconds", 0
    )
    with (
        patch.object(
            collection_service.crawler_client,
            "crawl_announcements",
            return_value=crawl_result("retry-new", ["A"]),
        ),
        patch.object(
            integration_service,
            "reprocess_document",
            side_effect=[
                {
                    "success": False,
                    "stage": "embedding",
                    "message": "temporary failure",
                },
                {"success": True},
            ],
        ) as process,
        patch.object(
            publisher, "_validate_primary_document_for_publish", return_value=(1, 1)
        ),
    ):
        result = integration_service.collect_persist_and_process()
    assert result["status"] == "success"
    assert process.call_count == 2
    assert process.call_args_list[0].kwargs == {}
    assert process.call_args_list[1].kwargs == {"start_stage": "embedding"}
    assert active_sources(sessions) == ["A"]
    integration_service.record_error.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "execution",
        "verification",
        "missing_chunk_set",
        "chunk_status",
        "empty_chunks",
        "chunk_count",
        "incomplete_chunks",
        "incomplete_embeddings",
    ],
)
def test_real_publish_validator_rejects_incomplete_processing(failure):
    document = SimpleNamespace(id=1, download_status="completed")
    processing = SimpleNamespace(
        id=2, execution_status="succeeded", verification_status="pass"
    )
    chunk_set = SimpleNamespace(id=3, status="completed", chunk_count=2)
    actual, completed, embeddings = 2, 2, 2
    if failure == "execution":
        processing.execution_status = "failed"
    elif failure == "verification":
        processing.verification_status = "fail"
    elif failure == "missing_chunk_set":
        chunk_set = None
    elif failure == "chunk_status":
        chunk_set.status = "running"
    elif failure == "empty_chunks":
        actual = 0
    elif failure == "chunk_count":
        chunk_set.chunk_count = 3
    elif failure == "incomplete_chunks":
        completed = 1
    elif failure == "incomplete_embeddings":
        embeddings = 1
    db = Mock()
    db.scalar.side_effect = [processing, chunk_set, actual, completed, embeddings]
    with pytest.raises(RuntimeError):
        publisher._validate_primary_document_for_publish(db, document)


def test_real_publish_validator_accepts_complete_embeddings():
    db = Mock()
    db.scalar.side_effect = [
        SimpleNamespace(id=2, execution_status="succeeded", verification_status="pass"),
        SimpleNamespace(id=3, status="completed", chunk_count=2),
        2,
        2,
        2,
    ]
    document = SimpleNamespace(id=1, download_status="completed")
    assert publisher._validate_primary_document_for_publish(db, document) == (2, 2)
    embedding_query = db.scalar.call_args.args[0]
    query_text = str(embedding_query)
    assert "embeddings.embedding IS NOT NULL" in query_text
    assert "embeddings.normalized IS true" in query_text
    assert 1024 in embedding_query.compile().params.values()
    assert (
        publisher.RAG_EMBEDDING_MODEL_NAME in embedding_query.compile().params.values()
    )
