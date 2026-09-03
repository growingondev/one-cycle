from __future__ import annotations

from typing import Any

from backend.app.clients import document_worker_client
from backend.app.clients.document_worker_client import (
    DocumentWorkerResponse,
)
from backend.app.clients.http_json import (
    InternalServiceHTTPError,
    InternalServiceResponseError,
)
from backend.app.services.key_information_service import (
    upsert_key_information,
)
from backend.app.services.pipeline_persistence import (
    activate_processing_run,
    get_registered_document_context,
    mark_processing_run_failed,
    persist_document_outputs,
)


SUPPORTED_DOCUMENT_FORMATS = {
    "hwp",
    "hwpx",
}


WORKER_ERROR_STAGES = {
    "DOCUMENT_FORMAT_VALIDATION_FAILED": "format_detection",
    "DOCUMENT_PARSE_FAILED": "parser",
    "DOCUMENT_NORMALIZE_FAILED": "normalizer",
    "DOCUMENT_STRUCTURE_FAILED": "structure",
    "DOCUMENT_VERIFICATION_FAILED": "verification",
    "DOCUMENT_CHUNKING_FAILED": "chunking",
    "DOCUMENT_EMBEDDING_INPUT_FAILED": "embedding",
    "DOCUMENT_EMBEDDING_SERVICE_FAILED": "embedding",
    "DOCUMENT_EMBEDDING_ARTIFACT_FAILED": "embedding",
    "DOCUMENT_KEY_INFORMATION_FAILED": "key_information_extraction",
}


def _validate_document_id(document_id: int) -> None:
    if (
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id <= 0
    ):
        raise ValueError(
            "document_id must be a positive integer."
        )


def _normalize_worker_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    announcement_key = str(
        context.get("announcement_key") or ""
    ).strip()

    if not announcement_key:
        raise RuntimeError(
            "Document context is missing announcement_key."
        )

    announcement_id = context.get(
        "announcement_db_id"
    )

    if (
        isinstance(announcement_id, bool)
        or not isinstance(announcement_id, int)
        or announcement_id <= 0
    ):
        raise RuntimeError(
            "Document context has an invalid "
            "announcement_db_id."
        )

    document_id = context.get(
        "document_db_id"
    )

    if (
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id <= 0
    ):
        raise RuntimeError(
            "Document context has an invalid "
            "document_db_id."
        )

    filename = str(
        context.get("filename") or ""
    ).strip()

    if not filename:
        raise RuntimeError(
            "Document context is missing filename."
        )

    document_format = str(
        context.get("format") or ""
    ).strip().lower()

    if document_format not in SUPPORTED_DOCUMENT_FORMATS:
        raise RuntimeError(
            "Document context has an unsupported "
            f"document format: {document_format or '<empty>'}"
        )

    storage_path = str(
        context.get("storage_path") or ""
    ).strip()

    if not storage_path:
        raise RuntimeError(
            "Document context is missing storage_path."
        )

    return {
        "announcement_key": announcement_key,
        "announcement_id": announcement_id,
        "document_id": document_id,
        "filename": filename,
        "document_format": document_format,
        "storage_path": storage_path,
    }


def _validate_worker_response_context(
    *,
    response: DocumentWorkerResponse,
    context: dict[str, Any],
) -> None:
    mismatches: list[str] = []

    if response.document_id != context["document_id"]:
        mismatches.append(
            "document_id"
        )

    if (
        response.announcement_id
        != context["announcement_id"]
    ):
        mismatches.append(
            "announcement_id"
        )

    if (
        response.announcement_key
        != context["announcement_key"]
    ):
        mismatches.append(
            "announcement_key"
        )

    if (
        response.document_format
        != context["document_format"]
    ):
        mismatches.append(
            "document_format"
        )

    if mismatches:
        raise InternalServiceResponseError(
            "Document worker response does not match "
            "the requested document context: "
            + ", ".join(mismatches)
        )


def process_document_via_worker(
    document_id: int,
    start_stage: str | None = None,
) -> DocumentWorkerResponse:
    """
    Request document processing from Document Worker.

    This function only establishes the Backend-to-Worker
    HTTP boundary. Artifact persistence, key-information
    persistence, and ProcessingRun activation remain
    separate Backend responsibilities.
    """

    _validate_document_id(
        document_id
    )

    raw_context = get_registered_document_context(
        document_id
    )

    context = _normalize_worker_context(
        raw_context
    )

    if context["document_id"] != document_id:
        raise RuntimeError(
            "Requested document_id does not match "
            "the registered Document context."
        )

    worker_kwargs: dict[str, Any] = {
        "document_id": context["document_id"],
        "announcement_id": context["announcement_id"],
        "announcement_key": context["announcement_key"],
        "filename": context["filename"],
        "document_format": context["document_format"],
        "storage_path": context["storage_path"],
    }
    if start_stage:
        worker_kwargs["start_stage"] = start_stage

    response = document_worker_client.process_document(
        **worker_kwargs,
    )

    _validate_worker_response_context(
        response=response,
        context=context,
    )

    return response


def _get_processing_run_id(
    persistence: dict[str, Any],
) -> int:
    processing_run_id = persistence.get(
        "processing_run_id"
    )

    if (
        isinstance(processing_run_id, bool)
        or not isinstance(processing_run_id, int)
        or processing_run_id <= 0
    ):
        raise RuntimeError(
            "Artifact persistence did not return a valid "
            "processing_run_id."
        )

    return processing_run_id


