from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.rag.schemas import RAGAnswerRequest, RAGAnswerResponse
from services.rag.service import RAGServiceError, answer_question


app = FastAPI(
    title="DDOKBOT RAG Service",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "RAG_INVALID_REQUEST",
                "message": str(exc),
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.post(
    "/v1/rag/answer",
    response_model=RAGAnswerResponse,
)
def rag_answer(
    request: RAGAnswerRequest,
) -> RAGAnswerResponse | JSONResponse:
    try:
        return answer_question(
            announcement_id=request.announcement_id,
            question=request.question,
        )

    except RAGServiceError as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "RAG_SERVICE_ERROR",
                    "message": str(exc),
                }
            },
        )