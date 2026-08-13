from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class AnnouncementListItem(BaseModel):
    id: int
    title: str
    region: str | None = None
    announcementDate: date | None = None
    publicationStatus: str | None = None


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementListItem]
    page: int
    size: int
    total: int
    total_pages: int


class AnnouncementDocumentItem(BaseModel):
    id: int
    originalFilename: str
    documentFormat: str
    downloadStatus: str
    fileSizeBytes: int
    createdAt: datetime


class KeyInformationResponse(BaseModel):
    applicationPeriod: dict[str, Any] = Field(default_factory=dict)
    eligibility: dict[str, Any] = Field(default_factory=dict)
    supplyInformation: dict[str, Any] = Field(default_factory=dict)
    incomeAssetCriteria: dict[str, Any] = Field(default_factory=dict)
    requiredDocuments: dict[str, Any] = Field(default_factory=dict)
    winnerAnnouncement: dict[str, Any] = Field(default_factory=dict)
    contactInformation: dict[str, Any] = Field(default_factory=dict)


class AnnouncementDetailResponse(BaseModel):
    id: int
    title: str
    region: str | None = None
    announcementDate: date | None = None
    publicationStatus: str | None = None
    detailUrl: str
    documents: list[AnnouncementDocumentItem] = Field(default_factory=list)
    keyInformation: KeyInformationResponse
