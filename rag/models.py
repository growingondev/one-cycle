from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag.retrieval.models import SearchResult


@dataclass(frozen=True)
class RetrievalResult:
    """
    DB/pgvector 검색 결과를 Generation에 전달하기 위한 공용 계약.

    현재 MVP에서는 별도 Reranker를 실행하지 않으며,
    score/rank는 pgvector 검색 점수와 순위를 사용한다.
    """

    search_result: SearchResult
    score: float
    rank: int

    @property
    def chunk_id(self) -> str:
        return self.search_result.chunk_id

    @property
    def item(self):
        return self.search_result.item

    def to_dict(self) -> dict[str, Any]:
        payload = self.search_result.to_dict()
        payload.update(
            {
                "score": self.score,
                "rank": self.rank,
            }
        )
        return payload
