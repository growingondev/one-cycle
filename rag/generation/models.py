from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceContext:
    """LLM 프롬프트에 포함되는 공고문 근거 하나."""

    source_number: int
    chunk_id: str
    announcement_id: str | None
    document_id: str | None
    document_format: str
    section_path: list[str]
    title: str | None
    content: str
    reranker_score: float
    reranker_rank: int

    @property
    def section_label(self) -> str:
        if self.section_path:
            return " > ".join(self.section_path)

        if self.title:
            return self.title

        return "문서 위치 미상"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_number": self.source_number,
            "chunk_id": self.chunk_id,
            "announcement_id": self.announcement_id,
            "document_id": self.document_id,
            "document_format": self.document_format,
            "section_path": self.section_path,
            "title": self.title,
            "content": self.content,
            "reranker_score": self.reranker_score,
            "reranker_rank": self.reranker_rank,
        }


@dataclass(frozen=True)
class PromptPayload:
    """LLM에 전달할 프롬프트와 관련 정보."""

    system_prompt: str
    user_prompt: str
    query: str
    announcement_directory: str
    document_format: str
    sources: list[SourceContext]

    def to_messages(self) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": self.user_prompt,
            },
        ]


@dataclass(frozen=True)
class GeneratedAnswer:
    """최종 생성 답변과 근거 및 원본 응답."""

    answer: str
    query: str
    announcement_directory: str
    document_format: str
    sources: list[SourceContext]
    prompt: PromptPayload
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "query": self.query,
            "announcement_directory": self.announcement_directory,
            "document_format": self.document_format,
            "sources": [
                source.to_dict() for source in self.sources
            ],
            "prompt": {
                "system_prompt": self.prompt.system_prompt,
                "user_prompt": self.prompt.user_prompt,
            },
            "raw_response": self.raw_response,
        }
