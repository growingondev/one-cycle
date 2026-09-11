from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from backend.app.core.config import Settings


class TokenError(RuntimeError):
    pass


class AuthConfigurationError(RuntimeError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _get_secret() -> str:
    secret = Settings().admin_jwt_secret.strip()
    if not secret:
        raise AuthConfigurationError(
            "ADMIN_JWT_SECRET 환경변수가 설정되지 않았습니다."
        )
    return secret


def authenticate_admin(
    admin_id: str,
    password: str,
) -> dict[str, str] | None:
    """
    현재 DB 구조에는 admin_users 테이블이 없으므로 MVP에서는 환경변수로 검증한다.

    ADMIN_ID, ADMIN_PASSWORD를 반드시 .env에 설정한다.
    추후 관리자 테이블이 추가되면 이 함수 내부만 DB 인증으로 교체한다.
    """
    settings = Settings()
    expected_id = settings.admin_id.strip()
    expected_password = settings.admin_password

    if not expected_id or not expected_password:
        raise AuthConfigurationError(
            "ADMIN_ID 또는 ADMIN_PASSWORD 환경변수가 설정되지 않았습니다."
        )

    id_ok = hmac.compare_digest(admin_id, expected_id)
    password_ok = hmac.compare_digest(password, expected_password)

    if not (id_ok and password_ok):
        return None

    return {
        "admin_id": expected_id,
        "role": "admin",
    }


def create_admin_token(admin_id: str) -> str:
    now = int(time.time())
    ttl = Settings().admin_jwt_expire_seconds

    header = {
        "alg": "HS256",
        "typ": "JWT",
    }
    payload = {
        "sub": admin_id,
        "role": "admin",
        "iat": now,
        "exp": now + ttl,
    }

    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        _get_secret().encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    return (
        f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"
    )


def verify_admin_token(token: str) -> dict[str, str]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise TokenError("유효하지 않은 관리자 인증 토큰입니다.") from exc

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        _get_secret().encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    try:
        actual_signature = _b64url_decode(encoded_signature)
    except Exception as exc:
        raise TokenError("유효하지 않은 관리자 인증 토큰입니다.") from exc

    if not hmac.compare_digest(actual_signature, expected_signature):
        raise TokenError("관리자 인증 토큰 서명이 올바르지 않습니다.")

    try:
        payload: dict[str, Any] = json.loads(
            _b64url_decode(encoded_payload).decode("utf-8")
        )
    except Exception as exc:
        raise TokenError("관리자 인증 토큰을 해석할 수 없습니다.") from exc

    if payload.get("role") != "admin":
        raise TokenError("관리자 권한이 없습니다.")

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        raise TokenError("관리자 인증 토큰이 만료되었습니다.")

    admin_id = payload.get("sub")
    if not isinstance(admin_id, str) or not admin_id:
        raise TokenError("관리자 인증 정보가 올바르지 않습니다.")

    return {
        "admin_id": admin_id,
        "role": "admin",
    }


def get_auth_cookie_options() -> dict[str, Any]:
    settings = Settings()
    return {
        "name": settings.admin_cookie_name,
        "secure": settings.admin_cookie_secure,
        "samesite": settings.admin_cookie_samesite,
        "max_age": settings.admin_jwt_expire_seconds,
    }
