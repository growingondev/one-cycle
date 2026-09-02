from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_admin
from backend.app.clients.crawler_client import (
    CrawlerJobFailedError,
)
from backend.app.clients.http_json import (
    InternalServiceConfigurationError,
    InternalServiceHTTPError,
    InternalServiceResponseError,
    InternalServiceUnavailableError,
)
from backend.app.db.session import get_db
from backend.app.schemas.admin import (
    AdminAnnouncementDetail,
    AdminAnnouncementListResponse,
    AdminDocumentDetail,
    AdminDocumentListResponse,
    AdminErrorDetail,
    AdminErrorListResponse,
    AdminProcessingRunListResponse,
    ActionAcceptedResponse,
    ErrorStatusUpdateRequest,
)
from backend.app.services.admin_service import (
    get_admin_announcement,
    get_admin_document,
    get_admin_error,
    get_document_download_info,
    list_admin_announcements,
    list_admin_documents,
    list_admin_errors,
    list_processing_runs,
    update_error_status,
)
from backend.app.services.pipeline_gateway import (
    PipelineUnavailableError,
    collect_announcements,
    recollect_announcement,
    reprocess_document,
    retry_error,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_admin)],
)


def _raise_crawler_api_error(error: Exception) -> None:
    if isinstance(error, InternalServiceHTTPError):
        status_code = (
            status.HTTP_409_CONFLICT
            if error.status_code == 409
            else status.HTTP_502_BAD_GATEWAY
        )
        error_code = error.error_code
        message = error.message
    elif isinstance(error, CrawlerJobFailedError):
        status_code = status.HTTP_502_BAD_GATEWAY
        error_code = error.error_code
        message = error.message
    elif isinstance(
        error,
        (
            InternalServiceConfigurationError,
            InternalServiceUnavailableError,
        ),
    ):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        error_code = "CRAWLER_SERVICE_UNAVAILABLE"
        message = str(error)
    elif isinstance(error, InternalServiceResponseError):
        status_code = status.HTTP_502_BAD_GATEWAY
        error_code = "CRAWLER_RESPONSE_INVALID"
        message = str(error)
    else:
        raise error

    raise HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
        },
    ) from error


