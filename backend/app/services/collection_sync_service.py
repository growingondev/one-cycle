from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from backend.app.clients import crawler_client
from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.system_state import SystemState
from backend.app.services.error_log_service import record_error
from backend.app.services.integration_service import (
    recollect_persist_and_process,
)

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
SYNC_ADVISORY_LOCK_ID = 615_120_315
VALID_SCAN_STATUSES = {"success", "partial"}
CORRECTION_PREFIX = re.compile(
    r"^\s*[\[\(]\s*(?:정정\s*공고|수정\s*공고|변경\s*공고|정정|수정|변경)"
    r"\s*[\]\)]\s*",
    re.IGNORECASE,
)


def normalize_notice_title(title: str) -> str:
    normalized = str(title or "").strip()

    while True:
        without_prefix = CORRECTION_PREFIX.sub("", normalized, count=1)
        if without_prefix == normalized:
            break
        normalized = without_prefix.strip()

    return " ".join(normalized.split()).casefold()


def is_correction_title(title: str) -> bool:
    return CORRECTION_PREFIX.match(str(title or "")) is not None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value

    normalized = str(value or "").strip()
    if not normalized:
        return None

    for date_format in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            separator = date_format[2]
            return date.fromisoformat(normalized.replace(separator, "-"))
        except ValueError:
            continue

    return None


def _normalized_scan_notice(raw_notice: dict[str, Any]) -> dict[str, Any]:
    source_id = str(
        raw_notice.get("source_announcement_id") or ""
    ).strip()
    title = str(raw_notice.get("title") or "").strip()
    detail_url = str(raw_notice.get("detail_url") or "").strip()

    if not source_id:
        raise ValueError("스캔 공고에 source_announcement_id가 없습니다.")
    if not title:
        raise ValueError(f"스캔 공고 제목이 없습니다: {source_id}")
    if not detail_url:
        raise ValueError(f"스캔 공고 URL이 없습니다: {source_id}")

    return {
        "source_announcement_id": source_id,
        "title": title,
        "normalized_title": normalize_notice_title(title),
        "notice_number": (
            str(raw_notice.get("notice_number") or "").strip()
            or None
        ),
        "notice_type": (
            str(raw_notice.get("notice_type") or "").strip()
            or None
        ),
        "region": (
            str(raw_notice.get("region") or "").strip()
            or None
        ),
        "announcement_date": _parse_date(raw_notice.get("post_date")),
        "deadline_date": _parse_date(raw_notice.get("deadline_date")),
        "publication_status": (
            str(raw_notice.get("publication_status") or "").strip()
            or None
        ),
        "detail_url": detail_url,
    }


def _metadata_payload(values: dict[str, Any]) -> dict[str, str]:
    return {
        "source_announcement_id": str(
            values.get("source_announcement_id") or ""
        ),
        "title": str(values.get("title") or ""),
        "notice_number": str(values.get("notice_number") or ""),
        "notice_type": str(values.get("notice_type") or ""),
        "region": str(values.get("region") or ""),
        "announcement_date": (
            values["announcement_date"].isoformat()
            if isinstance(values.get("announcement_date"), date)
            else str(values.get("announcement_date") or "")
        ),
        "deadline_date": (
            values["deadline_date"].isoformat()
            if isinstance(values.get("deadline_date"), date)
            else str(values.get("deadline_date") or "")
        ),
        "publication_status": str(
            values.get("publication_status") or ""
        ),
        "detail_url": str(values.get("detail_url") or ""),
    }


