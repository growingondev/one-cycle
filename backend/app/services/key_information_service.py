from __future__ import annotations

from typing import Any

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.document import Document
from backend.app.models.key_information import KeyInformation
from backend.app.models.processing_run import ProcessingRun


VALID_EXTRACTION_STATUSES = {
    "pending",
    "completed",
    "failed",
}


def upsert_key_information(
    *,
    announcement_id: int,
    source_processing_run_id: int | None,
    application_period: dict[str, Any],
    eligibility: dict[str, Any],
    supply_information: dict[str, Any],
    income_asset_criteria: dict[str, Any],
    required_documents: dict[str, Any],
    winner_announcement: dict[str, Any],
    contact_information: dict[str, Any],
    extraction_status: str = "completed",
    is_verified: bool = False,
) -> dict[str, Any]:
    """
    추출된 공고 핵심정보를 key_information 테이블에 저장한다.

    공고당 key_information 행은 1개만 유지하며,
    기존 행이 있으면 UPDATE, 없으면 INSERT 한다.

    이 함수는 핵심정보를 직접 추출하지 않는다.
    """

    if extraction_status not in VALID_EXTRACTION_STATUSES:
        raise ValueError(
            "지원하지 않는 extraction_status입니다: "
            f"{extraction_status}"
        )

    with SessionLocal.begin() as db:
        announcement = db.get(
            Announcement,
            announcement_id,
        )

        if announcement is None:
            raise ValueError(
                f"존재하지 않는 announcement_id입니다: "
                f"{announcement_id}"
            )

        if source_processing_run_id is not None:
            processing_run = db.execute(
                select(ProcessingRun)
                .join(
                    Document,
                    Document.id == ProcessingRun.document_id,
                )
                .where(
                    ProcessingRun.id
                    == source_processing_run_id,
                    Document.announcement_id
                    == announcement_id,
                )
            ).scalar_one_or_none()

            if processing_run is None:
                raise ValueError(
                    "source_processing_run_id가 해당 공고에 "
                    "속한 ProcessingRun이 아닙니다: "
                    f"{source_processing_run_id}"
                )

        key_information = db.scalar(
            select(KeyInformation).where(
                KeyInformation.announcement_id
                == announcement_id
            )
        )

        created = key_information is None

        if key_information is None:
            key_information = KeyInformation(
                announcement_id=announcement_id,
            )
            db.add(key_information)

        key_information.source_processing_run_id = (
            source_processing_run_id
        )
        key_information.application_period = (
            application_period
        )
        key_information.eligibility = eligibility
        key_information.supply_information = (
            supply_information
        )
        key_information.income_asset_criteria = (
            income_asset_criteria
        )
        key_information.required_documents = (
            required_documents
        )
        key_information.winner_announcement = (
            winner_announcement
        )
        key_information.contact_information = (
            contact_information
        )
        key_information.extraction_status = (
            extraction_status
        )
        key_information.is_verified = is_verified

        db.flush()

        return {
            "id": key_information.id,
            "announcement_id": announcement_id,
            "source_processing_run_id": (
                source_processing_run_id
            ),
            "extraction_status": extraction_status,
            "is_verified": is_verified,
            "created": created,
        }