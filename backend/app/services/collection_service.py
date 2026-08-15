from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document


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

                # MVP에서는 HWP/HWPX만 DB 분석 대상으로 저장
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

                document = Document(
                    announcement_id=announcement.id,
                    original_filename=str(
                        raw_document.get("file_name")
                        or ""
                    ).strip(),
                    document_format=document_format,
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
        }


def collect_and_persist() -> dict[str, Any]:
    """
    실제 Crawler 실행 후 결과를 DB에 저장한다.

    crawler import를 함수 내부에서 수행해서
    DB 저장 로직 자체는 Selenium 설치 여부와 독립적으로
    테스트할 수 있도록 한다.
    """

    from crawler.crawler import crawl_lh_notices

    result = crawl_lh_notices()

    return persist_collection_result(result)