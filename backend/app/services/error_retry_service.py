from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.error_log import ErrorLog


class ErrorRetryConflictError(RuntimeError):
    """The selected error is already being retried or resolved."""


class ErrorRetryNotSupportedError(RuntimeError):
    """The error does not have enough target information to retry safely."""


class ErrorRetryExecutionError(RuntimeError):
    """The targeted retry ran, but the same work did not complete."""

    def __init__(self, message: str, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class RetryTarget:
    error_id: int
    announcement_id: int | None
    document_id: int | None
    error_type: str
    stage: str
    target_filename: str | None


DOWNLOAD_RETRY_STAGES = {
    "download",
    "attachment",
}


def _infer_legacy_target_filename(message: str) -> str | None:
    """Recover the filename from download errors created before migration."""

    candidate = str(message or "").rsplit(":", 1)[-1].strip()
    if not candidate:
        return None

    candidate = PurePath(candidate.replace("\\", "/")).name
    for partial_suffix in (".crdownload", ".tmp"):
        if candidate.lower().endswith(partial_suffix):
            candidate = candidate[: -len(partial_suffix)]

    if not candidate.lower().endswith((".hwp", ".hwpx")):
        return None

    return candidate


def _claim_retry(error_id: int) -> RetryTarget:
    """Atomically claim one unresolved error for retry."""

    with SessionLocal.begin() as db:
        error = db.scalar(
            select(ErrorLog)
            .where(ErrorLog.id == error_id)
            .with_for_update()
        )

        if error is None:
            raise LookupError(f"오류를 찾을 수 없습니다: {error_id}")

        if error.status == "in_progress":
            raise ErrorRetryConflictError(
                "이미 재시도 중인 오류입니다."
            )

        if error.status == "resolved":
            raise ErrorRetryConflictError(
                "이미 해결된 오류입니다."
            )

        normalized_stage = str(error.stage or "").strip().lower()
        normalized_error_type = str(
            error.error_type or ""
        ).strip().lower()

        is_download_retry = (
            normalized_stage in DOWNLOAD_RETRY_STAGES
            or normalized_error_type == "download"
        )

        target_filename = error.target_filename
        if (
            is_download_retry
            and not target_filename
        ):
            target_filename = _infer_legacy_target_filename(
                error.message
            )

        if is_download_retry and error.announcement_id is None:
            raise ErrorRetryNotSupportedError(
                "이 다운로드 오류에는 대상 공고 정보가 없어 "
                "실패한 문서만 안전하게 재시도할 수 없습니다."
            )

        if is_download_retry and not target_filename:
            raise ErrorRetryNotSupportedError(
                "이 다운로드 오류에는 대상 파일명이 없어 "
                "실패한 문서만 안전하게 재시도할 수 없습니다."
            )

        if not is_download_retry and error.document_id is None:
            raise ErrorRetryNotSupportedError(
                "이 처리 오류에는 대상 문서 정보가 없어 "
                "해당 오류 단계만 안전하게 재시도할 수 없습니다."
            )

        error.status = "in_progress"
        error.resolution = (
            f"{normalized_stage or '처음'} 단계 재시도 진행 중"
        )
        error.resolved_at = None

        return RetryTarget(
            error_id=error.id,
            announcement_id=error.announcement_id,
            document_id=error.document_id,
            error_type=normalized_error_type,
            stage=normalized_stage,
            target_filename=target_filename,
        )


def _finish_retry(
    error_id: int,
    *,
    succeeded: bool,
    message: str,
) -> None:
    with SessionLocal.begin() as db:
        error = db.get(ErrorLog, error_id)
        if error is None:
            return

        error.status = "resolved" if succeeded else "unresolved"
        error.resolution = message[:2000]
        error.resolved_at = (
            datetime.now(timezone.utc) if succeeded else None
        )


def _is_download_retry(target: RetryTarget) -> bool:
    return (
        target.stage in DOWNLOAD_RETRY_STAGES
        or target.error_type == "download"
    )


def _retry_download_document(target: RetryTarget) -> dict[str, Any]:
    # Imported lazily to avoid the integration_service -> pipeline_gateway
    # import cycle during application startup.
    from backend.app.services.integration_service import (
        recollect_persist_and_process,
    )

    assert target.announcement_id is not None
    assert target.target_filename is not None
    result = recollect_persist_and_process(
        announcement_id=target.announcement_id,
        target_file_name=target.target_filename,
    )

    processing = result.get("document_processing") or {}
    crawler_status = str(result.get("status") or "").strip().lower()
    error_count = int(result.get("error_count") or 0)
    processing_failures = int(processing.get("failed_count") or 0)

    if (
        crawler_status in {"failed", "error"}
        or error_count > 0
        or processing_failures > 0
    ):
        raise ErrorRetryExecutionError(
            "실패했던 문서의 다운로드 또는 후속 처리에 다시 실패했습니다.",
            result,
        )

    return {
        "success": True,
        "retry_scope": "document",
        "announcement_id": target.announcement_id,
        "target_filename": target.target_filename,
        "start_stage": target.stage,
        "result": result,
    }


def _retry_document(target: RetryTarget) -> dict[str, Any]:
    # A document worker run recreates artifacts from the nearest safe
    # checkpoint for the selected document only. It never starts collection.
    from backend.app.services.pipeline_gateway import reprocess_document

    assert target.document_id is not None
    result = reprocess_document(
        target.document_id,
        start_stage=target.stage,
    )

    if not isinstance(result, dict) or result.get("success") is not True:
        message = (
            str(result.get("message") or "")
            if isinstance(result, dict)
            else ""
        )
        raise ErrorRetryExecutionError(
            message or "해당 문서 재처리에 다시 실패했습니다.",
            result if isinstance(result, dict) else None,
        )

    return {
        "success": True,
        "retry_scope": "document",
        "announcement_id": target.announcement_id,
        "document_id": target.document_id,
        "start_stage": target.stage,
        "result": result,
    }


def retry_error_from_stage(*, error_id: int) -> dict[str, Any]:
    """
    Retry only the announcement/document linked to an ErrorLog.

    Download failures retry only the failed attachment in the selected
    announcement. Later failures resume only the linked document from the
    recorded worker stage while reusing successful earlier-stage artifacts.
    """

    target = _claim_retry(error_id)

    try:
        result = (
            _retry_download_document(target)
            if _is_download_retry(target)
            else _retry_document(target)
        )
    except Exception as exc:
        _finish_retry(
            error_id,
            succeeded=False,
            message=f"{target.stage} 단계 재시도 실패: {exc}",
        )
        raise

    _finish_retry(
        error_id,
        succeeded=True,
        message=(
            f"{target.stage} 단계 재시도 성공 "
            f"({result['retry_scope']} 단위)"
        ),
    )
    return result
