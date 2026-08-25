from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.error_log import ErrorLog

from backend.app.schemas.admin import (
    AdminAnnouncementDetail,
    AdminAnnouncementItem,
    AdminAnnouncementListResponse,
    AdminDocumentDetail,
    AdminDocumentItem,
    AdminDocumentListResponse,
    AdminErrorDetail,
    AdminErrorListResponse,
    AdminProcessingRunItem,
    AdminProcessingRunListResponse,
    ChunkingSummary,
    EmbeddingSummary,
    ProcessingSummary,
    StructureSummary,
)


def _total_pages(total: int, size: int) -> int:
    return math.ceil(total / size) if total else 0


def _extract_period_value(
    value: dict[str, Any] | None,
    keys: tuple[str, ...],
):
    if not isinstance(value, dict):
        return None

    for key in keys:
        candidate = value.get(key)
        if candidate not in (None, ""):
            return candidate

    # 중첩 JSON도 한 단계까지 탐색
    for nested in value.values():
        if isinstance(nested, dict):
            for key in keys:
                candidate = nested.get(key)
                if candidate not in (None, ""):
                    return candidate
    return None


def _announcement_item(row) -> AdminAnnouncementItem:
    period = row["application_period"] or {}
    return AdminAnnouncementItem(
        id=row["id"],
        title=row["title"],
        region=row["region"],
        notice_type=row["notice_type"],
        announcement_date=row["announcement_date"],
        application_start=_extract_period_value(
            period,
            (
                "application_start",
                "start",
                "start_date",
                "startDate",
                "from",
            ),
        ),
        application_end=_extract_period_value(
            period,
            (
                "application_end",
                "end",
                "end_date",
                "endDate",
                "to",
            ),
        ),
        announcement_status=row["publication_status"],
        collection_status=row["collection_status"],
        created_at=row["created_at"],
    )


