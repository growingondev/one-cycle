from __future__ import annotations

import importlib
import os
from typing import Any, Callable


class PipelineUnavailableError(RuntimeError):
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
    return _load_callable("COLLECTION_RUNNER")()


def recollect_announcement(announcement_id: int):
    return _load_callable("ANNOUNCEMENT_RECOLLECTOR")(
        announcement_id=announcement_id
    )


def reprocess_document(document_id: int):
    return _load_callable("DOCUMENT_REPROCESSOR")(
        document_id=document_id
    )


def retry_error(
    error_id: str,
    document_id: int,
    stage: str | None,
):
    return _load_callable("ERROR_RETRY_RUNNER")(
        error_id=error_id,
        document_id=document_id,
        start_stage=stage,
    )
