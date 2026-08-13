from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.chat_service import (
    RagServiceUnavailableError,
    answer_question_via_rag,
)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


@router.post(
    "",
    response_model=ChatResponse,
)
def chat(payload: ChatRequest) -> ChatResponse:
    """RAG 담당자가 제공하는 answer_question()을 호출하는 API 계약."""
    try:
        return answer_question_via_rag(
            announcement_id=payload.announcement_id,
            question=payload.question,
        )
    except RagServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
