"""Migrated PostgreSQL + real publish, listing, vector and keyword retrieval tests.

Only synthetic document processing/query embeddings replace external services.
All synthetic DB changes are rolled back after each test.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import numpy as np
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.models import (
    Chunk,
    ChunkSet,
    Document,
    Embedding,
    ProcessingRun,
    SystemState,
)
from backend.app.services import (
    announcement_service,
    collection_service,
    integration_service,
)
from backend.app.services import collection_publish_service as publisher


@pytest.fixture
def migrated_db(monkeypatch):
    url = os.getenv("ONE_CYCLE_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("Requires isolated migrated PostgreSQL")
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or not (
        parsed.database or ""
    ).startswith("restore_test"):
        pytest.fail("Refusing non-local/non-test database")
    for key, value in {
        "POSTGRES_HOST": parsed.host,
        "POSTGRES_PORT": parsed.port,
        "POSTGRES_USER": parsed.username,
        "POSTGRES_PASSWORD": parsed.password,
        "POSTGRES_DB": parsed.database,
    }.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.setenv("LLAMA_MODEL", "unused-test-model")
    from rag import db_pipeline
    from rag.retrieval import keyword_search

    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "d91f7a63b2c4"
        )
        sessions = sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        for module in (collection_service, publisher, db_pipeline, keyword_search):
            monkeypatch.setattr(module, "SessionLocal", sessions)
        monkeypatch.setattr(
            integration_service, "record_error", Mock(return_value={"error_id": 1})
        )
        try:
            yield sessions, connection, db_pipeline, keyword_search
        finally:
            transaction.rollback()
    engine.dispose()


def response(source_ids):
    return {
        "execution_id": "test_" + uuid.uuid4().hex,
        "execution_status": "success",
        "total_count": len(source_ids),
        "success_count": len(source_ids),
        "failed_count": 0,
        "data": [
            {
                "source_announcement_id": source,
                "title": f"{source} 임대 신청",
                "detail_url": f"https://example.test/{source}",
                "region": "서울",
                "documents": [
                    {
                        "file_name": "공고문.hwpx",
                        "file_format": "hwpx",
                        "download_status": "completed",
                        "storage_path": f"/fixture/{source}.hwpx",
                    }
                ],
            }
            for source in source_ids
        ],
    }


def process(sessions, document_ids, *, embeddings=True):
    with sessions.begin() as db:
        for document_id in document_ids:
            document = db.get(Document, document_id)
            run = ProcessingRun(
                document_id=document_id,
                execution_status="succeeded",
                verification_status="pass",
                is_active=True,
                activated_at=datetime.now(timezone.utc),
            )
            db.add(run)
            db.flush()
            chunk_set = ChunkSet(
                processing_run_id=run.id,
                chunker_version="test",
                strategy="test",
                status="completed",
                is_active=True,
                chunk_count=1,
            )
            db.add(chunk_set)
            db.flush()
            chunk = Chunk(
                chunk_set_id=chunk_set.id,
                announcement_id=document.announcement_id,
                document_id=document_id,
                external_chunk_key=f"chunk_{document_id}",
                chunk_index=0,
                document_format="hwpx",
                content_type="text",
                content="임대 신청 자격 안내",
                search_text="임대 신청 자격 안내",
                embedding_text="임대 신청 자격 안내",
                status="completed",
            )
            db.add(chunk)
            db.flush()
            if embeddings:
                db.add(
                    Embedding(
                        chunk_id=chunk.id,
                        model_name=publisher.RAG_EMBEDDING_MODEL_NAME,
                        embedding=[1.0] + [0.0] * 1023,
                        status="completed",
                    )
                )
    return {"failed_count": 0}


def active_ids(sessions):
    with sessions() as db:
        listing = announcement_service.list_active_announcements(
            db, 1, 100, None, None, None
        )
        return {item.id for item in listing.items}


def test_full_publish_switches_listing_and_both_rag_searches(migrated_db, monkeypatch):
    sessions, connection, db_pipeline, keyword_search = migrated_db
    old = collection_service.persist_collection_result(response(["A", "B"]))
    process(sessions, old["analysis_document_ids"])
    publisher.publish_collection_run(old["collection_run_id"])
    # Legacy columns remain physically present but are not application selection criteria.
    connection.execute(
        text("UPDATE announcements SET is_visible=false WHERE id=:id"),
        {"id": old["announcement_ids"][0]},
    )
    assert active_ids(sessions) == set(old["announcement_ids"])
    monkeypatch.setattr(
        collection_service.crawler_client,
        "crawl_announcements",
        lambda: response(["A", "C"]),
    )

    def process_new(ids):
        assert active_ids(sessions) == set(old["announcement_ids"])
        return process(sessions, ids)

    monkeypatch.setattr(integration_service, "process_document_ids", process_new)
    new = integration_service.collect_persist_and_process()
    assert new["status"] == "success"
    assert active_ids(sessions) == set(new["announcement_ids"])
    from rag.generation.config import DEFAULT_GENERATION_CONFIG
    from rag.retrieval.config import RetrievalConfig

    embedding_client = Mock()
    embedding_client.embed_query.return_value = np.array([1.0] + [0.0] * 1023)
    pipeline = db_pipeline.DBRAGPipeline(
        embedding_client,
        RetrievalConfig(embedding_model_name=publisher.RAG_EMBEDDING_MODEL_NAME),
        DEFAULT_GENERATION_CONFIG,
    )

    def assert_search_scope(active, inactive):
        for announcement_id in active:
            assert pipeline.retrieve(announcement_id=announcement_id, query="임대 신청")
            assert keyword_search.search_bm25(
                announcement_id=announcement_id, query="임대 신청"
            )
        for announcement_id in inactive:
            assert (
                pipeline.retrieve(announcement_id=announcement_id, query="임대 신청")
                == []
            )
            assert (
                keyword_search.search_bm25(
                    announcement_id=announcement_id, query="임대 신청"
                )
                == []
            )

    assert_search_scope(new["announcement_ids"], old["announcement_ids"])
    # Exercise existing publish pointer semantics, not a new rollback feature.
    publisher.publish_collection_run(old["collection_run_id"])
    assert_search_scope(old["announcement_ids"], new["announcement_ids"])


def test_missing_embedding_blocks_real_publish_and_keeps_previous_run(
    migrated_db, monkeypatch
):
    sessions, _, _, _ = migrated_db
    old = collection_service.persist_collection_result(response(["A"]))
    process(sessions, old["analysis_document_ids"])
    publisher.publish_collection_run(old["collection_run_id"])
    monkeypatch.setattr(
        collection_service.crawler_client,
        "crawl_announcements",
        lambda: response(["C"]),
    )
    monkeypatch.setattr(
        integration_service,
        "process_document_ids",
        lambda ids: process(sessions, ids, embeddings=False),
    )
    new = integration_service.collect_persist_and_process()
    assert new["status"] == "failed"
    assert new["publish"]["status"] == "failed"
    assert active_ids(sessions) == set(old["announcement_ids"])
    with sessions() as db:
        assert (
            db.scalar(select(SystemState.active_collection_run_id))
            == old["collection_run_id"]
        )
