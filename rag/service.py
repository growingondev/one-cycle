from __future__ import annotations

import os
from functools import lru_cache

from rag.db_pipeline import DBRAGNoEvidenceError, DBRAGPipeline


NO_ANSWER_MESSAGE = "제공된 LH 공고문 근거에서 확인할 수 없습니다."


class RAGServiceError(RuntimeError):
    """API와 RAG 연결 과정에서 발생하는 오류."""


@lru_cache(maxsize=1)
def _get_pipeline() -> DBRAGPipeline:
    """
    DB 기반 MVP RAGPipeline을 최초 1회만 로드한다.

    BGE-M3 모델은 프로세스 내에서 재사용하고,
    검색 대상 Chunk/Embedding은 PostgreSQL + pgvector를 사용한다.
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
    FastAPI의 chat_service가 호출하는 최종 RAG 진입점.

    입력:
        announcement_id
        question

    출력:
        ChatResponse와 호환되는 dict
    """

    question = question.strip()

    if not question:
        raise RAGServiceError("질문이 비어 있습니다.")

    #
    # MVP에서는 공고 하나만 서비스한다.
    #
    expected_announcement_id_raw = os.getenv(
        "MVP_ANNOUNCEMENT_ID",
        "",
    ).strip()

    if expected_announcement_id_raw:
        try:
            expected_announcement_id = int(
                expected_announcement_id_raw
            )
        except ValueError as exc:
            raise RAGServiceError(
                "MVP_ANNOUNCEMENT_ID는 정수여야 합니다."
            ) from exc

        if announcement_id != expected_announcement_id:
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
                "공고문 근거 검색은 완료되었지만 답변 생성에 실패했습니다."
            ),
            "grounded": False,
            "evidence": [],
        }

    grounded = (
        bool(generated.sources)
        and generated.answer.strip() != NO_ANSWER_MESSAGE
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
                "score": float(source.reranker_score),
            }
        )

    return {
        "answer": generated.answer,
        "grounded": grounded,
        "evidence": evidence,
    }