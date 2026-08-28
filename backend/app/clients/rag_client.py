from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.clients.http_json import (
    InternalServiceResponseError,
    post_json,
)
from backend.app.core.config import settings


class RagEvidence(BaseModel):
    """Internal RAG evidence contract."""

    chunk_id: str | int
    section_title: str | None = None
    content: str
    score: float | None = None


class RagAnswerResponse(BaseModel):
    """Response contract for RAG /v1/rag/answer."""

    result: Literal[
        "grounded",
        "no_evidence",
        "unsupported",
    ]
    answer: str
    grounded: bool
    evidence: list[RagEvidence] = Field(
        default_factory=list
    )


def answer_question(
    *,
    announcement_id: int,
    question: str,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
) -> RagAnswerResponse:
    """Send a question to the RAG service."""

    if (
        isinstance(announcement_id, bool)
        or not isinstance(announcement_id, int)
        or announcement_id <= 0
    ):
        raise ValueError(
            "announcement_id must be a positive integer."
        )

    normalized_question = str(
        question or ""
    ).strip()

    if not normalized_question:
        raise ValueError(
            "question must not be empty."
        )

    service_base_url = (
        base_url
        if base_url is not None
        else settings.rag_service_base_url
    )

    service_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.rag_service_timeout_seconds
    )

    endpoint = (
        f"{service_base_url.rstrip('/')}"
        "/v1/rag/answer"
    )

    payload = post_json(
        url=endpoint,
        payload={
            "announcement_id": announcement_id,
            "question": normalized_question,
        },
        timeout_seconds=service_timeout,
    )

    try:
        return RagAnswerResponse.model_validate(
            payload
        )
    except ValidationError as exc:
        raise InternalServiceResponseError(
            "RAG service response does not match "
            "the API contract."
        ) from exc
