from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
)

from backend.app.clients.http_json import (
    InternalServiceResponseError,
    post_json,
)
from backend.app.core.config import settings


class DocumentSource(BaseModel):
    """Source document information sent to the worker."""

    filename: str = Field(min_length=1)
    format: Literal["hwp", "hwpx"]
    storage_path: str = Field(min_length=1)


class DocumentWorkerSummary(BaseModel):
    """Document worker processing summary."""

    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)


class KeyInformationPayload(BaseModel):
    """
    Required seven key-information fields.

    A field with status="not_found" is still a valid result.
    Missing or malformed fields are contract violations.
    """

    application_period: dict[str, Any]
    eligibility: dict[str, Any]
    supply_information: dict[str, Any]
    income_asset_criteria: dict[str, Any]
    required_documents: dict[str, Any]
    winner_announcement: dict[str, Any]
    contact_information: dict[str, Any]


class DocumentWorkerResponse(BaseModel):
    """Successful document worker response contract."""

    document_id: int = Field(gt=0)
    announcement_id: int = Field(gt=0)
    announcement_key: str = Field(min_length=1)
    status: Literal["completed"]
    document_format: Literal["hwp", "hwpx"]
    output_path: str = Field(min_length=1)
    summary: DocumentWorkerSummary
    key_information: KeyInformationPayload


def process_document(
    *,
    document_id: int,
    announcement_id: int,
    announcement_key: str,
    filename: str,
    document_format: Literal["hwp", "hwpx"],
    storage_path: str,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
) -> DocumentWorkerResponse:
    """Call the document worker processing API."""

    if (
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id <= 0
    ):
        raise ValueError(
            "document_id must be a positive integer."
        )

    if (
        isinstance(announcement_id, bool)
        or not isinstance(announcement_id, int)
        or announcement_id <= 0
    ):
        raise ValueError(
            "announcement_id must be a positive integer."
        )

    normalized_announcement_key = str(
        announcement_key or ""
    ).strip()

    if not normalized_announcement_key:
        raise ValueError(
            "announcement_key must not be empty."
        )

    source = DocumentSource(
        filename=str(filename or "").strip(),
        format=document_format,
        storage_path=str(storage_path or "").strip(),
    )

    service_base_url = (
        base_url
        if base_url is not None
        else settings.document_worker_base_url
    )

    service_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.document_worker_timeout_seconds
    )

    endpoint = (
        f"{service_base_url.rstrip('/')}"
        f"/v1/documents/{document_id}/process"
    )

    payload = post_json(
        url=endpoint,
        payload={
            "announcement_id": announcement_id,
            "announcement_key": (
                normalized_announcement_key
            ),
            "source": source.model_dump(),
        },
        timeout_seconds=service_timeout,
    )

    try:
        return DocumentWorkerResponse.model_validate(
            payload
        )
    except ValidationError as exc:
        raise InternalServiceResponseError(
            "Document worker response does not match "
            "the API contract."
        ) from exc
