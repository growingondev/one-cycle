from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.error_log import ErrorLog
from backend.app.models.processing_run import ProcessingRun


VALID_ERROR_TYPES = {
    "collection",
    "download",
    "parsing",
    "normalizing",
    "structuring",
    "verification",
    "chunking",
    "embedding",
    "database",
    "rag",
    "llm",
}


def _validate_error_input(
    *,
    error_type: str,
    stage: str,
    message: str,
) -> None:
    if error_type not in VALID_ERROR_TYPES:
        raise ValueError(
            f"지원하지 않는 error_type입니다: {error_type}"
        )

    if not stage.strip():
        raise ValueError("error stage가 비어 있습니다.")

    if not message.strip():
        raise ValueError("error message가 비어 있습니다.")


def _resolve_error_links(
    db: Session,
    *,
    collection_run_id: int | None,
    announcement_id: int | None,
    document_id: int | None,
    processing_run_id: int | None,
) -> dict[str, int | None]:
    if processing_run_id is not None:
        processing_run = db.get(
            ProcessingRun,
            processing_run_id,
        )

        if processing_run is None:
            raise ValueError(
                "ProcessingRun을 찾을 수 없습니다: "
                f"{processing_run_id}"
            )

        if (
            document_id is not None
            and processing_run.document_id != document_id
        ):
            raise ValueError(
                "ProcessingRun과 Document가 일치하지 않습니다."
            )

        document_id = processing_run.document_id

    if document_id is not None:
        document = db.get(
            Document,
            document_id,
        )

        if document is None:
            raise ValueError(
                f"Document를 찾을 수 없습니다: {document_id}"
            )

        if (
            announcement_id is not None
            and document.announcement_id != announcement_id
        ):
            raise ValueError(
                "Document와 Announcement가 일치하지 않습니다."
            )

        announcement_id = document.announcement_id

    if announcement_id is not None:
        announcement = db.get(
            Announcement,
            announcement_id,
        )

        if announcement is None:
            raise ValueError(
                "Announcement를 찾을 수 없습니다: "
                f"{announcement_id}"
            )

        if (
            collection_run_id is not None
            and announcement.collection_run_id
            != collection_run_id
        ):
            raise ValueError(
                "Announcement와 CollectionRun이 "
                "일치하지 않습니다."
            )

        collection_run_id = announcement.collection_run_id

    if collection_run_id is not None:
        collection_run = db.get(
            CollectionRun,
            collection_run_id,
        )

        if collection_run is None:
            raise ValueError(
                "CollectionRun을 찾을 수 없습니다: "
                f"{collection_run_id}"
            )

    return {
        "collection_run_id": collection_run_id,
        "announcement_id": announcement_id,
        "document_id": document_id,
        "processing_run_id": processing_run_id,
    }


def record_error(
    *,
    error_type: str,
    stage: str,
    message: str,
    collection_run_id: int | None = None,
    announcement_id: int | None = None,
    document_id: int | None = None,
    processing_run_id: int | None = None,
    error_code: str | None = None,
    stack_trace: str | None = None,
) -> dict[str, Any]:
    """
    Crawler / 문서 처리 / AI 기능에서 발생한 오류를
    공통 ErrorLog 형식으로 저장한다.

    관련 ID가 일부만 전달되면 DB 관계를 따라 상위 ID를 보완한다.

    예:
        processing_run_id
        → document_id
        → announcement_id
        → collection_run_id
    """

    error_type = error_type.strip().lower()
    stage = stage.strip()
    message = message.strip()

    _validate_error_input(
        error_type=error_type,
        stage=stage,
        message=message,
    )

    with SessionLocal.begin() as db:
        links = _resolve_error_links(
            db,
            collection_run_id=collection_run_id,
            announcement_id=announcement_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
        )

        error_log = ErrorLog(
            **links,
            error_type=error_type,
            error_code=(
                error_code.strip()
                if isinstance(error_code, str)
                and error_code.strip()
                else None
            ),
            stage=stage,
            message=message,
            stack_trace=stack_trace,
            status="unresolved",
        )

        db.add(error_log)
        db.flush()

        return {
            "error_id": error_log.id,
            "error_type": error_log.error_type,
            "stage": error_log.stage,
            "status": error_log.status,
            **links,
        }