from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentSource(BaseModel):
    """Backend가 Worker에 전달하는 원본 문서 정보."""

    filename: str = Field(min_length=1)
    format: Literal["hwp", "hwpx"]
    storage_path: str = Field(min_length=1)


class DocumentProcessRequest(BaseModel):
    """POST /v1/documents/{document_id}/process Request."""

    announcement_id: int = Field(gt=0)
    announcement_key: str = Field(min_length=1)
    announcement_date: date | None = None
    source: DocumentSource
    start_stage: str | None = None


class DocumentWorkerSummary(BaseModel):
    """Worker 문서처리 결과 요약."""

    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)


class KeyInformationPayload(BaseModel):
    """현재 MVP에서 사용하는 필수 핵심정보 7개 필드."""

    application_period: dict[str, Any]
    eligibility: dict[str, Any]
    supply_information: dict[str, Any]
    income_asset_criteria: dict[str, Any]
    required_documents: dict[str, Any]
    winner_announcement: dict[str, Any]
    contact_information: dict[str, Any]


class DocumentProcessResponse(BaseModel):
    """Document Worker 정상 처리 Response."""

    document_id: int = Field(gt=0)
    announcement_id: int = Field(gt=0)
    announcement_key: str = Field(min_length=1)

    status: Literal["completed"]

    document_format: Literal["hwp", "hwpx"]

    output_path: str = Field(min_length=1)

    summary: DocumentWorkerSummary

    key_information: KeyInformationPayload
