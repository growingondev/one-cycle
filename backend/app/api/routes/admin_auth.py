from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.app.api.dependencies import get_current_admin
from backend.app.schemas.admin_auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLogoutResponse,
    AdminMeResponse,
)
from backend.app.services.admin_auth_service import (
    AuthConfigurationError,
    authenticate_admin,
    create_admin_token,
    get_auth_cookie_options,
)

router = APIRouter(
    prefix="/admin/auth",
    tags=["Admin Auth"],
)


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    payload: AdminLoginRequest,
    response: Response,
) -> AdminLoginResponse:
    """관리자 ID/PW를 검증하고 JWT를 HttpOnly Cookie에 저장한다."""
    try:
        admin = authenticate_admin(payload.admin_id, payload.password)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 ID 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_admin_token(admin["admin_id"])
    cookie = get_auth_cookie_options()

    response.set_cookie(
        key=cookie["name"],
        value=token,
        httponly=True,
        secure=cookie["secure"],
        samesite=cookie["samesite"],
        max_age=cookie["max_age"],
        path="/",
    )

    return AdminLoginResponse(
        authenticated=True,
        admin_id=admin["admin_id"],
        role="admin",
    )


@router.get(
    "/me",
    response_model=AdminMeResponse,
)
def me(
    current_admin: dict[str, str] = Depends(get_current_admin),
) -> AdminMeResponse:
    """현재 로그인한 관리자 정보를 반환한다."""
    return AdminMeResponse(
        authenticated=True,
        admin_id=current_admin["admin_id"],
        role=current_admin["role"],
    )


@router.post(
    "/logout",
    response_model=AdminLogoutResponse,
)
def logout(response: Response) -> AdminLogoutResponse:
    """관리자 인증 Cookie를 삭제한다."""
    cookie = get_auth_cookie_options()
    response.delete_cookie(
        key=cookie["name"],
        path="/",
    )
    return AdminLogoutResponse(success=True)
