from __future__ import annotations

import traceback
from dataclasses import dataclass, replace

from rag.db_pipeline import DBRAGPipeline
from rag.retrieval.keyword_search import (
    KeywordSearchConfig,
    search_keywords,
)
from rag.retrieval.models import SearchResult
from backend.app.services.error_log_service import record_error


class HybridSearchError(RuntimeError):
    """Hybrid Search 중 발생하는 오류."""


@dataclass(frozen=True)
class HybridSearchConfig:
    vector_top_k: int = 20
    keyword_top_k: int = 20
    hybrid_top_k: int = 20
    rrf_k: int = 60

    def validate(self) -> None:
        if self.vector_top_k <= 0:
            raise ValueError(
                "vector_top_k는 1 이상이어야 합니다."
            )
        if self.keyword_top_k <= 0:
            raise ValueError(
                "keyword_top_k는 1 이상이어야 합니다."
            )
        if self.hybrid_top_k <= 0:
            raise ValueError(
                "hybrid_top_k는 1 이상이어야 합니다."
            )
        if self.rrf_k <= 0:
            raise ValueError(
                "rrf_k는 1 이상이어야 합니다."
            )


def _rrf_score(rank: int, rrf_k: int) -> float:
    """
    Reciprocal Rank Fusion:
        score = 1 / (rrf_k + rank)

    Vector와 Keyword의 원점수 스케일이 서로 다르므로
    원점수를 직접 더하지 않고 각 검색기의 순위를 결합한다.
    """
    if rank <= 0:
        raise HybridSearchError(
            f"rank는 1 이상이어야 합니다: {rank}"
        )

    return 1.0 / (rrf_k + rank)


def _hybrid_search_impl(
    *,
    pipeline: DBRAGPipeline,
    announcement_id: int,
    query: str,
    config: HybridSearchConfig | None = None,
) -> list[SearchResult]:
    """
    Vector Search + Keyword Search 결과를 RRF로 결합한다.

    특정 공고를 하드코딩하지 않는다.
    announcement_id는 호출자가 전달하며,
    Vector/Keyword 양쪽 모두 동일한 공고 범위에서 검색한다.
    """

    if not isinstance(announcement_id, int) or announcement_id <= 0:
        raise HybridSearchError(
            "announcement_id는 1 이상의 정수여야 합니다."
        )

    query = query.strip()

    if not query:
        raise HybridSearchError(
            "검색 질문이 비어 있습니다."
        )

    config = config or HybridSearchConfig()
    config.validate()

    original_top_k = pipeline.top_k

    try:
        pipeline.top_k = config.vector_top_k

        vector_results = pipeline.retrieve(
            announcement_id=announcement_id,
            query=query,
        )
    finally:
        pipeline.top_k = original_top_k

    keyword_results = search_keywords(
        announcement_id=announcement_id,
        query=query,
        config=KeywordSearchConfig(
            top_k=config.keyword_top_k,
        ),
    )

    fused: dict[str, dict] = {}

    for vector_rank, result in enumerate(
        vector_results,
        start=1,
    ):
        chunk_id = result.search_result.chunk_id
        search_result = result.search_result

        fused[chunk_id] = {
            "item": search_result.item,
            "vector_score": result.score,
            "vector_rank": vector_rank,
            "keyword_rank": None,
            "matched_by": {"pgvector"},
            "fusion_score": _rrf_score(
                vector_rank,
                config.rrf_k,
            ),
        }

    for keyword_rank, result in enumerate(
        keyword_results,
        start=1,
    ):
        chunk_id = result.chunk_id

        if chunk_id not in fused:
            fused[chunk_id] = {
                "item": result.item,
                "vector_score": None,
                "vector_rank": None,
                "keyword_rank": keyword_rank,
                "matched_by": {"keyword"},
                "fusion_score": _rrf_score(
                    keyword_rank,
                    config.rrf_k,
                ),
            }
        else:
            fused[chunk_id]["keyword_rank"] = (
                keyword_rank
            )
            fused[chunk_id]["matched_by"].add(
                "keyword"
            )
            fused[chunk_id]["fusion_score"] += (
                _rrf_score(
                    keyword_rank,
                    config.rrf_k,
                )
            )

    ordered = sorted(
        fused.items(),
        key=lambda pair: (
            -pair[1]["fusion_score"],
            pair[1]["vector_rank"]
            if pair[1]["vector_rank"] is not None
            else 10**9,
            pair[1]["keyword_rank"]
            if pair[1]["keyword_rank"] is not None
            else 10**9,
            pair[0],
        ),
    )

    results: list[SearchResult] = []

    for fusion_rank, (chunk_id, data) in enumerate(
        ordered[: config.hybrid_top_k],
        start=1,
    ):
        original_item = data["item"]

        raw_metadata = dict(
            original_item.raw_metadata or {}
        )
        raw_metadata["hybrid"] = {
            "vector_rank": data["vector_rank"],
            "keyword_rank": data["keyword_rank"],
            "rrf_k": config.rrf_k,
        }

        # CorpusItem은 frozen=True이므로 직접 수정하지 않고
        # dataclasses.replace()로 새 객체를 만든다.
        item = replace(
            original_item,
            raw_metadata=raw_metadata,
        )

        results.append(
            SearchResult(
                vector_index=item.vector_index,
                chunk_id=chunk_id,
                item=item,
                vector_score=data["vector_score"],
                vector_rank=data["vector_rank"],
                fusion_score=float(
                    data["fusion_score"]
                ),
                fusion_rank=fusion_rank,
                matched_by=set(
                    data["matched_by"]
                ),
            )
        )

    return results


def hybrid_search(
    *,
    pipeline: DBRAGPipeline,
    announcement_id: int,
    query: str,
    config: HybridSearchConfig | None = None,
) -> list[SearchResult]:
    """
    Hybrid Retrieval의 외부 진입점.

    실제 Retrieval 오류는 이 경계에서 Backend 공통 ErrorLog에
    한 번만 기록한 뒤 원래 예외를 다시 올립니다.
    """
    try:
        return _hybrid_search_impl(
            pipeline=pipeline,
            announcement_id=announcement_id,
            query=query,
            config=config,
        )

    except Exception as error:
        try:
            record_error(
                error_type="rag",
                stage="retrieval",
                message=str(error),
                announcement_id=(
                    announcement_id
                    if isinstance(announcement_id, int)
                    and announcement_id > 0
                    else None
                ),
                error_code=type(error).__name__,
                stack_trace=traceback.format_exc(),
            )
        except Exception as log_error:
            # 로그 저장 실패가 원래 Retrieval 예외를 가리지 않도록 한다.
            print(
                f"[WARNING] Retrieval ErrorLog 기록 실패: {log_error}"
            )

        raise