@router.get(
    "/announcements",
    response_model=AdminAnnouncementListResponse,
)
def admin_announcements(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    region: str | None = Query(default=None),
    announcement_status: str | None = Query(default=None),
    collection_status: str | None = Query(default=None),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return list_admin_announcements(
            db=db,
            page=page,
            size=size,
            search=search,
            region=region,
            announcement_status=announcement_status,
            collection_status=collection_status,
            created_from=created_from,
            created_to=created_to,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 공고 목록을 조회하지 못했습니다.",
        ) from exc


@router.get(
    "/announcements/{announcement_id}",
    response_model=AdminAnnouncementDetail,
)
def admin_announcement_detail(
    announcement_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = get_admin_announcement(db, announcement_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 공고 상세를 조회하지 못했습니다.",
        ) from exc

    if result is None:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return result


@router.post(
    "/announcements/collect",
    response_model=ActionAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_collection():
    try:
        result = collect_announcements()
    except PipelineUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (
        CrawlerJobFailedError,
        InternalServiceConfigurationError,
        InternalServiceHTTPError,
        InternalServiceResponseError,
        InternalServiceUnavailableError,
    ) as exc:
        _raise_crawler_api_error(exc)

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="공고 수집에 실패했습니다.",
        )

    return ActionAcceptedResponse(
        accepted=True,
        message="공고 수집 실행 요청을 전달했습니다.",
        reference=result,
    )


@router.post(
    "/announcements/{announcement_id}/recollect",
    response_model=ActionAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_recollection(announcement_id: int):
    try:
        result = recollect_announcement(announcement_id)
    except PipelineUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (
        CrawlerJobFailedError,
        InternalServiceConfigurationError,
        InternalServiceHTTPError,
        InternalServiceResponseError,
        InternalServiceUnavailableError,
    ) as exc:
        _raise_crawler_api_error(exc)
    return ActionAcceptedResponse(
        accepted=True,
        message="공고 재수집 요청을 전달했습니다.",
        reference=result,
    )


@router.get(
    "/documents",
    response_model=AdminDocumentListResponse,
)
def admin_documents(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    processing_status: str | None = Query(default=None),
    analysis_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return list_admin_documents(
            db=db,
            page=page,
            size=size,
            search=search,
            document_type=document_type,
            processing_status=processing_status,
            analysis_status=analysis_status,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(503, "관리자 문서 목록을 조회하지 못했습니다.") from exc


@router.get(
    "/documents/{document_id}",
    response_model=AdminDocumentDetail,
)
def admin_document_detail(
    document_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = get_admin_document(db, document_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "관리자 문서 상세를 조회하지 못했습니다.") from exc

    if result is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return result


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    try:
        info = get_document_download_info(db, document_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "문서 다운로드 정보를 조회하지 못했습니다.") from exc

    if info is None:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if not info["storage_path"]:
        raise HTTPException(409, "다운로드 가능한 파일 경로가 없습니다.")

    return FileResponse(
        path=info["storage_path"],
        filename=info["filename"],
        media_type="application/octet-stream",
    )


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=ActionAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_document_reprocess(document_id: int):
    try:
        result = reprocess_document(document_id)
    except PipelineUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    return ActionAcceptedResponse(
        accepted=True,
        message="문서 재처리 요청을 전달했습니다.",
        reference=result,
    )


@router.get(
    "/processing-runs",
    response_model=AdminProcessingRunListResponse,
)
def admin_processing_runs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    execution_status: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return list_processing_runs(
            db=db,
            page=page,
            size=size,
            execution_status=execution_status,
            verification_status=verification_status,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(503, "처리 이력을 조회하지 못했습니다.") from exc


@router.get(
    "/errors",
    response_model=AdminErrorListResponse,
)
def admin_errors(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    error_type: str | None = Query(default=None),
    error_status: str | None = Query(default=None, alias="status"),
    occurred_from: date | None = Query(default=None),
    occurred_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return list_admin_errors(
            db=db,
            page=page,
            size=size,
            search=search,
            error_type=error_type,
            error_status=error_status,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(503, "오류 목록을 조회하지 못했습니다.") from exc


@router.get(
    "/errors/{error_id}",
    response_model=AdminErrorDetail,
)
def admin_error_detail(
    error_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = get_admin_error(db, error_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "오류 상세를 조회하지 못했습니다.") from exc

    if result is None:
        raise HTTPException(404, "오류를 찾을 수 없습니다.")
    return result


@router.patch(
    "/errors/{error_id}/status",
    response_model=AdminErrorDetail,
)
def change_error_status(
    error_id: int,
    payload: ErrorStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        result = update_error_status(
            db=db,
            error_id=error_id,
            status_value=payload.status,
            resolution=payload.resolution,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="오류 상태를 변경하지 못했습니다.",
        ) from exc

    if result is None:
        raise HTTPException(404, "오류를 찾을 수 없습니다.")
    return result


@router.post(
    "/errors/{error_id}/retry",
    response_model=ActionAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_error_retry(
    error_id: int,
    db: Session = Depends(get_db),
):
    try:
        error = get_admin_error(db, error_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "오류 정보를 조회하지 못했습니다.") from exc

    if error is None:
        raise HTTPException(404, "오류를 찾을 수 없습니다.")

    try:
        result = retry_error(
            error_id=error_id,
            document_id=error.document_id,
            stage=error.stage,
        )
    except PipelineUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc

    return ActionAcceptedResponse(
        accepted=True,
        message=f"{error.stage or '처음'} 단계부터 재처리 요청을 전달했습니다.",
        reference=result,
    )
