from fastapi import Cookie, HTTPException, status

from backend.app.services.admin_auth_service import (
    AuthConfigurationError,
    TokenError,
    verify_admin_token,
)


def get_current_admin(
    admin_access_token: str | None = Cookie(default=None),
) -> dict[str, str]:
    """HttpOnly Cookie에 저장된 관리자 JWT를 검증한다."""
    if not admin_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 로그인이 필요합니다.",
        )

    try:
        return verify_admin_token(admin_access_token)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
