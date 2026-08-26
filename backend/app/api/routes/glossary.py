from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_admin
from backend.app.db.session import get_db
from backend.app.schemas.glossary import (
    GlossaryAdminItem,
    GlossaryAdminListResponse,
    GlossaryCreateRequest,
    GlossaryPublicItem,
    GlossaryStatusUpdateRequest,
    GlossaryUpdateRequest,
)
from backend.app.services.glossary_service import (
    DuplicateGlossaryTermError,
    create_glossary,
    delete_glossary,
    list_admin_glossary,
    list_public_glossary,
    update_glossary,
    update_glossary_status,
)


public_router = APIRouter(
    prefix="/glossary",
    tags=["Glossary"],
)

admin_router = APIRouter(
    prefix="/admin/glossary",
    tags=["Admin Glossary"],
    dependencies=[Depends(get_current_admin)],
)


@public_router.get(
    "",
    response_model=list[GlossaryPublicItem],
)
def get_public_glossary(
    db: Session = Depends(get_db),
) -> list[GlossaryPublicItem]:
    try:
        return list_public_glossary(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="용어 사전을 조회하지 못했습니다.",
        ) from exc


@admin_router.get(
    "",
    response_model=GlossaryAdminListResponse,
)
def get_admin_glossary(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> GlossaryAdminListResponse:
    try:
        return list_admin_glossary(
            db=db,
            page=page,
            size=size,
            search=search,
            category=category,
            is_active=is_active,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 용어 목록을 조회하지 못했습니다.",
        ) from exc


@admin_router.post(
    "",
    response_model=GlossaryAdminItem,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_glossary(
    request: GlossaryCreateRequest,
    db: Session = Depends(get_db),
) -> GlossaryAdminItem:
    try:
        return create_glossary(db, request)
    except DuplicateGlossaryTermError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 용어입니다.",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="용어를 등록하지 못했습니다.",
        ) from exc


@admin_router.put(
    "/{glossary_id}",
    response_model=GlossaryAdminItem,
)
def update_admin_glossary(
    glossary_id: int,
    request: GlossaryUpdateRequest,
    db: Session = Depends(get_db),
) -> GlossaryAdminItem:
    try:
        result = update_glossary(
            db=db,
            glossary_id=glossary_id,
            request=request,
        )
    except DuplicateGlossaryTermError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 용어입니다.",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="용어를 수정하지 못했습니다.",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="용어를 찾을 수 없습니다.",
        )

    return result


@admin_router.patch(
    "/{glossary_id}/status",
    response_model=GlossaryAdminItem,
)
def update_admin_glossary_status(
    glossary_id: int,
    request: GlossaryStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> GlossaryAdminItem:
    try:
        result = update_glossary_status(
            db=db,
            glossary_id=glossary_id,
            request=request,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="용어 상태를 변경하지 못했습니다.",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="용어를 찾을 수 없습니다.",
        )

    return result


@admin_router.delete(
    "/{glossary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_admin_glossary(
    glossary_id: int,
    db: Session = Depends(get_db),
) -> Response:
    try:
        deleted = delete_glossary(
            db=db,
            glossary_id=glossary_id,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="용어를 삭제하지 못했습니다.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="용어를 찾을 수 없습니다.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
