from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pipeline.embedding.embedding_generator import EmbeddingGenerationError
from services.embedding.schemas import EmbeddingRequest, EmbeddingResponse
from services.embedding.service import EmbeddingService


embedding_service = EmbeddingService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    embedding_service.load_model()

    yield

    embedding_service.unload_model()


app = FastAPI(
    title="DDOKBOT Embedding Service",
    version="1.0.0",
    lifespan=lifespan,
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
                "code": "EMBEDDING_INVALID_REQUEST",
                "message": str(exc),
            }
        },
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model_loaded": embedding_service.is_ready,
        "model": embedding_service.model_name,
    }


@app.post(
    "/v1/embeddings",
    response_model=EmbeddingResponse,
)
def create_embeddings(
    request: EmbeddingRequest,
) -> EmbeddingResponse | JSONResponse:
    if not embedding_service.is_ready:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "EMBEDDING_MODEL_UNAVAILABLE",
                    "message": "Embedding model is not loaded.",
                }
            },
        )

    try:
        return embedding_service.create_embeddings(request.items)

    except EmbeddingGenerationError as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "EMBEDDING_GENERATION_FAILED",
                    "message": str(exc),
                }
            },
        )