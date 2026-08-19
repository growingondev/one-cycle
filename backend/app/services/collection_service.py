from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.services.error_log_service import record_error

from backend.app.services.document_role_service import (
    DOCUMENT_ROLE_PRIMARY,
    classify_document_role,
)


VALID_RUN_STATUSES = {
    "running",
    "success",
    "partial",
    "failed",
}

VALID_DOWNLOAD_STATUSES = {
    "completed",
    "failed",
    "skipped",
}

VALID_DOCUMENT_FORMATS = {
    "hwp",
    "hwpx",
}

VALID_RECOLLECT_STATUSES = {
    "success",
    "partial",
    "failed",
}


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    formats = (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def _validate_collection_result(result: dict[str, Any]) -> None:
    execution_id = str(
        result.get("execution_id") or ""
    ).strip()

    if not execution_id:
        raise ValueError("crawler execution_id가 없습니다.")

    status = str(
        result.get("execution_status") or ""
    ).strip()

    if status not in VALID_RUN_STATUSES:
        raise ValueError(
            f"지원하지 않는 collection status입니다: {status}"
        )

    data = result.get("data")

    if data is None:
        raise ValueError("crawler data가 없습니다.")

    if not isinstance(data, list):
        raise ValueError("crawler data는 list여야 합니다.")


def _validate_recollection_result(
    result: dict[str, Any],
    *,
    expected_source_announcement_id: str,
) -> None:
    if not isinstance(result, dict):
        raise ValueError("crawler 재수집 결과는 dict여야 합니다.")

    execution_id = str(
        result.get("execution_id") or ""
    ).strip()

    if not execution_id:
        raise ValueError(
            "crawler 재수집 execution_id가 없습니다."
        )

    status = str(
        result.get("status") or ""
    ).strip()

    if status not in VALID_RECOLLECT_STATUSES:
        raise ValueError(
            f"지원하지 않는 recollect status입니다: {status}"
        )

    source_announcement_id = str(
        result.get("source_announcement_id") or ""
    ).strip()

    if not source_announcement_id:
        raise ValueError(
            "crawler 재수집 source_announcement_id가 없습니다."
        )

    if (
        source_announcement_id
        != expected_source_announcement_id
    ):
        raise ValueError(
            "재수집 대상 공고 식별자가 일치하지 않습니다. "
            f"expected={expected_source_announcement_id}, "
            f"actual={source_announcement_id}"
        )

    data = result.get("data")

    if data is not None and not isinstance(data, dict):
        raise ValueError(
            "crawler 재수집 data는 dict 또는 None이어야 합니다."
        )

    errors = result.get("errors")

    if errors is not None and not isinstance(errors, list):
        raise ValueError(
            "crawler 재수집 errors는 list여야 합니다."
        )


def persist_collection_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Crawler 반환 결과를
    CollectionRun → Announcement → Document 구조로 저장한다.
    """

    _validate_collection_result(result)

    execution_id = str(result["execution_id"]).strip()
    execution_status = str(
        result["execution_status"]
    ).strip()

    announcements_data = result.get("data") or []

    with SessionLocal.begin() as db:
        duplicate = db.scalar(
            select(CollectionRun.id).where(
                CollectionRun.execution_id == execution_id
            )
        )

        if duplicate is not None:
            raise ValueError(
                f"이미 저장된 execution_id입니다: {execution_id}"
            )

        collection_run = CollectionRun(
            execution_id=execution_id,
            status=execution_status,
            total_announcement_count=int(
                result.get("total_count") or 0
            ),
            successful_announcement_count=int(
                result.get("success_count") or 0
            ),
            failed_announcement_count=int(
                result.get("failed_count") or 0
            ),
            fatal_error=result.get("fatal_error"),
            finished_at=datetime.now(timezone.utc),
        )

        db.add(collection_run)
        db.flush()

        announcement_ids: list[int] = []
        document_ids: list[int] = []
        analysis_document_ids: list[int] = []

        for raw_announcement in announcements_data:
            source_announcement_id = str(
                raw_announcement.get(
                    "source_announcement_id"
                )
                or ""
            ).strip()

            title = str(
                raw_announcement.get("title")
                or ""
            ).strip()

            detail_url = str(
                raw_announcement.get("detail_url")
                or ""
            ).strip()

            if not source_announcement_id:
                raise ValueError(
                    "source_announcement_id가 없는 공고가 있습니다."
                )

            if not title:
                raise ValueError(
                    f"공고 제목이 없습니다: {source_announcement_id}"
                )

            announcement = Announcement(
                collection_run_id=collection_run.id,
                source_announcement_id=source_announcement_id,
                title=title,
                detail_url=detail_url,
                notice_type=(
                    str(
                        raw_announcement.get("notice_type")
                        or ""
                    ).strip()
                    or None
                ),
                region=(
                    str(
                        raw_announcement.get("region")
                        or ""
                    ).strip()
                    or None
                ),
                announcement_date=_parse_date(
                    raw_announcement.get("post_date")
                ),
                publication_status=(
                    str(
                        raw_announcement.get(
                            "publication_status"
                        )
                        or ""
                    ).strip()
                    or None
                ),
            )

            db.add(announcement)
            db.flush()

            announcement_ids.append(announcement.id)

            for raw_document in (
                raw_announcement.get("documents") or []
            ):
                document_format = str(
                    raw_document.get("file_format")
                    or ""
                ).strip().lower()

                if document_format not in VALID_DOCUMENT_FORMATS:
                    continue

                download_status = str(
                    raw_document.get("download_status")
                    or ""
                ).strip()

                if download_status not in VALID_DOWNLOAD_STATUSES:
                    raise ValueError(
                        "지원하지 않는 download_status입니다: "
                        f"{download_status}"
                    )

                file_name = str(
                    raw_document.get("file_name")
                    or ""
                ).strip()

                if not file_name:
                    raise ValueError(
                        "수집 문서의 file_name이 없습니다."
                    )

                document_role = classify_document_role(
                    file_name
                )

                document = Document(
                    announcement_id=announcement.id,
                    original_filename=file_name,
                    document_format=document_format,
                    document_role=document_role,
                    storage_path=(
                        str(
                            raw_document.get("storage_path")
                            or ""
                        ).strip()
                        or None
                    ),
                    file_size_bytes=int(
                        raw_document.get(
                            "file_size_bytes"
                        )
                        or 0
                    ),
                    checksum_sha256=(
                        str(
                            raw_document.get(
                                "checksum_sha256"
                            )
                            or ""
                        ).strip()
                        or None
                    ),
                    download_status=download_status,
                    error_message=raw_document.get(
                        "error_message"
                    ),
                )

                db.add(document)
                db.flush()

                document_ids.append(document.id)

                if (
                    document_role == DOCUMENT_ROLE_PRIMARY
                    and download_status == "completed"
                ):
                    analysis_document_ids.append(
                        document.id
                    )

        return {
            "collection_run_id": collection_run.id,
            "execution_id": collection_run.execution_id,
            "status": collection_run.status,
            "announcement_count": len(
                announcement_ids
            ),
            "document_count": len(document_ids),
            "announcement_ids": announcement_ids,
            "document_ids": document_ids,
            "analysis_document_count": len(
                analysis_document_ids
            ),
            "analysis_document_ids": (
                analysis_document_ids
            ),
        }


def collect_and_persist() -> dict[str, Any]:
    """
    실제 Crawler 실행 후 결과를 DB에 저장한다.
    """

    from crawler.crawler import crawl_lh_notices

    result = crawl_lh_notices()

    return persist_collection_result(result)


def recollect_and_persist(
    *,
    announcement_id: int,
) -> dict[str, Any]:
    """
    기존 Announcement 한 건을 다시 수집하고
    새 HWP/HWPX Document를 DB에 저장한다.

    동일 파일명 + 동일 checksum의 문서는
    중복 저장하지 않는다.

    Crawler 오류는 Backend ErrorLog에 저장한다.
    """

    if (
        isinstance(announcement_id, bool)
        or not isinstance(announcement_id, int)
        or announcement_id <= 0
    ):
        raise ValueError(
            "announcement_id는 1 이상의 정수여야 합니다."
        )

    # 1. Backend DB의 공고 식별 정보 조회
    with SessionLocal() as db:
        announcement = db.get(
            Announcement,
            announcement_id,
        )

        if announcement is None:
            raise ValueError(
                f"공고를 찾을 수 없습니다: {announcement_id}"
            )

        source_announcement_id = str(
            announcement.source_announcement_id
        ).strip()

        detail_url = str(
            announcement.detail_url
        ).strip()

        collection_run_id = (
            announcement.collection_run_id
        )

    if not source_announcement_id:
        raise ValueError(
            "공고의 source_announcement_id가 없습니다."
        )

    if not detail_url:
        raise ValueError(
            "공고의 detail_url이 없습니다."
        )

    # 2. Crawler 개별 재수집 callable 실행
    from crawler.crawler import recollect_lh_notice

    crawler_result = recollect_lh_notice(
        source_announcement_id=source_announcement_id,
        detail_url=detail_url,
    )

    _validate_recollection_result(
        crawler_result,
        expected_source_announcement_id=(
            source_announcement_id
        ),
    )

    data = crawler_result.get("data") or {}
    raw_documents = data.get("documents") or []

    new_document_ids: list[int] = []
    new_analysis_document_ids: list[int] = []
    reused_document_ids: list[int] = []
    document_by_filename: dict[str, int] = {}

    # 3. 성공적으로 다운로드된 HWP/HWPX 저장
    with SessionLocal.begin() as db:
        announcement_exists = db.get(
            Announcement,
            announcement_id,
        )

        if announcement_exists is None:
            raise ValueError(
                f"공고를 찾을 수 없습니다: {announcement_id}"
            )

        for raw_document in raw_documents:
            document_format = str(
                raw_document.get("file_format")
                or ""
            ).strip().lower()

            if document_format not in VALID_DOCUMENT_FORMATS:
                continue

            file_name = str(
                raw_document.get("file_name")
                or ""
            ).strip()

            if not file_name:
                raise ValueError(
                    "재수집 문서의 file_name이 없습니다."
                )

            download_status = str(
                raw_document.get("download_status")
                or ""
            ).strip()

            if download_status not in VALID_DOWNLOAD_STATUSES:
                raise ValueError(
                    "지원하지 않는 download_status입니다: "
                    f"{download_status}"
                )

            document_role = classify_document_role(
                file_name
            )

            checksum = (
                str(
                    raw_document.get(
                        "checksum_sha256"
                    )
                    or ""
                ).strip()
                or None
            )

            existing_document = None

            if checksum:
                existing_document = db.scalar(
                    select(Document).where(
                        Document.announcement_id
                        == announcement_id,
                        Document.original_filename
                        == file_name,
                        Document.checksum_sha256
                        == checksum,
                    )
                )

            if existing_document is not None:
                reused_document_ids.append(
                    existing_document.id
                )

                document_by_filename[
                    file_name
                ] = existing_document.id

                continue

            document = Document(
                announcement_id=announcement_id,
                original_filename=file_name,
                document_format=document_format,
                document_role=document_role,
                storage_path=(
                    str(
                        raw_document.get(
                            "storage_path"
                        )
                        or ""
                    ).strip()
                    or None
                ),
                file_size_bytes=int(
                    raw_document.get(
                        "file_size_bytes"
                    )
                    or 0
                ),
                checksum_sha256=checksum,
                download_status=download_status,
                error_message=raw_document.get(
                    "error_message"
                ),
            )

            db.add(document)
            db.flush()

            new_document_ids.append(
                document.id
            )

            if (
                document_role == DOCUMENT_ROLE_PRIMARY
                and download_status == "completed"
            ):
                new_analysis_document_ids.append(
                    document.id
                )

            document_by_filename[
                file_name
            ] = document.id

    # 4. Crawler 오류를 Backend ErrorLog에 저장
    crawler_errors = (
        crawler_result.get("errors")
        or []
    )

    recorded_error_ids: list[int] = []

    for raw_error in crawler_errors:
        file_name = str(
            raw_error.get("file_name")
            or ""
        ).strip()

        error_result = record_error(
            error_type=str(
                raw_error.get("error_type")
                or "collection"
            ).strip(),
            stage=str(
                raw_error.get("stage")
                or "recollect"
            ).strip(),
            error_code=(
                str(
                    raw_error.get("error_code")
                    or ""
                ).strip()
                or None
            ),
            message=str(
                raw_error.get("message")
                or "Crawler 재수집 오류"
            ),
            collection_run_id=collection_run_id,
            announcement_id=announcement_id,
            document_id=(
                document_by_filename.get(
                    file_name
                )
                if file_name
                else None
            ),
        )

        error_id = error_result.get("error_id")

        if error_id is not None:
            recorded_error_ids.append(
                int(error_id)
            )

    all_document_ids = (
        new_document_ids
        + reused_document_ids
    )

    return {
        "execution_id": crawler_result["execution_id"],
        "status": crawler_result["status"],
        "announcement_id": announcement_id,
        "source_announcement_id": (
            source_announcement_id
        ),
        "detail_url": detail_url,
        "document_count": len(
            all_document_ids
        ),
        "new_document_ids": (
            new_document_ids
        ),
        "new_analysis_document_count": len(
            new_analysis_document_ids
        ),
        "new_analysis_document_ids": (
            new_analysis_document_ids
        ),
        "reused_document_ids": (
            reused_document_ids
        ),
        "document_ids": all_document_ids,
        "error_count": len(
            recorded_error_ids
        ),
        "error_ids": recorded_error_ids,
    }