from __future__ import annotations

from typing import TYPE_CHECKING

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig

if TYPE_CHECKING:
    from rag.models import RetrievalResult
from .models import SourceContext


class ContextBuildError(RuntimeError):
    """Reranker 결과를 LLM 근거 문맥으로 만들지 못했을 때 발생."""


def build_source_contexts(
    retrieval_results: list[RetrievalResult],
    *,
    document_format: str,
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> list[SourceContext]:
    config.validate()

    if not retrieval_results:
        raise ContextBuildError(
            "Generation에 사용할 Reranker 결과가 없습니다."
        )

    selected = retrieval_results[: config.context_top_k]
    contexts: list[SourceContext] = []

    for source_number, result in enumerate(selected, start=1):
        item = result.item
        content = item.content.strip()

        if not content:
            raise ContextBuildError(
                f"근거 청크 content가 비어 있습니다: {result.chunk_id}"
            )

        if len(content) > config.max_chars_per_context:
            content = (
                content[: config.max_chars_per_context]
                + "\n[이하 내용은 프롬프트 길이 제한으로 생략]"
            )

        contexts.append(
            SourceContext(
                source_number=source_number,
                chunk_id=result.chunk_id,
                announcement_id=item.announcement_id,
                document_id=item.document_id,
                document_format=document_format,
                section_path=list(item.section_path),
                title=item.title,
                content=content,
                reranker_score=result.score,
                reranker_rank=result.rank,
            )
        )

    return contexts


def render_context_block(
    sources: list[SourceContext],
) -> str:
    if not sources:
        raise ContextBuildError("표시할 근거가 없습니다.")

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
