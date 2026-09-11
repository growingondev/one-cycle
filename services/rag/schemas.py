from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RAGAnswerRequest(BaseModel):
    announcement_id: int = Field(ge=1)
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("question must not be empty.")

        return value


class RAGEvidence(BaseModel):
    chunk_id: str
    section_title: str | None = None
    content: str
    score: float


class RAGAnswerResponse(BaseModel):
    result: Literal[
        "grounded",
        "no_evidence",
        "unsupported",
    ]
    answer: str
    grounded: bool
    evidence: list[RAGEvidence]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail