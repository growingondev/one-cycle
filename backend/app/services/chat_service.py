from __future__ import annotations

import importlib
import os
from typing import Any

from backend.app.clients import rag_client
from backend.app.clients.http_json import (
    InternalServiceClientError,
)
from backend.app.schemas.chat import ChatResponse


class RagServiceUnavailableError(RuntimeError):
    pass


def _load_answer_question():
    """
    Load the legacy direct-call RAG function.

    Example:
      RAG_ANSWER_FUNCTION=rag.service:answer_question
    """
    target = os.getenv(
        "RAG_ANSWER_FUNCTION",
        "",
    ).strip()

    if not target or ":" not in target:
        raise RagServiceUnavailableError(
            "RAG_ANSWER_FUNCTION is not configured."
        )

    module_name, function_name = target.split(
        ":",
        1,
    )

    try:
        module = importlib.import_module(
            module_name
        )
        function = getattr(
            module,
            function_name,
        )
    except (
        ImportError,
        AttributeError,
    ) as exc:
        raise RagServiceUnavailableError(
            f"Failed to load RAG function: {target}"
        ) from exc

    return function


def _get_rag_runtime() -> str:
    runtime = os.getenv(
        "RAG_RUNTIME",
        "legacy",
    ).strip().lower()

    if runtime not in {
        "legacy",
        "rag_http",
    }:
        raise RagServiceUnavailableError(
            "RAG_RUNTIME must be "
            "'legacy' or 'rag_http'. "
            f"Current value: {runtime or '<empty>'}"
        )

    return runtime


def _convert_rag_http_response(
    response: rag_client.RagAnswerResponse,
) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "answer": response.answer,
            "grounded": response.grounded,
            "evidence": [
                {
                    "chunkId": item.chunk_id,
                    "sectionTitle": (
                        item.section_title
                    ),
                    "content": item.content,
                    "score": item.score,
                }
                for item in response.evidence
            ],
        }
    )


def _answer_question_via_legacy(
    *,
    announcement_id: int,
    question: str,
) -> ChatResponse:
    answer_question = (
        _load_answer_question()
    )

    result: Any = answer_question(
        announcement_id=announcement_id,
        question=question,
    )

    if isinstance(
        result,
        ChatResponse,
    ):
        return result

    if isinstance(
        result,
        dict,
    ):
        return ChatResponse.model_validate(
            result
        )

    raise RagServiceUnavailableError(
        "RAG answer_question() returned "
        "an unsupported response format."
    )


def _answer_question_via_http(
    *,
    announcement_id: int,
    question: str,
) -> ChatResponse:
    try:
        response = rag_client.answer_question(
            announcement_id=announcement_id,
            question=question,
        )
    except InternalServiceClientError as exc:
        raise RagServiceUnavailableError(
            str(exc)
        ) from exc

    return _convert_rag_http_response(
        response
    )


def answer_question_via_rag(
    announcement_id: int,
    question: str,
) -> ChatResponse:
    runtime = _get_rag_runtime()

    if runtime == "legacy":
        return _answer_question_via_legacy(
            announcement_id=announcement_id,
            question=question,
        )

    return _answer_question_via_http(
        announcement_id=announcement_id,
        question=question,
    )
