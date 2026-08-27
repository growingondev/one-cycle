from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.chunk import Chunk
from backend.app.models.chunk_set import ChunkSet
from backend.app.models.document import Document
from backend.app.models.embedding import Embedding
from backend.app.models.processing_run import ProcessingRun
from backend.app.services.collection_publish_service import (
    publish_collection_run,
)
from backend.app.services.integration_service import (
    process_document_ids,
)
from backend.app.services.evaluation_service import (
    EVALUATION_DB_NAME,
)


def _assert_evaluation_database() -> None:
    if settings.postgres_db != EVALUATION_DB_NAME:
        raise RuntimeError(
            "Evaluation pipeline requires the evaluation database. "
            f"configured={settings.postgres_db}, "
            f"required={EVALUATION_DB_NAME}"
        )

    with SessionLocal() as db:
        current_database = db.execute(
            text("SELECT current_database()")
        ).scalar_one()

    if current_database != EVALUATION_DB_NAME:
        raise RuntimeError(
            "Actual database connection is not the evaluation database. "
            f"actual={current_database}, "
            f"required={EVALUATION_DB_NAME}"
        )


def _get_collection_document_ids(
    collection_run_id: int,
) -> list[int]:
    with SessionLocal() as db:
        document_ids = list(
            db.scalars(
                select(Document.id)
                .join(
                    Announcement,
                    Document.announcement_id
                    == Announcement.id,
                )
                .where(
                    Announcement.collection_run_id
                    == collection_run_id,
                    Document.document_role
                    == "primary",
                    Document.download_status
                    == "completed",
                )
                .order_by(Document.id)
            )
        )

    if not document_ids:
        raise RuntimeError(
            "처리할 평가 Document가 없습니다. "
            f"collection_run_id={collection_run_id}"
        )

    return document_ids


def _get_document_result(
    document_id: int,
) -> dict[str, Any]:
    with SessionLocal() as db:
        document = db.get(
            Document,
            document_id,
        )

        if document is None:
            raise RuntimeError(
                f"Document가 없습니다: {document_id}"
            )

        announcement = db.get(
            Announcement,
            document.announcement_id,
        )

        if announcement is None:
            raise RuntimeError(
                "Document의 Announcement가 없습니다. "
                f"document_id={document_id}"
            )

        processing_run = db.scalar(
            select(ProcessingRun).where(
                ProcessingRun.document_id
                == document.id,
                ProcessingRun.is_active.is_(True),
            )
        )

        if processing_run is None:
            raise RuntimeError(
                "active ProcessingRun이 없습니다. "
                f"document_id={document_id}"
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
                f"processing_run_id="
                f"{processing_run.id}"
            )

        chunk_count = int(
            db.scalar(
                select(
                    func.count(Chunk.id)
                ).where(
                    Chunk.chunk_set_id
                    == chunk_set.id
                )
            )
            or 0
        )

        embedding_count = int(
            db.scalar(
                select(
                    func.count(Embedding.id)
                )
                .join(
                    Chunk,
                    Chunk.id
                    == Embedding.chunk_id,
                )
                .where(
                    Chunk.chunk_set_id
                    == chunk_set.id,
                    Embedding.status
                    == "completed",
                )
            )
            or 0
        )

        model_names = list(
            db.scalars(
                select(
                    Embedding.model_name
                )
                .join(
                    Chunk,
                    Chunk.id
                    == Embedding.chunk_id,
                )
                .where(
                    Chunk.chunk_set_id
                    == chunk_set.id,
                    Embedding.status
                    == "completed",
                )
                .distinct()
                .order_by(
                    Embedding.model_name
                )
            )
        )

    if len(model_names) != 1:
        raise RuntimeError(
            "완료된 Embedding model_name이 "
            "정확히 1개여야 합니다. "
            f"document_id={document_id}, "
            f"models={model_names}"
        )

    return {
        "evaluation_document_id": (
            announcement.source_announcement_id
        ),
        "announcement_id": announcement.id,
        "document_id": document.id,
        "processing_run_id": (
            processing_run.id
        ),
        "chunk_set_id": chunk_set.id,
        "chunk_count": chunk_count,
        "embedding_count": embedding_count,
        "embedding_model_name": (
            model_names[0]
        ),
    }


def process_and_publish_evaluation_collection(
    *,
    collection_run_id: int,
) -> dict[str, Any]:
    """
    등록 완료된 평가 Collection을 기존 문서처리
    Pipeline으로 처리한 뒤 전체 성공 시 Publish한다.
    """

    _assert_evaluation_database()

    if (
        isinstance(collection_run_id, bool)
        or not isinstance(
            collection_run_id,
            int,
        )
        or collection_run_id <= 0
    ):
        raise ValueError(
            "collection_run_id는 "
            "1 이상의 정수여야 합니다."
        )

    document_ids = (
        _get_collection_document_ids(
            collection_run_id
        )
    )

    processing = process_document_ids(
        document_ids
    )

    if processing.get(
        "failed_count",
        0,
    ) > 0:
        raise RuntimeError(
            "평가 문서처리에 실패한 문서가 "
            "있어 Publish하지 않습니다. "
            f"success="
            f"{processing.get('success_count')}, "
            f"failed="
            f"{processing.get('failed_count')}, "
            f"error_ids="
            f"{processing.get('error_ids')}"
        )

    document_results = [
        _get_document_result(
            document_id
        )
        for document_id in document_ids
    ]

    publish_result = (
        publish_collection_run(
            collection_run_id
        )
    )

    return {
        "collection_run_id": (
            collection_run_id
        ),
        "document_count": len(
            document_results
        ),
        "processing": {
            "requested_count": (
                processing[
                    "requested_count"
                ]
            ),
            "success_count": (
                processing[
                    "success_count"
                ]
            ),
            "failed_count": (
                processing[
                    "failed_count"
                ]
            ),
            "error_ids": (
                processing[
                    "error_ids"
                ]
            ),
        },
        "documents": document_results,
        "publish": publish_result,
    }