def calculate_metadata_hash(values: dict[str, Any]) -> str:
    serialized = json.dumps(
        _metadata_payload(values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _announcement_values(announcement: Announcement) -> dict[str, Any]:
    return {
        "source_announcement_id": announcement.source_announcement_id,
        "title": announcement.title,
        "notice_number": announcement.notice_number,
        "notice_type": announcement.notice_type,
        "region": announcement.region,
        "announcement_date": announcement.announcement_date,
        "deadline_date": announcement.deadline_date,
        "publication_status": announcement.publication_status,
        "detail_url": announcement.detail_url,
    }


def classify_notice_change(
    existing: Announcement | None,
    notice: dict[str, Any],
    metadata_hash: str,
) -> str:
    if existing is None:
        return (
            "correction"
            if is_correction_title(notice["title"])
            else "new"
        )

    existing_hash = (
        existing.metadata_hash
        or calculate_metadata_hash(_announcement_values(existing))
    )
    if existing_hash == metadata_hash and existing.is_visible:
        return "unchanged"

    if not existing.is_visible and existing.change_type in {
        "new",
        "correction",
        "updated",
    }:
        return existing.change_type

    return "updated"


def _validate_scan_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        raise TypeError("Crawler scan 결과는 dict여야 합니다.")

    execution_id = str(result.get("execution_id") or "").strip()
    if not execution_id:
        raise ValueError("Crawler scan execution_id가 없습니다.")

    status = str(result.get("execution_status") or "").strip()
    if status not in VALID_SCAN_STATUSES:
        raise RuntimeError(
            "Crawler scan이 성공하지 못했습니다: "
            f"status={status or 'unknown'}"
        )

    notices = result.get("notices")
    if not isinstance(notices, list):
        raise TypeError("Crawler scan notices는 list여야 합니다.")

    return notices


def _find_correction_target(
    notice: dict[str, Any],
    announcements: list[Announcement],
) -> Announcement | None:
    candidates = [
        announcement
        for announcement in announcements
        if announcement.is_visible
        and announcement.source_announcement_id
        != notice["source_announcement_id"]
        and (
            announcement.normalized_title
            or normalize_notice_title(announcement.title)
        )
        == notice["normalized_title"]
    ]

    if len(candidates) == 1:
        return candidates[0]

    narrowed = [
        announcement
        for announcement in candidates
        if (
            not notice.get("region")
            or announcement.region == notice["region"]
        )
        and (
            not notice.get("notice_type")
            or announcement.notice_type == notice["notice_type"]
        )
    ]

    return narrowed[0] if len(narrowed) == 1 else None


def _apply_notice_metadata(
    announcement: Announcement,
    notice: dict[str, Any],
    *,
    metadata_hash: str,
    change_type: str,
    seen_at: datetime,
) -> None:
    announcement.title = notice["title"]
    announcement.normalized_title = notice["normalized_title"]
    announcement.notice_number = notice["notice_number"]
    announcement.notice_type = notice["notice_type"]
    announcement.region = notice["region"]
    announcement.announcement_date = notice["announcement_date"]
    announcement.deadline_date = notice["deadline_date"]
    announcement.publication_status = notice["publication_status"]
    announcement.detail_url = notice["detail_url"]
    announcement.metadata_hash = metadata_hash
    announcement.change_type = change_type
    announcement.last_seen_at = seen_at


def _processing_succeeded(result: dict[str, Any]) -> bool:
    processing = result.get("document_processing") or {}
    return (
        result.get("status") == "success"
        and int(processing.get("failed_count") or 0) == 0
    )


def _write_sync_log(result: dict[str, Any]) -> str | None:
    configured_root = str(settings.document_storage_root or "").strip()
    if not configured_root:
        return None

    now = datetime.now(KST)
    log_directory = (
        Path(configured_root)
        / "runs"
        / now.strftime("%Y")
        / now.strftime("%m")
        / now.strftime("%d")
    )
    log_directory.mkdir(parents=True, exist_ok=True)

    execution_id = str(result.get("execution_id") or "scan_unknown")
    log_path = log_directory / f"{execution_id}.json"
    temporary_path = log_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary_path.replace(log_path)
    return str(log_path)


def _run_incremental_sync_locked() -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    scan_result = crawler_client.scan_announcements()
    raw_notices = _validate_scan_result(scan_result)

    with SessionLocal() as db:
        system_state = db.get(SystemState, 1)
        active_run_id = (
            system_state.active_collection_run_id
            if system_state is not None
            else None
        )

        if active_run_id is None:
            return {
                "execution_id": scan_result["execution_id"],
                "status": "skipped",
                "reason": "initial_collection_required",
                "checked_count": len(raw_notices),
            }

        announcements = list(
            db.scalars(
                select(Announcement).where(
                    Announcement.collection_run_id == active_run_id
                )
            ).all()
        )

    by_source_id = {
        announcement.source_announcement_id: announcement
        for announcement in announcements
    }
    seen_source_ids: set[str] = set()
    counts = {
        "checked_count": 0,
        "new_count": 0,
        "correction_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "failed_count": 0,
    }
    processed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen_at = datetime.now(timezone.utc)

    for raw_notice in raw_notices:
        counts["checked_count"] += 1

        try:
            notice = _normalized_scan_notice(raw_notice)
        except (AttributeError, TypeError, ValueError) as exc:
            counts["failed_count"] += 1
            errors.append({"stage": "normalize", "message": str(exc)})
            continue

        source_id = notice["source_announcement_id"]
        if source_id in seen_source_ids:
            counts["failed_count"] += 1
            errors.append(
                {
                    "source_announcement_id": source_id,
                    "stage": "compare",
                    "message": "스캔 결과에 중복 공고 ID가 있습니다.",
                }
            )
            continue
        seen_source_ids.add(source_id)

        metadata_hash = calculate_metadata_hash(notice)
        existing = by_source_id.get(source_id)
        change_type = classify_notice_change(
            existing,
            notice,
            metadata_hash,
        )

        if existing is not None:
            if change_type == "unchanged":
                with SessionLocal.begin() as db:
                    current = db.get(Announcement, existing.id)
                    if current is not None:
                        current.metadata_hash = metadata_hash
                        current.normalized_title = notice[
                            "normalized_title"
                        ]
                        current.last_seen_at = seen_at
                counts["unchanged_count"] += 1
                continue

            announcement_id = existing.id
            correction_target = (
                _find_correction_target(notice, announcements)
                if change_type == "correction"
                else None
            )
            was_visible = existing.is_visible
        else:
            correction_target = (
                _find_correction_target(notice, announcements)
                if change_type == "correction"
                else None
            )

            with SessionLocal.begin() as db:
                pending = Announcement(
                    collection_run_id=active_run_id,
                    source_announcement_id=source_id,
                    title=notice["title"],
                    detail_url=notice["detail_url"],
                    is_visible=False,
                    supersedes_announcement_id=(
                        correction_target.id
                        if correction_target is not None
                        else None
                    ),
                )
                _apply_notice_metadata(
                    pending,
                    notice,
                    metadata_hash=metadata_hash,
                    change_type=change_type,
                    seen_at=seen_at,
                )
                db.add(pending)
                db.flush()
                announcement_id = pending.id
            was_visible = False

        try:
            pipeline_result = recollect_persist_and_process(
                announcement_id=announcement_id,
                source_announcement_id_override=source_id,
                detail_url_override=notice["detail_url"],
            )
        except Exception as exc:  # noqa: BLE001 - 외부 수집 실패를 건별 격리한다.
            pipeline_result = {"status": "failed"}
            errors.append(
                {
                    "source_announcement_id": source_id,
                    "stage": "recollect",
                    "message": str(exc),
                }
            )

        if not _processing_succeeded(pipeline_result):
            counts["failed_count"] += 1
            if not any(
                error.get("source_announcement_id") == source_id
                and error.get("stage") == "recollect"
                for error in errors
            ):
                errors.append(
                    {
                        "source_announcement_id": source_id,
                        "stage": "recollect",
                        "message": (
                            "단건 수집 또는 문서 처리에 실패했습니다."
                        ),
                    }
                )
            if existing is None:
                with SessionLocal.begin() as db:
                    pending = db.get(Announcement, announcement_id)
                    if pending is not None:
                        db.delete(pending)
            continue

        with SessionLocal.begin() as db:
            current = db.get(Announcement, announcement_id)
            if current is None:
                raise RuntimeError(
                    f"처리 완료 공고를 찾을 수 없습니다: {announcement_id}"
                )

            _apply_notice_metadata(
                current,
                notice,
                metadata_hash=metadata_hash,
                change_type=change_type,
                seen_at=seen_at,
            )
            current.is_visible = True
            current.supersedes_announcement_id = (
                correction_target.id
                if correction_target is not None
                else current.supersedes_announcement_id
            )

            if correction_target is not None:
                previous = db.get(Announcement, correction_target.id)
                if previous is not None:
                    previous.is_visible = False

            if not was_visible:
                run = db.get(CollectionRun, active_run_id)
                if run is not None:
                    run.total_announcement_count += 1
                    run.successful_announcement_count += 1

        if change_type == "new":
            counts["new_count"] += 1
        elif change_type == "correction":
            counts["correction_count"] += 1
        else:
            counts["updated_count"] += 1

        processed.append(
            {
                "announcement_id": announcement_id,
                "source_announcement_id": source_id,
                "change_type": change_type,
                "new_analysis_document_count": pipeline_result.get(
                    "new_analysis_document_count",
                    0,
                ),
            }
        )

    result = {
        "execution_id": scan_result["execution_id"],
        "status": (
            "success" if counts["failed_count"] == 0 else "partial"
        ),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        **counts,
        "processed": processed,
        "errors": errors,
    }

    try:
        result["run_log_path"] = _write_sync_log(result)
    except Exception as exc:  # noqa: BLE001 - 로그 저장 실패가 동기화를 뒤집지 않게 한다.
        result["run_log_error"] = str(exc)

    return result


def run_incremental_sync() -> dict[str, Any]:
    """DB advisory lock으로 중복 실행을 막고 증분 동기화를 수행한다."""
    lock_db = SessionLocal()
    active_run_id: int | None = None
    acquired = False

    try:
        acquired = bool(
            lock_db.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": SYNC_ADVISORY_LOCK_ID},
            )
        )
        if not acquired:
            return {
                "status": "skipped",
                "reason": "sync_already_running",
            }

        return _run_incremental_sync_locked()

    except Exception as exc:
        try:
            state = lock_db.get(SystemState, 1)
            active_run_id = (
                state.active_collection_run_id
                if state is not None
                else None
            )
            record_error(
                error_type="collection",
                stage="incremental_sync",
                error_code="INCREMENTAL_SYNC_FAILED",
                message=str(exc),
                collection_run_id=active_run_id,
            )
        except Exception:
            LOGGER.exception("Failed to record incremental sync error")
        raise

    finally:
        try:
            if acquired:
                lock_db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": SYNC_ADVISORY_LOCK_ID},
                )
        finally:
            lock_db.close()
