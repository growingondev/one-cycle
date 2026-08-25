from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.chunk import Chunk
from backend.app.models.chunk_set import ChunkSet
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.embedding import Embedding
from backend.app.models.processing_run import ProcessingRun
from backend.app.models.system_state import SystemState
from backend.app.services.document_role_service import (
    DOCUMENT_ROLE_PRIMARY,
    DOCUMENT_ROLE_SUPPORTING,
    DOCUMENT_ROLE_UNKNOWN,
)
from rag.retrieval.config import DEFAULT_RETRIEVAL_CONFIG


RAG_EMBEDDING_MODEL_NAME = (
    DEFAULT_RETRIEVAL_CONFIG.embedding_model_name
)


def _validate_primary_document_for_publish(
    db: Session,
    document: Document,
) -> tuple[int, int]:
    """
    실제 AI 분석 대상인 primary Document가
    사용자 서비스에 publish 가능한 상태인지 검증한다.

    반환값:
        (
            chunk_count,
            embedding_chunk_count,
        )
    """

    if document.download_status != "completed":
        raise RuntimeError(
            "다운로드가 완료되지 않은 primary Document가 있습니다. "
            f"document_id={document.id}, "
            f"status={document.download_status}"
        )

    processing_run = db.scalar(
        select(ProcessingRun).where(
            ProcessingRun.document_id == document.id,
            ProcessingRun.is_active.is_(True),
        )
    )

    if processing_run is None:
        raise RuntimeError(
            "active ProcessingRun이 없는 primary Document가 있습니다. "
            f"document_id={document.id}"
        )

    if processing_run.execution_status != "succeeded":
        raise RuntimeError(
            "active ProcessingRun이 succeeded가 아닙니다. "
            f"processing_run_id={processing_run.id}"
        )

    if processing_run.verification_status != "pass":
        raise RuntimeError(
            "active ProcessingRun verification이 pass가 아닙니다. "
            f"processing_run_id={processing_run.id}"
        )

    chunk_set = db.scalar(
        select(ChunkSet).where(
            ChunkSet.processing_run_id
            == processing_run.id,
            ChunkSet.is_active.is_(True),
        )
    )

    if chunk_set is None:
        raise RuntimeError(
            "active ChunkSet이 없습니다. "
            f"processing_run_id={processing_run.id}"
        )

    if chunk_set.status != "completed":
        raise RuntimeError(
            "active ChunkSet이 completed가 아닙니다. "
            f"chunk_set_id={chunk_set.id}"
        )

    actual_chunks = int(
        db.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.chunk_set_id == chunk_set.id
            )
        )
        or 0
    )

    completed_chunks = int(
        db.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.chunk_set_id == chunk_set.id,
                Chunk.status == "completed",
            )
        )
        or 0
    )

    if actual_chunks <= 0:
        raise RuntimeError(
            "Chunk가 없는 active ChunkSet입니다. "
            f"chunk_set_id={chunk_set.id}"
        )

    if actual_chunks != chunk_set.chunk_count:
        raise RuntimeError(
            "ChunkSet chunk_count와 실제 Chunk 수가 다릅니다. "
            f"chunk_set_id={chunk_set.id}, "
            f"declared={chunk_set.chunk_count}, "
            f"actual={actual_chunks}"
        )

    if completed_chunks != actual_chunks:
        raise RuntimeError(
            "completed 상태가 아닌 Chunk가 있습니다. "
            f"chunk_set_id={chunk_set.id}, "
            f"completed={completed_chunks}, "
            f"actual={actual_chunks}"
        )

    completed_embedding_chunks = int(
        db.scalar(
            select(
                func.count(
                    func.distinct(Embedding.chunk_id)
                )
            )
            .join(
                Chunk,
                Chunk.id == Embedding.chunk_id,
            )
            .where(
                Chunk.chunk_set_id == chunk_set.id,
                Embedding.status == "completed",
                Embedding.model_name
                == RAG_EMBEDDING_MODEL_NAME,
                Embedding.embedding.is_not(None),
                Embedding.dimension == 1024,
                Embedding.normalized.is_(True),
            )
        )
        or 0
    )

    if completed_embedding_chunks != actual_chunks:
        raise RuntimeError(
            "RAG 검색 가능한 completed Embedding이 "
            "모든 Chunk에 존재하지 않습니다. "
            f"chunk_set_id={chunk_set.id}, "
            f"model={RAG_EMBEDDING_MODEL_NAME}, "
            f"embedding_chunks={completed_embedding_chunks}, "
            f"chunks={actual_chunks}"
        )

    return (
        actual_chunks,
        completed_embedding_chunks,
    )


