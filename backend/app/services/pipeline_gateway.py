from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from backend.app.db.session import engine

LOGGER = logging.getLogger(__name__)
# 이전 증분 스케줄러와도 잠금 범위를 공유한다(배포 전환 중 동시 실행 방지).
COLLECTION_ADVISORY_LOCK_ID = 615_120_315


class PipelineUnavailableError(RuntimeError):
    pass


class CollectionAlreadyRunningError(RuntimeError):
    pass


def _load_callable(env_name: str) -> Callable[..., Any]:
    """
    파이프라인 내부 코드를 API 계층에서 직접 구현하지 않고,
    환경변수로 지정한 기존 실행 함수를 호출한다.

    예:
      COLLECTION_RUNNER=crawler.runner:collect
      ANNOUNCEMENT_RECOLLECTOR=crawler.runner:recollect
      DOCUMENT_REPROCESSOR=run_pipeline:reprocess_document
      ERROR_RETRY_RUNNER=run_pipeline:retry_from_stage
    """
    target = os.getenv(env_name, "").strip()
    if not target or ":" not in target:
        raise PipelineUnavailableError(
            f"{env_name} 환경변수가 설정되지 않았습니다. "
            "실제 파이프라인 실행 함수 경로를 연결해 주세요."
        )

    module_name, function_name = target.split(":", 1)

    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
    except (ImportError, AttributeError) as exc:
        raise PipelineUnavailableError(
            f"{env_name}에 지정된 함수 {target}을 불러오지 못했습니다."
        ) from exc

    return function


def collect_announcements():
    """전체 수집부터 publish까지 예약/수동 실행이 같은 DB 잠금을 사용한다."""
    runner = _load_callable("COLLECTION_RUNNER")
    # 세션 잠금은 같은 연결에서 해제해야 한다. 장시간 idle transaction은 피한다.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        params = {"lock_id": COLLECTION_ADVISORY_LOCK_ID}
        try:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"), params
            )
        except Exception:
            connection.invalidate()
            raise

        if not acquired:
            raise CollectionAlreadyRunningError("전체 공고 수집이 이미 실행 중입니다.")

        try:
            return runner()
        finally:
            try:
                released = connection.scalar(
                    text("SELECT pg_advisory_unlock(:lock_id)"), params
                )
                if not released:
                    LOGGER.error("Collection advisory lock was not held at release")
                    connection.invalidate()
            except Exception:
                # 잠금이 남은 연결을 풀에 반환하지 않고 원래 실행 결과는 보존한다.
                LOGGER.exception("Failed to release collection advisory lock")
                connection.invalidate()


def recollect_announcement(announcement_id: int):
    return _load_callable("ANNOUNCEMENT_RECOLLECTOR")(
        announcement_id=announcement_id
    )


def _get_document_processing_runtime() -> str:
    runtime = os.getenv(
        "DOCUMENT_PROCESSING_RUNTIME",
        "worker_http",
    ).strip().lower()

    if runtime not in {
        "legacy",
        "worker_http",
    }:
        raise PipelineUnavailableError(
            "DOCUMENT_PROCESSING_RUNTIME must be "
            "'legacy' or 'worker_http'. "
            f"Current value: {runtime or '<empty>'}"
        )

    return runtime


def reprocess_document(
    document_id: int,
    start_stage: str | None = None,
):
    runtime = _get_document_processing_runtime()

    if runtime == "legacy":
        if start_stage:
            raise PipelineUnavailableError(
                "실패 단계부터 문서 재시도하려면 "
                "DOCUMENT_PROCESSING_RUNTIME=worker_http 설정이 필요합니다."
            )
        runner = _load_callable("DOCUMENT_REPROCESSOR")
        return runner(document_id=document_id)

    from backend.app.services import (
        document_processing_service,
    )

    if start_stage:
        return document_processing_service.process_document_with_worker(
            document_id,
            start_stage=start_stage,
        )

    return document_processing_service.process_document_with_worker(
        document_id
    )


def retry_error(
    error_id: int,
):
    target = os.getenv("ERROR_RETRY_RUNNER", "").strip()

    if target:
        return _load_callable("ERROR_RETRY_RUNNER")(
            error_id=error_id,
        )

    from backend.app.services.error_retry_service import (
        retry_error_from_stage,
    )

    return retry_error_from_stage(error_id=error_id)