def list_admin_announcements(
    db: Session,
    page: int,
    size: int,
    search: str | None,
    region: str | None,
    announcement_status: str | None,
    collection_status: str | None,
    created_from: date | None,
    created_to: date | None,
) -> AdminAnnouncementListResponse:
    conditions = ["1=1"]
    params: dict[str, Any] = {
        "offset": (page - 1) * size,
        "limit": size,
    }

    if search:
        conditions.append("a.title ILIKE :search")
        params["search"] = f"%{search}%"
    if region:
        conditions.append("a.region = :region")
        params["region"] = region
    if announcement_status:
        conditions.append("a.publication_status = :announcement_status")
        params["announcement_status"] = announcement_status
    if collection_status:
        conditions.append("cr.status = :collection_status")
        params["collection_status"] = collection_status
    if created_from:
        conditions.append("a.created_at::date >= :created_from")
        params["created_from"] = created_from
    if created_to:
        conditions.append("a.created_at::date <= :created_to")
        params["created_to"] = created_to

    where = " AND ".join(conditions)

    total = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM announcements a
            JOIN collection_runs cr ON cr.id = a.collection_run_id
            LEFT JOIN key_information ki ON ki.announcement_id = a.id
            WHERE {where}
            """
        ),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                a.id,
                a.title,
                a.region,
                a.notice_type,
                a.announcement_date,
                a.publication_status,
                a.created_at,
                cr.status AS collection_status,
                ki.application_period
            FROM announcements a
            JOIN collection_runs cr ON cr.id = a.collection_run_id
            LEFT JOIN key_information ki ON ki.announcement_id = a.id
            WHERE {where}
            ORDER BY a.created_at DESC, a.id DESC
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return AdminAnnouncementListResponse(
        items=[_announcement_item(row) for row in rows],
        page=page,
        size=size,
        total=total,
        total_pages=_total_pages(total, size),
    )


def get_admin_announcement(
    db: Session,
    announcement_id: int,
) -> AdminAnnouncementDetail | None:
    row = db.execute(
        text(
            """
            SELECT
                a.id,
                a.collection_run_id,
                a.source_announcement_id,
                a.title,
                a.detail_url,
                a.region,
                a.notice_type,
                a.announcement_date,
                a.publication_status,
                a.created_at,
                cr.status AS collection_status,
                ki.application_period,
                ki.eligibility,
                ki.supply_information,
                ki.income_asset_criteria,
                ki.required_documents,
                ki.winner_announcement,
                ki.contact_information,
                ki.extraction_status,
                ki.is_verified,
                (
                    SELECT COUNT(*)
                    FROM documents d
                    WHERE d.announcement_id = a.id
                ) AS document_count
            FROM announcements a
            JOIN collection_runs cr ON cr.id = a.collection_run_id
            LEFT JOIN key_information ki ON ki.announcement_id = a.id
            WHERE a.id = :announcement_id
            """
        ),
        {"announcement_id": announcement_id},
    ).mappings().first()

    if row is None:
        return None

    base = _announcement_item(row)

    key_information = {
        "application_period": row["application_period"] or {},
        "eligibility": row["eligibility"] or {},
        "supply_information": row["supply_information"] or {},
        "income_asset_criteria": row["income_asset_criteria"] or {},
        "required_documents": row["required_documents"] or {},
        "winner_announcement": row["winner_announcement"] or {},
        "contact_information": row["contact_information"] or {},
        "extraction_status": row["extraction_status"],
        "is_verified": row["is_verified"],
    }

    return AdminAnnouncementDetail(
        **base.model_dump(),
        source_announcement_id=row["source_announcement_id"],
        detail_url=row["detail_url"],
        collection_run_id=row["collection_run_id"],
        key_information=key_information,
        document_count=row["document_count"],
    )


LATEST_PROCESSING_JOIN = """
LEFT JOIN LATERAL (
    SELECT pr.*
    FROM processing_runs pr
    WHERE pr.document_id = d.id
    ORDER BY pr.created_at DESC, pr.id DESC
    LIMIT 1
) pr ON TRUE
"""


def list_admin_documents(
    db: Session,
    page: int,
    size: int,
    search: str | None,
    document_type: str | None,
    processing_status: str | None,
    analysis_status: str | None,
) -> AdminDocumentListResponse:
    conditions = ["1=1"]
    params: dict[str, Any] = {
        "offset": (page - 1) * size,
        "limit": size,
    }

    if search:
        conditions.append(
            "(a.title ILIKE :search OR d.original_filename ILIKE :search)"
        )
        params["search"] = f"%{search}%"
    if document_type:
        conditions.append("d.document_format = :document_type")
        params["document_type"] = document_type
    if processing_status:
        conditions.append("pr.execution_status = :processing_status")
        params["processing_status"] = processing_status
    if analysis_status:
        conditions.append("pr.verification_status = :analysis_status")
        params["analysis_status"] = analysis_status

    where = " AND ".join(conditions)

    total = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM documents d
            JOIN announcements a ON a.id = d.announcement_id
            {LATEST_PROCESSING_JOIN}
            WHERE {where}
            """
        ),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                d.id,
                d.announcement_id,
                a.title AS announcement_title,
                d.original_filename,
                d.document_format,
                d.file_size_bytes,
                d.download_status,
                d.created_at,
                pr.execution_status,
                pr.verification_status
            FROM documents d
            JOIN announcements a ON a.id = d.announcement_id
            {LATEST_PROCESSING_JOIN}
            WHERE {where}
            ORDER BY d.created_at DESC, d.id DESC
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return AdminDocumentListResponse(
        items=[
            AdminDocumentItem(
                id=row["id"],
                announcement_id=row["announcement_id"],
                announcement_title=row["announcement_title"],
                file_name=row["original_filename"],
                document_type=row["document_format"],
                file_size=row["file_size_bytes"],
                download_status=row["download_status"],
                processing_status=row["execution_status"],
                analysis_status=row["verification_status"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        page=page,
        size=size,
        total=total,
        total_pages=_total_pages(total, size),
    )


def get_admin_document(
    db: Session,
    document_id: int,
) -> AdminDocumentDetail | None:
    row = db.execute(
        text(
            f"""
            SELECT
                d.id,
                d.announcement_id,
                a.title AS announcement_title,
                d.original_filename,
                d.document_format,
                d.file_size_bytes,
                d.download_status,
                d.storage_path,
                d.checksum_sha256,
                d.created_at,
                pr.id AS processing_run_id,
                pr.execution_status,
                pr.verification_status,
                pr.current_stage,
                pr.error_stage,
                pr.error_code,
                pr.error_message
            FROM documents d
            JOIN announcements a ON a.id = d.announcement_id
            {LATEST_PROCESSING_JOIN}
            WHERE d.id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()

    if row is None:
        return None

    processing_run_id = row["processing_run_id"]

    structure = None
    chunking = None
    embedding = {
        "completed_count": 0,
        "total_count": 0,
        "failed_count": 0,
    }

    if processing_run_id is not None:
        structure = db.execute(
            text(
                """
                SELECT schema_version, element_count
                FROM document_structures
                WHERE processing_run_id = :processing_run_id
                """
            ),
            {"processing_run_id": processing_run_id},
        ).mappings().first()

        chunking = db.execute(
            text(
                """
                SELECT id, status, chunk_count
                FROM chunk_sets
                WHERE processing_run_id = :processing_run_id
                ORDER BY is_active DESC, created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"processing_run_id": processing_run_id},
        ).mappings().first()

        if chunking is not None:
            embedding_row = db.execute(
                text(
                    """
                    SELECT
                        COUNT(e.id) AS total_count,
                        COUNT(e.id) FILTER (
                            WHERE e.status = 'completed'
                        ) AS completed_count,
                        COUNT(e.id) FILTER (
                            WHERE e.status = 'failed'
                        ) AS failed_count
                    FROM chunks c
                    LEFT JOIN embeddings e ON e.chunk_id = c.id
                    WHERE c.chunk_set_id = :chunk_set_id
                    """
                ),
                {"chunk_set_id": chunking["id"]},
            ).mappings().first()
            if embedding_row:
                embedding = dict(embedding_row)

    base = AdminDocumentItem(
        id=row["id"],
        announcement_id=row["announcement_id"],
        announcement_title=row["announcement_title"],
        file_name=row["original_filename"],
        document_type=row["document_format"],
        file_size=row["file_size_bytes"],
        download_status=row["download_status"],
        processing_status=row["execution_status"],
        analysis_status=row["verification_status"],
        created_at=row["created_at"],
    )

    return AdminDocumentDetail(
        **base.model_dump(),
        storage_path=row["storage_path"],
        checksum_sha256=row["checksum_sha256"],
        processing=ProcessingSummary(
            run_id=processing_run_id,
            execution_status=row["execution_status"],
            verification_status=row["verification_status"],
            current_stage=row["current_stage"],
            error_stage=row["error_stage"],
            error_code=row["error_code"],
            error_message=row["error_message"],
        ),
        structure=StructureSummary(
            schema_version=(
                structure["schema_version"] if structure else None
            ),
            element_count=(
                structure["element_count"] if structure else 0
            ),
        ),
        chunking=ChunkingSummary(
            status=chunking["status"] if chunking else None,
            chunk_count=chunking["chunk_count"] if chunking else 0,
        ),
        embedding=EmbeddingSummary(**embedding),
    )


def get_document_download_info(
    db: Session,
    document_id: int,
) -> dict[str, str | None] | None:
    row = db.execute(
        text(
            """
            SELECT original_filename, storage_path
            FROM documents
            WHERE id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().first()

    if row is None:
        return None

    path = row["storage_path"]
    if path and not Path(path).is_file():
        path = None

    return {
        "filename": row["original_filename"],
        "storage_path": path,
    }


def list_processing_runs(
    db: Session,
    page: int,
    size: int,
    execution_status: str | None,
    verification_status: str | None,
) -> AdminProcessingRunListResponse:
    conditions = ["1=1"]
    params: dict[str, Any] = {
        "offset": (page - 1) * size,
        "limit": size,
    }

    if execution_status:
        conditions.append("pr.execution_status = :execution_status")
        params["execution_status"] = execution_status
    if verification_status:
        conditions.append("pr.verification_status = :verification_status")
        params["verification_status"] = verification_status

    where = " AND ".join(conditions)

    total = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM processing_runs pr
            WHERE {where}
            """
        ),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                pr.id,
                a.id AS announcement_id,
                a.title AS announcement_title,
                d.id AS document_id,
                d.original_filename AS document_name,
                pr.execution_status,
                pr.verification_status,
                pr.current_stage,
                pr.error_stage,
                pr.error_code,
                pr.error_message,
                pr.started_at,
                pr.finished_at
            FROM processing_runs pr
            JOIN documents d ON d.id = pr.document_id
            JOIN announcements a ON a.id = d.announcement_id
            WHERE {where}
            ORDER BY pr.created_at DESC, pr.id DESC
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return AdminProcessingRunListResponse(
        items=[
            AdminProcessingRunItem(**dict(row))
            for row in rows
        ],
        page=page,
        size=size,
        total=total,
        total_pages=_total_pages(total, size),
    )


def _error_base_sql() -> str:
    return """
    SELECT
        el.id,
        el.announcement_id,
        a.title AS announcement_title,
        el.document_id,
        d.original_filename AS document_name,
        el.error_type,
        el.error_code,
        el.stage,
        el.message,
        el.status,
        el.resolution,
        el.created_at,
        el.resolved_at
    FROM error_logs el
    LEFT JOIN announcements a ON a.id = el.announcement_id
    LEFT JOIN documents d ON d.id = el.document_id
    """


def list_admin_errors(
    db: Session,
    page: int,
    size: int,
    search: str | None,
    error_type: str | None,
    error_status: str | None,
    occurred_from: date | None,
    occurred_to: date | None,
) -> AdminErrorListResponse:
    conditions = ["1=1"]
    params: dict[str, Any] = {
        "offset": (page - 1) * size,
        "limit": size,
    }

    if search:
        conditions.append(
            "("
            "COALESCE(a.title, '') ILIKE :search "
            "OR COALESCE(d.original_filename, '') ILIKE :search "
            "OR el.message ILIKE :search"
            ")"
        )
        params["search"] = f"%{search}%"
    if error_type:
        conditions.append("el.error_type = :error_type")
        params["error_type"] = error_type
    if error_status:
        conditions.append("el.status = :error_status")
        params["error_status"] = error_status
    if occurred_from:
        conditions.append("el.created_at::date >= :occurred_from")
        params["occurred_from"] = occurred_from
    if occurred_to:
        conditions.append("el.created_at::date <= :occurred_to")
        params["occurred_to"] = occurred_to

    where = " AND ".join(conditions)
    base_sql = _error_base_sql()

    total = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM error_logs el
            LEFT JOIN announcements a ON a.id = el.announcement_id
            LEFT JOIN documents d ON d.id = el.document_id
            WHERE {where}
            """
        ),
        params,
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            {base_sql}
            WHERE {where}
            ORDER BY el.created_at DESC, el.id DESC
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return AdminErrorListResponse(
        items=[AdminErrorDetail(**dict(row)) for row in rows],
        page=page,
        size=size,
        total=total,
        total_pages=_total_pages(total, size),
    )


def get_admin_error(
    db: Session,
    error_id: int,
) -> AdminErrorDetail | None:
    row = db.execute(
        text(
            f"""
            {_error_base_sql()}
            WHERE el.id = :error_id
            """
        ),
        {"error_id": error_id},
    ).mappings().first()

    return AdminErrorDetail(**dict(row)) if row else None


def update_error_status(
    db: Session,
    error_id: int,
    status_value: str,
    resolution: str | None,
) -> AdminErrorDetail | None:
    error_log = db.get(ErrorLog, error_id)

    if error_log is None:
        return None

    error_log.status = status_value
    error_log.resolution = resolution
    error_log.resolved_at = (
        datetime.now(timezone.utc)
        if status_value == "resolved"
        else None
    )

    db.commit()
    db.refresh(error_log)

    return get_admin_error(db, error_id)
