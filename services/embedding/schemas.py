from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class EmbeddingRequestItem(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("id must not be empty.")

        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("text must not be empty.")

        return value


class EmbeddingRequest(BaseModel):
    items: list[EmbeddingRequestItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "EmbeddingRequest":
        ids = [item.id for item in self.items]

        if len(ids) != len(set(ids)):
            raise ValueError("items[].id must be unique.")

        return self


class EmbeddingResponseItem(BaseModel):
    id: str
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    model: str
    dimension: int
    normalized: bool
    items: list[EmbeddingResponseItem]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail