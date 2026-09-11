from __future__ import annotations

import json
from typing import Any, Mapping
from urllib import error, request
from urllib.parse import urlparse


class InternalServiceClientError(RuntimeError):
    """Base error for internal HTTP service calls."""


class InternalServiceConfigurationError(
    InternalServiceClientError
):
    """Invalid service URL or timeout configuration."""


class InternalServiceUnavailableError(
    InternalServiceClientError
):
    """Service connection failure or timeout."""


class InternalServiceResponseError(
    InternalServiceClientError
):
    """Service response does not match the expected contract."""


class InternalServiceHTTPError(
    InternalServiceClientError
):
    """Service returned an HTTP 4xx or 5xx error."""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message

        super().__init__(
            f"{status_code} {error_code}: {message}"
        )


def _validate_url(url: str) -> str:
    normalized = str(url or "").strip()

    if not normalized:
        raise InternalServiceConfigurationError(
            "Service URL is not configured."
        )

    parsed = urlparse(normalized)

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
    ):
        raise InternalServiceConfigurationError(
            f"Invalid HTTP service URL: {normalized}"
        )

    return normalized


def _parse_error_body(
    raw_body: bytes,
    *,
    fallback_code: str,
    fallback_message: str,
) -> tuple[str, str]:
    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return fallback_code, fallback_message

    if not isinstance(payload, dict):
        return fallback_code, fallback_message

    error_payload = payload.get("error")

    if isinstance(error_payload, dict):
        code = str(
            error_payload.get("code")
            or fallback_code
        ).strip()

        message = str(
            error_payload.get("message")
            or fallback_message
        ).strip()

        return (
            code or fallback_code,
            message or fallback_message,
        )

    detail = payload.get("detail")

    if isinstance(detail, dict):
        code = str(
            detail.get("error_code")
            or detail.get("code")
            or fallback_code
        ).strip()

        message = str(
            detail.get("message")
            or fallback_message
        ).strip()

        return (
            code or fallback_code,
            message or fallback_message,
        )

    if isinstance(detail, str) and detail.strip():
        return fallback_code, detail.strip()

    return fallback_code, fallback_message


def _open_json(
    *,
    http_request: request.Request,
    timeout_seconds: float,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise InternalServiceConfigurationError(
            "timeout_seconds must be greater than zero."
        )

    try:
        with request.urlopen(
            http_request,
            timeout=timeout_seconds,
        ) as response:
            raw_body = response.read()

    except error.HTTPError as exc:
        raw_body = exc.read()

        error_code, message = _parse_error_body(
            raw_body,
            fallback_code="INTERNAL_SERVICE_HTTP_ERROR",
            fallback_message=(
                "Internal service returned "
                f"HTTP {exc.code}."
            ),
        )

        raise InternalServiceHTTPError(
            status_code=exc.code,
            error_code=error_code,
            message=message,
        ) from exc

    except error.URLError as exc:
        raise InternalServiceUnavailableError(
            "Failed to connect to internal service: "
            f"{exc.reason}"
        ) from exc

    except TimeoutError as exc:
        raise InternalServiceUnavailableError(
            "Internal service request timed out: "
            f"{timeout_seconds} seconds"
        ) from exc

    except OSError as exc:
        raise InternalServiceUnavailableError(
            "Operating system error during internal "
            f"service request: {exc}"
        ) from exc

    try:
        decoded_body = raw_body.decode("utf-8")
        response_payload = json.loads(decoded_body)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise InternalServiceResponseError(
            "Internal service returned invalid JSON."
        ) from exc

    if not isinstance(response_payload, dict):
        raise InternalServiceResponseError(
            "Internal service JSON response must be an object."
        )

    return response_payload


def get_json(
    *,
    url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """GET JSON from an internal service and return an object."""

    normalized_url = _validate_url(url)

    http_request = request.Request(
        normalized_url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    return _open_json(
        http_request=http_request,
        timeout_seconds=timeout_seconds,
    )


def post_json(
    *,
    url: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    """POST JSON to an internal service and return a JSON object."""

    normalized_url = _validate_url(url)

    try:
        encoded_body = json.dumps(
            dict(payload),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InternalServiceClientError(
            "Failed to encode HTTP payload as JSON."
        ) from exc

    http_request = request.Request(
        normalized_url,
        data=encoded_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    return _open_json(
        http_request=http_request,
        timeout_seconds=timeout_seconds,
    )
