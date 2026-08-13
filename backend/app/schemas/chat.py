from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    announcement_id: int = Field(alias="announcementId")
    question: str = Field(min_length=1, max_length=2000)


class EvidenceItem(BaseModel):
    chunk_id: str | int = Field(alias="chunkId")
    section_title: str | None = Field(default=None, alias="sectionTitle")
    content: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    evidence: list[EvidenceItem] = Field(default_factory=list)