def _validate_persistence_summary(
    *,
    response: DocumentWorkerResponse,
    persistence: dict[str, Any],
) -> None:
    written_chunks = persistence.get(
        "written_chunks"
    )
    written_embeddings = persistence.get(
        "written_embeddings"
    )

    if (
        written_chunks
        != response.summary.chunk_count
    ):
        raise RuntimeError(
            "Persisted Chunk count does not match "
            "the Document Worker summary. "
            f"worker={response.summary.chunk_count}, "
            f"persisted={written_chunks}"
        )

    if (
        written_embeddings
        != response.summary.embedding_count
    ):
        raise RuntimeError(
            "Persisted Embedding count does not match "
            "the Document Worker summary. "
            f"worker={response.summary.embedding_count}, "
            f"persisted={written_embeddings}"
        )


def _record_processing_failure(
    *,
    processing_run_id: int,
    stage: str,
    error_code: str,
    original_error: Exception,
) -> None:
    try:
        mark_processing_run_failed(
            processing_run_id,
            stage=stage,
            error_code=error_code,
            error_message=str(original_error),
            exit_code=1,
        )
    except Exception as status_error:
        raise RuntimeError(
            "Backend processing failed and "
            "ProcessingRun failure recording also failed. "
            f"original_error={original_error}; "
            f"status_error={status_error}"
        ) from status_error


def finalize_document_worker_result(
    *,
    document_id: int,
    response: DocumentWorkerResponse,
) -> dict[str, Any]:
    """
    Persist a successful Document Worker result in Backend.

    Order:
      Artifact validation / persistence
      -> Key Information persistence
      -> ProcessingRun activation
    """

    try:
        persistence = persist_document_outputs(
            document_id,
            output_root_path=response.output_path,
        )
    except Exception as error:
        raise RuntimeError(
            "Document Worker artifacts could not be "
            f"persisted: {error}"
        ) from error

    processing_run_id = _get_processing_run_id(
        persistence
    )

    try:
        _validate_persistence_summary(
            response=response,
            persistence=persistence,
        )
    except Exception as error:
        _record_processing_failure(
            processing_run_id=processing_run_id,
            stage="persistence",
            error_code=(
                "WORKER_PERSISTENCE_SUMMARY_MISMATCH"
            ),
            original_error=error,
        )
        raise

    key_information = (
        response.key_information.model_dump()
    )

    try:
        key_information_result = (
            upsert_key_information(
                announcement_id=(
                    response.announcement_id
                ),
                source_processing_run_id=(
                    processing_run_id
                ),
                application_period=(
                    key_information[
                        "application_period"
                    ]
                ),
                eligibility=(
                    key_information[
                        "eligibility"
                    ]
                ),
                supply_information=(
                    key_information[
                        "supply_information"
                    ]
                ),
                income_asset_criteria=(
                    key_information[
                        "income_asset_criteria"
                    ]
                ),
                required_documents=(
                    key_information[
                        "required_documents"
                    ]
                ),
                winner_announcement=(
                    key_information[
                        "winner_announcement"
                    ]
                ),
                contact_information=(
                    key_information[
                        "contact_information"
                    ]
                ),
                extraction_status="completed",
                is_verified=False,
            )
        )
    except Exception as error:
        _record_processing_failure(
            processing_run_id=processing_run_id,
            stage="key_information",
            error_code=(
                "KEY_INFORMATION_PERSISTENCE_FAILED"
            ),
            original_error=error,
        )
        raise

    try:
        activation = activate_processing_run(
            processing_run_id
        )
    except Exception as error:
        _record_processing_failure(
            processing_run_id=processing_run_id,
            stage="activation",
            error_code=(
                "PROCESSING_RUN_ACTIVATION_FAILED"
            ),
            original_error=error,
        )
        raise

    return {
        "success": True,
        "stage": "completed",
        "document_id": response.document_id,
        "announcement_id": (
            response.announcement_id
        ),
        "announcement_key": (
            response.announcement_key
        ),
        "document_format": (
            response.document_format
        ),
        "processing_run_id": (
            processing_run_id
        ),
        "key_information_id": (
            key_information_result["id"]
        ),
        "key_information_status": (
            key_information_result[
                "extraction_status"
            ]
        ),
        "output_root": response.output_path,
        "is_active": True,
        "activation": activation,
    }


def process_document_with_worker(
    document_id: int,
    start_stage: str | None = None,
) -> dict[str, Any]:
    """
    Complete Backend orchestration for Document Worker.

    The existing MVP runtime is not switched to this
    function until the actual Worker endpoint is ready.
    """

    try:
        if start_stage:
            response = process_document_via_worker(
                document_id,
                start_stage=start_stage,
            )
        else:
            response = process_document_via_worker(document_id)
    except InternalServiceHTTPError as error:
        return {
            "success": False,
            "document_id": document_id,
            "stage": WORKER_ERROR_STAGES.get(
                error.error_code,
                "integration",
            ),
            "error_code": error.error_code,
            "message": error.message,
        }

    return finalize_document_worker_result(
        document_id=document_id,
        response=response,
    )
