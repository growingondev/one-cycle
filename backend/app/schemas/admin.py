from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionAcceptedResponse(BaseModel):
    accepted: bool
    message: str
    reference: str | int | dict[str, Any] | None = None


class AdminAnnouncementItem(BaseModel):
    id: int
    title: str
    region: str | None = None
    announcement_date: date | None = None
    application_start: date | str | None = None
    application_end: date | str | None = None
    announcement_status: str | None = None
    collection_status: str | None = None
    created_at: datetime


class AdminAnnouncementListResponse(BaseModel):
    items: list[AdminAnnouncementItem]
    page: int
    size: int
    total: int
    total_pages: int


class AdminAnnouncementDetail(AdminAnnouncementItem):
    source_announcement_id: str
    detail_url: str
    collection_run_id: int
    key_information: dict[str, Any] | None = None
    document_count: int = 0


class AdminDocumentItem(BaseModel):
    id: int
    announcement_id: int
    announcement_title: str
    file_name: str
    document_type: str
    file_size: int
    download_status: str
    processing_status: str | None = None
    analysis_status: str | None = None
    created_at: datetime


class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocumentItem]
    page: int
    size: int
    total: int
    total_pages: int


class ProcessingSummary(BaseModel):
    run_id: int | None = None
    execution_status: str | None = None
    verification_status: str | None = None
    current_stage: str | None = None
    error_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class StructureSummary(BaseModel):
    schema_version: str | None = None
    element_count: int = 0


class ChunkingSummary(BaseModel):
    status: str | None = None
    chunk_count: int = 0


class EmbeddingSummary(BaseModel):
    completed_count: int = 0
    total_count: int = 0
    failed_count: int = 0


class AdminDocumentDetail(AdminDocumentItem):
    storage_path: str | None = None
    checksum_sha256: str | None = None
    processing: ProcessingSummary
    structure: StructureSummary
    chunking: ChunkingSummary
    embedding: EmbeddingSummary


class AdminProcessingRunItem(BaseModel):
    id: int
    announcement_id: int
    announcement_title: str
    document_id: int
    document_name: str
    execution_status: str
    verification_status: str
    current_stage: str | None = None
    error_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AdminProcessingRunListResponse(BaseModel):
    items: list[AdminProcessingRunItem]
    page: int
    size: int
    total: int
    total_pages: int


class AdminErrorDetail(BaseModel):
    id: str
    announcement_id: int
    announcement_title: str
    document_id: int
    document_name: str
    error_type: str
    error_code: str | None = None
    stage: str | None = None
    message: str
    status: str
    resolution: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AdminErrorListResponse(BaseModel):
    items: list[AdminErrorDetail]
    page: int
    size: int
    total: int
    total_pages: int


class ErrorStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(open|in_progress|resolved)$")
    resolution: str | None = Field(default=None, max_length=2000)
