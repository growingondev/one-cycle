from __future__ import annotations

from typing import Any

from backend.app.services.collection_service import (
    collect_and_persist,
    recollect_and_persist,
)
from backend.app.services.error_log_service import record_error
from backend.app.services.pipeline_gateway import (
    PipelineUnavailableError,
    reprocess_document,
)


STAGE_ERROR_TYPES = {
    "prepare": "parsing",
    "format_detection": "parsing",
    "parser": "parsing",
    "normalizer": "normalizing",
    "structure": "structuring",
    "verification": "verification",
    "chunking": "chunking",
    "embedding": "embedding",
    "persistence": "database",
    "key_information": "database",
    "activation": "database",
}


def _error_type_for_stage(stage: str) -> str:
    return STAGE_ERROR_TYPES.get(
        stage,
        "database",
    )


def process_document_ids(
    document_ids: list[int],
) -> dict[str, Any]:
    """
    DB에 저장된 Document를 문서 처리 callable로 전달한다.

    실패 결과는 Backend ErrorLog에 기록한다.
    """

    results: list[dict[str, Any]] = []
    error_ids: list[int] = []

    success_count = 0
    failed_count = 0

    for document_id in document_ids:
        try:
            result = reprocess_document(
                document_id
            )

        except PipelineUnavailableError:
            raise

        except Exception as exc:
            error_result = record_error(
                error_type="database",
                stage="integration",
                error_code=(
                    "DOCUMENT_REPROCESS_UNEXPECTED_ERROR"
                ),
                message=str(exc),
                document_id=document_id,
            )

            error_id = error_result.get("error_id")

            if error_id is not None:
                error_ids.append(
                    int(error_id)
                )

            failed_count += 1

            results.append(
                {
                    "success": False,
                    "document_id": document_id,
                    "stage": "integration",
                    "error_code": (
                        "DOCUMENT_REPROCESS_UNEXPECTED_ERROR"
                    ),
                    "message": str(exc),
                }
            )

            continue

        if not isinstance(result, dict):
            message = (
                "Document reprocessor 반환값은 "
                "dict여야 합니다."
            )

            error_result = record_error(
                error_type="database",
                stage="integration",
                error_code=(
                    "INVALID_DOCUMENT_REPROCESS_RESULT"
                ),
                message=message,
                document_id=document_id,
            )

            error_id = error_result.get("error_id")

            if error_id is not None:
                error_ids.append(
                    int(error_id)
                )

            failed_count += 1

            results.append(
                {
                    "success": False,
                    "document_id": document_id,
                    "stage": "integration",
                    "error_code": (
                        "INVALID_DOCUMENT_REPROCESS_RESULT"
                    ),
                    "message": message,
                }
            )

            continue

        results.append(result)

        if result.get("success") is True:
            success_count += 1
            continue

        failed_count += 1

        stage = str(
            result.get("stage")
            or "integration"
        ).strip()

        error_code = (
            str(
                result.get("error_code")
                or ""
            ).strip()
            or None
        )

        message = str(
            result.get("message")
            or "문서 처리에 실패했습니다."
        )

        error_result = record_error(
            error_type=_error_type_for_stage(
                stage
            ),
            stage=stage,
            error_code=error_code,
            message=message,
            document_id=document_id,
        )

        error_id = error_result.get("error_id")

        if error_id is not None:
            error_ids.append(
                int(error_id)
            )

    return {
        "requested_count": len(
            document_ids
        ),
        "success_count": success_count,
        "failed_count": failed_count,
        "error_ids": error_ids,
        "results": results,
    }


def collect_persist_and_process() -> dict[str, Any]:
    """
    전체 수집 → DB 저장 → 신규 Document 처리.
    """

    persistence = collect_and_persist()

    processing = process_document_ids(
        persistence.get(
            "document_ids",
            [],
        )
    )

    return {
        **persistence,
        "document_processing":
            processing,
    }


def recollect_persist_and_process(
    *,
    announcement_id: int,
) -> dict[str, Any]:
    """
    개별 공고 재수집 → DB 저장 → 새 Document만 처리.
    """

    persistence = recollect_and_persist(
        announcement_id=announcement_id
    )

    processing = process_document_ids(
        persistence.get(
            "new_document_ids",
            [],
        )
    )

    return {
        **persistence,
        "document_processing":
            processing,
    }