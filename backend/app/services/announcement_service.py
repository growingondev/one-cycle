from __future__ import annotations

import math
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.schemas.announcement import (
    AnnouncementDetailResponse,
    AnnouncementDocumentItem,
    AnnouncementListItem,
    AnnouncementListResponse,
    KeyInformationResponse,
)


def list_active_announcements(
    db: Session,
    page: int,
    size: int,
    search: str | None,
    region: str | None,
    status_filter: str | None,
    sort_order: str = "latest",
) -> AnnouncementListResponse:
    conditions = [
        "a.collection_run_id = ss.active_collection_run_id",
        "a.is_visible IS TRUE",
    ]
    params: dict[str, object] = {
        "offset": (page - 1) * size,
        "limit": size,
    }

    if search:
        conditions.append("a.title ILIKE :search")
        params["search"] = f"%{search}%"
    if region:
        conditions.append("a.region = :region")
        params["region"] = region
    if status_filter:
        if status_filter == "상태 미확인":
            conditions.append(
                "("
                "a.publication_status IS NULL "
                "OR a.publication_status = '' "
                "OR a.publication_status = 'fixture'"
                ")"
            )
        else:
            conditions.append(
                "a.publication_status = :status"
            )
            params["status"] = status_filter

    where = " AND ".join(conditions)

    notice_number_order = (
        "CASE "
        "WHEN a.notice_number ~ '^[0-9]+$' "
        "THEN a.notice_number::integer "
        "END"
    )

    if sort_order == "oldest":
        order_by = (
            "a.announcement_date ASC NULLS LAST, "
            f"{notice_number_order} ASC NULLS LAST, "
            "a.id ASC"
        )
    else:
        order_by = (
            "a.announcement_date DESC NULLS LAST, "
            f"{notice_number_order} DESC NULLS LAST, "
            "a.id DESC"
        )

    total = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM system_state ss
            JOIN announcements a
              ON a.collection_run_id = ss.active_collection_run_id
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
                a.notice_number,
                a.title,
                a.notice_type,
                a.region,
                a.announcement_date,
                a.publication_status,
                COALESCE(
                    a.deadline_date::text,
                    ki.application_period ->> 'end'
                ) AS deadline_date
            FROM system_state ss
            JOIN announcements a
              ON a.collection_run_id = ss.active_collection_run_id
            LEFT JOIN key_information ki
              ON ki.announcement_id = a.id
            WHERE {where}
            ORDER BY {order_by}
            OFFSET :offset
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return AnnouncementListResponse(
        items=[
            AnnouncementListItem(
                id=row["id"],
                notice_number=row["notice_number"],
                title=row["title"],
                notice_type=row["notice_type"],
                region=row["region"],
                announcementDate=row["announcement_date"],
                publicationStatus=row["publication_status"],
                deadlineDate=row["deadline_date"],
            )
            for row in rows
        ],
        page=page,
        size=size,
        total=total,
        total_pages=math.ceil(total / size) if total else 0,
    )


def get_active_announcement(
    db: Session,
    announcement_id: int,
) -> AnnouncementDetailResponse | None:
    row = db.execute(
        text(
            """
            SELECT
                a.id,
                a.title,
                a.region,
                a.notice_type,
                a.announcement_date,
                a.publication_status,
                a.detail_url,
                ki.application_period,
                ki.eligibility,
                ki.supply_information,
                ki.income_asset_criteria,
                ki.required_documents,
                ki.winner_announcement,
                ki.contact_information
            FROM system_state ss
            JOIN announcements a
              ON a.collection_run_id = ss.active_collection_run_id
            LEFT JOIN key_information ki
              ON ki.announcement_id = a.id
            WHERE a.id = :announcement_id
              AND a.is_visible IS TRUE
            LIMIT 1
            """
        ),
        {"announcement_id": announcement_id},
    ).mappings().first()

    if row is None:
        return None

    documents = db.execute(
        text(
            """
            SELECT
                id,
                original_filename,
                document_format,
                download_status,
                file_size_bytes,
                created_at
            FROM documents
            WHERE announcement_id = :announcement_id
            ORDER BY id
            """
        ),
        {"announcement_id": announcement_id},
    ).mappings().all()

    key_info = KeyInformationResponse(
        applicationPeriod=row["application_period"] or {},
        eligibility=row["eligibility"] or {},
        supplyInformation=row["supply_information"] or {},
        incomeAssetCriteria=row["income_asset_criteria"] or {},
        requiredDocuments=row["required_documents"] or {},
        winnerAnnouncement=row["winner_announcement"] or {},
        contactInformation=row["contact_information"] or {},
    )

    return AnnouncementDetailResponse(
        id=row["id"],
        title=row["title"],
        region=row["region"],
        notice_type=row["notice_type"],
        announcementDate=row["announcement_date"],
        publicationStatus=row["publication_status"],
        detailUrl=row["detail_url"],
        documents=[
            AnnouncementDocumentItem(
                id=d["id"],
                originalFilename=d["original_filename"],
                documentFormat=d["document_format"],
                downloadStatus=d["download_status"],
                fileSizeBytes=d["file_size_bytes"],
                createdAt=d["created_at"],
            )
            for d in documents
        ],
        keyInformation=key_info,
    )


def get_active_announcement_download_info(
    db: Session,
    announcement_id: int,
) -> dict[str, str | None] | None:
    """Return the primary downloadable document for a public announcement."""
    row = db.execute(
        text(
            """
            SELECT d.original_filename, d.storage_path
            FROM system_state ss
            JOIN announcements a
              ON a.collection_run_id = ss.active_collection_run_id
            JOIN documents d
              ON d.announcement_id = a.id
            WHERE a.id = :announcement_id
              AND a.is_visible IS TRUE
              AND d.download_status = 'completed'
            ORDER BY
              CASE d.document_role
                WHEN 'primary' THEN 0
                WHEN 'supporting' THEN 1
                ELSE 2
              END,
              d.created_at DESC,
              d.id DESC
            LIMIT 1
            """
        ),
        {"announcement_id": announcement_id},
    ).mappings().first()

    if row is None:
        return None

    storage_path = row["storage_path"]
    if storage_path and not Path(storage_path).is_file():
        storage_path = None

    return {
        "filename": row["original_filename"],
        "storage_path": storage_path,
    }
