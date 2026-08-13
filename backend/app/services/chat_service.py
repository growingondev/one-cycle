from __future__ import annotations

import importlib
import os
from typing import Any

from backend.app.schemas.chat import ChatResponse


class RagServiceUnavailableError(RuntimeError):
    pass


def _load_answer_question():
    """
    RAG 내부를 API 계층에 구현하지 않는다.

    환경변수 예:
      RAG_ANSWER_FUNCTION=rag.service:answer_question

    지정 모듈의 answer_question(announcement_id, question)을 호출한다.
    """
    target = os.getenv("RAG_ANSWER_FUNCTION", "").strip()
    if not target or ":" not in target:
        raise RagServiceUnavailableError(
            "RAG_ANSWER_FUNCTION이 설정되지 않았습니다. "
            "RAG 담당자의 answer_question() 함수 경로를 연결해 주세요."
        )

    module_name, function_name = target.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
    except (ImportError, AttributeError) as exc:
        raise RagServiceUnavailableError(
            f"RAG 함수 {target}을 불러오지 못했습니다."
        ) from exc

    return function


def answer_question_via_rag(
    announcement_id: int,
    question: str,
) -> ChatResponse:
    answer_question = _load_answer_question()

    result: Any = answer_question(
        announcement_id=announcement_id,
        question=question,
    )

    if isinstance(result, ChatResponse):
        return result
    if isinstance(result, dict):
        return ChatResponse.model_validate(result)

    raise RagServiceUnavailableError(
        "RAG answer_question() 반환 형식이 API 계약과 맞지 않습니다."
    )
