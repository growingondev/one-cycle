from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from document_worker.api.schemas import (
    DocumentProcessRequest,
    DocumentProcessResponse,
)
from document_worker.service import (
    DocumentWorkerServiceError,
    process_document,
)


router = APIRouter()


@router.post(
    "/v1/documents/{document_id}/process",
    response_model=DocumentProcessResponse,
)
def process_document_endpoint(
    document_id: int,
    request: DocumentProcessRequest,
):
    """
    Backend가 호출하는 Document Worker API.

    document_id:
        URL Path Parameter

    나머지 Processing Context:
        JSON Request Body
    """

    if document_id <= 0:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": (
                        "DOCUMENT_REQUEST_INVALID"
                    ),
                    "message": (
                        "document_id는 "
                        "1 이상의 정수여야 합니다."
                    ),
                }
            },
        )

    try:
        return process_document(
            document_id=document_id,
            request=request,
        )

    except DocumentWorkerServiceError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.error_code,
                    "message": error.message,
                }
            },
        )

    except NotImplementedError as error:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "code": (
                        "DOCUMENT_PROCESSING_"
                        "NOT_IMPLEMENTED"
                    ),
                    "message": str(error),
                }
            },
        )