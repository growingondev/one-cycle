from __future__ import annotations

from functools import lru_cache

from rag.db_pipeline import (
    DBRAGNoEvidenceError,
    DBRAGPipeline,
)
from services.rag.config import settings


NO_ANSWER_MESSAGE = (
    "제공된 LH 공고문 근거에서 확인할 수 없습니다."
)


class RAGServiceError(RuntimeError):
    """API와 RAG 연결 과정에서 발생하는 오류."""


@lru_cache(maxsize=1)
def _get_pipeline() -> DBRAGPipeline:
    """
    DB 기반 MVP RAGPipeline을 최초 1회만 로드한다.

    Query Embedding은 Embedding Service를 사용하고,
    검색 대상 Chunk/Embedding은
    PostgreSQL + pgvector를 사용한다.
    """

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
) -> dict:
    """
    RAG Service의 최종 질의응답 진입점.
    """

    question = question.strip()

    if not question:
        raise RAGServiceError(
            "질문이 비어 있습니다."
        )

    expected_announcement_id = (
        settings.mvp_announcement_id
    )

    if (
        expected_announcement_id is not None
        and announcement_id
        != expected_announcement_id
    ):
        return {
            "answer": (
                "현재 MVP에서 지원하지 않는 공고입니다."
            ),
            "grounded": False,
            "evidence": [],
        }

    pipeline = _get_pipeline()

    try:
        generated = pipeline.ask(
            announcement_id=announcement_id,
            query=question,
        )

    except DBRAGNoEvidenceError:
        return {
            "answer": NO_ANSWER_MESSAGE,
            "grounded": False,
            "evidence": [],
        }

    except Exception:
        return {
            "answer": (
                "현재 답변 생성 중 오류가 발생했습니다. "
                "공고문 근거 검색은 완료되었지만 "
                "답변 생성에 실패했습니다."
            ),
            "grounded": False,
            "evidence": [],
        }

    grounded = (
        bool(generated.sources)
        and generated.answer.strip()
        != NO_ANSWER_MESSAGE
    )

    evidence = []

    for source in generated.sources:
        section_title = None

        if source.section_path:
            section_title = " > ".join(
                source.section_path
            )

        elif source.title:
            section_title = source.title

        evidence.append(
            {
                "chunkId": source.chunk_id,
                "sectionTitle": section_title,
                "content": source.content,
                "score": float(
                    source.reranker_score
                ),
            }
        )

    return {
        "answer": generated.answer,
        "grounded": grounded,
        "evidence": evidence,
    }
