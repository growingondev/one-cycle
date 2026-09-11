from __future__ import annotations

from typing import Any

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from .models import SourceContext


class ContextBuildError(RuntimeError):
    """Retrieval 결과를 LLM 근거 문맥으로 만들지 못했을 때 발생."""


def _unwrap_retrieval_result(result: Any):
    """
    현재 Hybrid SearchResult와 기존 RetrievalResult를 모두 지원한다.

    현재:
        SearchResult
        - item
        - chunk_id
        - fusion_score
        - fusion_rank

    기존 호환:
        RetrievalResult
        - search_result
        - score
        - rank

    향후 Reranker를 붙여도 Generation 경계를 다시 바꾸지 않도록
    여기서 결과 형식을 정규화한다.
    """

    # 현재 Hybrid / Keyword / Vector SearchResult
    if (
        hasattr(result, "item")
        and hasattr(result, "chunk_id")
        and hasattr(result, "fusion_score")
    ):
        item = result.item

        score = float(
            result.fusion_score
            if result.fusion_score is not None
            else (
                result.vector_score
                if getattr(result, "vector_score", None) is not None
                else 0.0
            )
        )

        rank = (
            result.fusion_rank
            if getattr(result, "fusion_rank", None) is not None
            else (
                result.vector_rank
                if getattr(result, "vector_rank", None) is not None
                else 0
            )
        )

        return {
            "item": item,
            "chunk_id": str(result.chunk_id),
            "score": score,
            "rank": int(rank or 0),
        }

    # 기존 RetrievalResult compatibility wrapper
    if (
        hasattr(result, "search_result")
        and hasattr(result, "score")
        and hasattr(result, "rank")
    ):
        search_result = result.search_result

        if search_result is None or not hasattr(
            search_result,
            "item",
        ):
            raise ContextBuildError(
                "RetrievalResult.search_result 형식이 올바르지 않습니다."
            )

        return {
            "item": search_result.item,
            "chunk_id": str(
                getattr(
                    search_result,
                    "chunk_id",
                    getattr(result, "chunk_id", ""),
                )
            ),
            "score": float(result.score),
            "rank": int(result.rank),
        }

    raise ContextBuildError(
        "지원하지 않는 Retrieval 결과 형식입니다. "
        f"type={type(result).__name__}"
    )


def build_source_contexts(
    retrieval_results: list[Any],
    *,
    document_format: str,
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> list[SourceContext]:
    """
    Vector / Keyword / Hybrid / 향후 Reranker 결과를
    Generation용 SourceContext로 변환한다.

    중간발표 현재 실행 경로:
        Hybrid SearchResult
        -> SourceContext
        -> Prompt
        -> LLM
    """
    config.validate()

    if not retrieval_results:
        raise ContextBuildError(
            "Generation에 사용할 Retrieval 결과가 없습니다."
        )

    selected = retrieval_results[
        : config.context_top_k
    ]

    contexts: list[SourceContext] = []
    remaining_chars = config.max_chars_per_context

    for source_number, raw_result in enumerate(
        selected,
        start=1,
    ):
        if remaining_chars <= 0:
            break
        normalized = _unwrap_retrieval_result(
            raw_result
        )

        item = normalized["item"]
        chunk_id = normalized["chunk_id"]
        content = str(item.content).strip()

        if not content:
            raise ContextBuildError(
                "근거 청크 content가 비어 있습니다: "
                f"{chunk_id}"
            )

        if len(content) > remaining_chars:
            content = (
                content[:remaining_chars]
                + "\n[이하 내용은 프롬프트 길이 제한으로 생략]"
            )

        remaining_chars -= len(content)

        contexts.append(
            SourceContext(
                source_number=source_number,
                chunk_id=chunk_id,
                announcement_id=(
                    item.announcement_id
                ),
                document_id=item.document_id,
                document_format=document_format,
                section_path=list(
                    item.section_path
                    or []
                ),
                title=item.title,
                content=content,

                # 현재 SourceContext 필드명은 기존 Reranker 계약을
                # 유지한다. 중간발표 버전에서는 Hybrid fusion score/rank가
                # 이 필드에 들어가며, 향후 실제 Reranker를 붙이면
                # 동일 필드에 reranker 결과를 넣으면 된다.
                reranker_score=float(
                    normalized["score"]
                ),
                reranker_rank=int(
                    normalized["rank"]
                ),
            )
        )

    return contexts


def render_context_block(
    sources: list[SourceContext],
) -> str:
    if not sources:
        raise ContextBuildError(
            "표시할 근거가 없습니다."
        )

    blocks: list[str] = []

    for source in sources:
        blocks.append(
            "\n".join(
                [
                    f"[근거 {source.source_number}]",
                    f"청크 ID: {source.chunk_id}",
                    f"문서 위치: {source.section_label}",
                    f"문서 형식: {source.document_format}",
                    "내용:",
                    source.content,
                ]
            )
        )

    return "\n\n".join(blocks)
