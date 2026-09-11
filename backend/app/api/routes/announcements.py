from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.announcement import (
    AnnouncementDetailResponse,
    AnnouncementListResponse,
)
from backend.app.services.announcement_service import (
    get_active_announcement,
    get_active_announcement_download_info,
    list_active_announcements,
)

router = APIRouter(
    prefix="/announcements",
    tags=["Announcements"],
)


@router.get(
    "",
    response_model=AnnouncementListResponse,
)
def get_announcements(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    region: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    sort_order: str = Query(
        default="latest",
        alias="sort",
        pattern="^(latest|oldest)$",
    ),
    db: Session = Depends(get_db),
) -> AnnouncementListResponse:
    try:
        return list_active_announcements(
            db=db,
            page=page,
            size=size,
            search=search,
            region=region,
            status_filter=status_filter,
            sort_order=sort_order,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="공고 목록을 조회하지 못했습니다.",
        ) from exc


@router.get(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
)
def get_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
) -> AnnouncementDetailResponse:
    try:
        result = get_active_announcement(db, announcement_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="공고 상세 정보를 조회하지 못했습니다.",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공고를 찾을 수 없습니다.",
        )
    return result


@router.get("/{announcement_id}/download")
def download_announcement_document(
    announcement_id: int,
    db: Session = Depends(get_db),
):
    try:
        info = get_active_announcement_download_info(db, announcement_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="공고문 다운로드 정보를 조회하지 못했습니다.",
        ) from exc

    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="다운로드 가능한 공고문을 찾을 수 없습니다.",
        )
    if not info["storage_path"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="공고문 파일이 저장소에 존재하지 않습니다.",
        )

    return FileResponse(
        path=info["storage_path"],
        filename=info["filename"],
        media_type="application/octet-stream",
    )
