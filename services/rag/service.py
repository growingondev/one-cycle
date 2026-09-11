from __future__ import annotations

from functools import lru_cache

from rag.db_pipeline import DBRAGNoEvidenceError, DBRAGPipeline
from services.rag.schemas import RAGAnswerResponse, RAGEvidence


NO_ANSWER_MESSAGE = "제공된 LH 공고문 근거에서 확인할 수 없습니다."


class RAGServiceError(RuntimeError):
    """RAG Service 처리 중 발생하는 오류."""


@lru_cache(maxsize=1)
def _get_pipeline() -> DBRAGPipeline:
    try:
        return DBRAGPipeline.from_database()
    except Exception as exc:
        raise RAGServiceError(
            "DB RAGPipeline 초기화에 실패했습니다. "
            f"error={type(exc).__name__}: {exc}"
        ) from exc


def answer_question(
    announcement_id: int,
    question: str,
) -> RAGAnswerResponse:
    question = question.strip()

    if not question:
        raise RAGServiceError(
            "질문이 비어 있습니다."
        )

    pipeline = _get_pipeline()

    try:
        generated = pipeline.ask(
            announcement_id=announcement_id,
            query=question,
        )

    except DBRAGNoEvidenceError:
        return RAGAnswerResponse(
            result="no_evidence",
            answer=NO_ANSWER_MESSAGE,
            grounded=False,
            evidence=[],
        )

    except Exception as exc:
        raise RAGServiceError(
            "RAG 답변 생성에 실패했습니다. "
            f"error={type(exc).__name__}: {exc}"
        ) from exc

    evidence: list[RAGEvidence] = []

    for source in generated.sources:
        section_title = None

        if source.section_path:
            section_title = " > ".join(
                source.section_path
            )
        elif source.title:
            section_title = source.title

        evidence.append(
            RAGEvidence(
                chunk_id=source.chunk_id,
                section_title=section_title,
                content=source.content,
                score=float(source.reranker_score),
            )
        )

    grounded = (
        bool(evidence)
        and generated.answer.strip() != NO_ANSWER_MESSAGE
    )

    if grounded:
        result = "grounded"
    else:
        result = "unsupported"

    return RAGAnswerResponse(
        result=result,
        answer=generated.answer,
        grounded=grounded,
        evidence=evidence,
    )