from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CorpusItem:
    """DB에서 조회한 하나의 검색 근거 청크."""

    vector_index: int
    chunk_id: str
    document_id: str | None
    announcement_id: str | None
    chunk_order: int | None
    chunk_type: str | None
    section_path: list[str]
    title: str | None
    content: str
    search_text: str
    source: dict[str, Any] | None
    raw_metadata: dict[str, Any]


@dataclass
class SearchResult:
    """Retrieval 결과와 검색 점수를 Generation 경계로 전달한다."""

    vector_index: int
    chunk_id: str
    item: CorpusItem
    vector_score: float | None = None
    vector_rank: int | None = None

    # 현재 DB Retrieval에서는 pgvector 점수/순위를 사용한다.
    fusion_score: float = 0.0
    fusion_rank: int | None = None

    matched_by: set[str] = field(
        default_factory=set
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector_index": self.vector_index,
            "chunk_id": self.chunk_id,
            "vector_score": self.vector_score,
            "vector_rank": self.vector_rank,
            "fusion_score": self.fusion_score,
            "fusion_rank": self.fusion_rank,
            "matched_by": sorted(self.matched_by),
            "announcement_id": self.item.announcement_id,
            "document_id": self.item.document_id,
            "chunk_type": self.item.chunk_type,
            "section_path": self.item.section_path,
            "title": self.item.title,
            "content": self.item.content,
            "search_text": self.item.search_text,
            "source": self.item.source,
        }