def _validate_collection_run_for_publish(
    db: Session,
    collection_run_id: int,
) -> dict[str, Any]:
    collection_run = db.get(
        CollectionRun,
        collection_run_id,
    )

    if collection_run is None:
        raise RuntimeError(
            f"CollectionRun이 없습니다: {collection_run_id}"
        )

    if collection_run.status != "success":
        raise RuntimeError(
            "success 상태의 CollectionRun만 publish할 수 있습니다. "
            f"현재 상태={collection_run.status}"
        )

    announcements = list(
        db.scalars(
            select(Announcement)
            .where(
                Announcement.collection_run_id
                == collection_run.id
            )
            .order_by(Announcement.id)
        )
    )

    if not announcements:
        raise RuntimeError(
            "CollectionRun에 Announcement가 없습니다."
        )

    if collection_run.failed_announcement_count != 0:
        raise RuntimeError(
            "실패한 Announcement가 있는 CollectionRun은 "
            "publish할 수 없습니다."
        )

    if (
        collection_run.successful_announcement_count
        != len(announcements)
    ):
        raise RuntimeError(
            "CollectionRun 성공 건수와 실제 Announcement 수가 "
            "다릅니다. "
            f"declared="
            f"{collection_run.successful_announcement_count}, "
            f"actual={len(announcements)}"
        )

    if (
        collection_run.total_announcement_count
        != len(announcements)
    ):
        raise RuntimeError(
            "CollectionRun 전체 건수와 실제 Announcement 수가 "
            "다릅니다. "
            f"declared={collection_run.total_announcement_count}, "
            f"actual={len(announcements)}"
        )

    document_count = 0
    analysis_document_count = 0
    supporting_document_count = 0
    metadata_only_announcement_count = 0
    chunk_count = 0
    embedding_chunk_count = 0

    for announcement in announcements:
        documents = list(
            db.scalars(
                select(Document)
                .where(
                    Document.announcement_id
                    == announcement.id
                )
                .order_by(Document.id)
            )
        )

        document_count += len(documents)

        primary_documents: list[Document] = []

        for document in documents:
            document_role = str(
                document.document_role
                or ""
            ).strip()

            if document_role == DOCUMENT_ROLE_UNKNOWN:
                raise RuntimeError(
                    "역할을 판별하지 못한 Document가 있습니다. "
                    f"document_id={document.id}, "
                    f"filename={document.original_filename}"
                )

            if (
                document_role
                == DOCUMENT_ROLE_SUPPORTING
            ):
                supporting_document_count += 1
                continue

            if document_role != DOCUMENT_ROLE_PRIMARY:
                raise RuntimeError(
                    "지원하지 않는 document_role입니다. "
                    f"document_id={document.id}, "
                    f"role={document_role}"
                )

            primary_documents.append(
                document
            )

        # HWP/HWPX 분석 대상이 없는 공고는
        # 기본 메타데이터만 제공하는 공고로 publish를 허용한다.
        if not primary_documents:
            metadata_only_announcement_count += 1
            continue

        for document in primary_documents:
            analysis_document_count += 1

            (
                document_chunk_count,
                document_embedding_chunk_count,
            ) = _validate_primary_document_for_publish(
                db,
                document,
            )

            chunk_count += document_chunk_count
            embedding_chunk_count += (
                document_embedding_chunk_count
            )

    return {
        "collection_run_id": collection_run.id,
        "announcement_count": len(
            announcements
        ),
        "document_count": document_count,
        "analysis_document_count": (
            analysis_document_count
        ),
        "supporting_document_count": (
            supporting_document_count
        ),
        "metadata_only_announcement_count": (
            metadata_only_announcement_count
        ),
        "chunk_count": chunk_count,
        "embedding_chunk_count": (
            embedding_chunk_count
        ),
    }


def validate_collection_run_for_publish(
    collection_run_id: int,
) -> dict[str, Any]:
    """
    DB를 변경하지 않고 CollectionRun이
    active dataset으로 전환 가능한지 검증한다.
    """

    with SessionLocal() as db:
        return _validate_collection_run_for_publish(
            db,
            collection_run_id,
        )


def publish_collection_run(
    collection_run_id: int,
) -> dict[str, Any]:
    """
    모든 검증을 통과한 CollectionRun만
    system_state.active_collection_run_id로 전환한다.
    """

    now = datetime.now(timezone.utc)

    with SessionLocal.begin() as db:
        summary = _validate_collection_run_for_publish(
            db,
            collection_run_id,
        )

        system_state = db.scalar(
            select(SystemState)
            .where(SystemState.id == 1)
            .with_for_update()
        )

        if system_state is None:
            raise RuntimeError(
                "system_state singleton 행이 없습니다."
            )

        previous_collection_run_id = (
            system_state.active_collection_run_id
        )

        if (
            previous_collection_run_id
            == collection_run_id
        ):
            return {
                **summary,
                "status": "already_active",
                "previous_collection_run_id": (
                    previous_collection_run_id
                ),
                "active_collection_run_id": (
                    collection_run_id
                ),
            }

        system_state.active_collection_run_id = (
            collection_run_id
        )
        system_state.updated_at = now

        db.flush()

        return {
            **summary,
            "status": "published",
            "previous_collection_run_id": (
                previous_collection_run_id
            ),
            "active_collection_run_id": (
                collection_run_id
            ),
        }