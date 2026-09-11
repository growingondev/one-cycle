from __future__ import annotations

import time
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, ValidationError

from backend.app.clients.http_json import (
    InternalServiceClientError,
    InternalServiceConfigurationError,
    InternalServiceResponseError,
    InternalServiceUnavailableError,
    get_json,
    post_json,
)
from backend.app.core.config import settings

CrawlerJobState = Literal[
    "queued",
    "running",
    "completed",
    "failed",
]


class CrawlerJobAccepted(BaseModel):
    job_id: str = Field(min_length=1)
    status: CrawlerJobState


class CrawlerJobStatus(BaseModel):
    job_id: str = Field(min_length=1)
    status: CrawlerJobState
    error_code: str | None = None
    message: str | None = None


class CrawlerJobResult(CrawlerJobStatus):
    result: dict[str, Any] | None = None


class CrawlerJobFailedError(InternalServiceClientError):
    def __init__(
        self,
        *,
        job_id: str,
        error_code: str,
        message: str,
    ) -> None:
        self.job_id = job_id
        self.error_code = error_code
        self.message = message

        super().__init__(
            f"{error_code}: {message} (job_id={job_id})"
        )


class CrawlerJobTimeoutError(
    InternalServiceUnavailableError
):
    """Crawler job did not finish before the configured deadline."""


def _validate_contract(
    model_type: type[BaseModel],
    payload: dict[str, Any],
    *,
    contract_name: str,
) -> BaseModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise InternalServiceResponseError(
            f"Crawler {contract_name} response does not "
            "match the API contract."
        ) from exc


def _service_url(path: str) -> str:
    return (
        f"{settings.crawler_service_base_url.rstrip('/')}"
        f"{path}"
    )


def _validate_polling_settings() -> None:
    if settings.crawler_job_timeout_seconds <= 0:
        raise InternalServiceConfigurationError(
            "crawler_job_timeout_seconds must be greater "
            "than zero."
        )

    if settings.crawler_job_poll_interval_seconds <= 0:
        raise InternalServiceConfigurationError(
            "crawler_job_poll_interval_seconds must be "
            "greater than zero."
        )


def _raise_job_failure(status: CrawlerJobStatus) -> None:
    raise CrawlerJobFailedError(
        job_id=status.job_id,
        error_code=(
            str(status.error_code or "CRAWLER_JOB_FAILED")
            .strip()
            or "CRAWLER_JOB_FAILED"
        ),
        message=(
            str(status.message or "Crawler job failed.")
            .strip()
            or "Crawler job failed."
        ),
    )


def _wait_for_result(job_id: str) -> dict[str, Any]:
    _validate_polling_settings()

    encoded_job_id = quote(job_id, safe="")
    job_path = f"/v1/crawl-jobs/{encoded_job_id}"
    deadline = (
        time.monotonic()
        + settings.crawler_job_timeout_seconds
    )

    while True:
        status_payload = get_json(
            url=_service_url(job_path),
            timeout_seconds=(
                settings.crawler_service_timeout_seconds
            ),
        )
        status = _validate_contract(
            CrawlerJobStatus,
            status_payload,
            contract_name="job status",
        )
        assert isinstance(status, CrawlerJobStatus)

        if status.job_id != job_id:
            raise InternalServiceResponseError(
                "Crawler job status returned a different job_id."
            )

        if status.status == "failed":
            _raise_job_failure(status)

        if status.status == "completed":
            break

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise CrawlerJobTimeoutError(
                "Crawler job timed out after "
                f"{settings.crawler_job_timeout_seconds} "
                f"seconds: job_id={job_id}"
            )

        time.sleep(
            min(
                settings.crawler_job_poll_interval_seconds,
                remaining,
            )
        )

    result_payload = get_json(
        url=_service_url(f"{job_path}/result"),
        timeout_seconds=(
            settings.crawler_service_timeout_seconds
        ),
    )
    result = _validate_contract(
        CrawlerJobResult,
        result_payload,
        contract_name="job result",
    )
    assert isinstance(result, CrawlerJobResult)

    if result.job_id != job_id:
        raise InternalServiceResponseError(
            "Crawler job result returned a different job_id."
        )

    if result.status == "failed":
        _raise_job_failure(result)

    if result.status != "completed" or result.result is None:
        raise InternalServiceResponseError(
            "Completed crawler job has no result object."
        )

    return result.result


def _create_and_wait(
    *,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    accepted_payload = post_json(
        url=_service_url(path),
        payload=payload,
        timeout_seconds=(
            settings.crawler_service_timeout_seconds
        ),
    )
    accepted = _validate_contract(
        CrawlerJobAccepted,
        accepted_payload,
        contract_name="job creation",
    )
    assert isinstance(accepted, CrawlerJobAccepted)

    if accepted.status not in {"queued", "running"}:
        raise InternalServiceResponseError(
            "New crawler job must be queued or running."
        )

    return _wait_for_result(accepted.job_id)


def crawl_announcements() -> dict[str, Any]:
    return _create_and_wait(
        path="/v1/crawl-jobs",
        payload={},
    )


def recollect_announcement(
    *,
    source_announcement_id: str,
    detail_url: str,
    target_file_name: str | None = None,
) -> dict[str, Any]:
    normalized_source_id = str(
        source_announcement_id or ""
    ).strip()
    normalized_detail_url = str(detail_url or "").strip()

    if not normalized_source_id:
        raise ValueError(
            "source_announcement_id must not be empty."
        )

    if not normalized_detail_url:
        raise ValueError("detail_url must not be empty.")

    payload = {
        "source_announcement_id": normalized_source_id,
        "detail_url": normalized_detail_url,
    }
    normalized_target_file_name = str(
        target_file_name or ""
    ).strip()
    if normalized_target_file_name:
        payload["target_file_name"] = normalized_target_file_name

    return _create_and_wait(
        path="/v1/recollect-jobs",
        payload=payload,
    )
