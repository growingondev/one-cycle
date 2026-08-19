from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text

from backend.app.db.session import SessionLocal
from rag.retrieval.models import CorpusItem, SearchResult


class KeywordSearchError(RuntimeError):
    """DB Keyword Search 중 발생하는 오류."""


@dataclass(frozen=True)
class KeywordSearchConfig:
    top_k: int = 20
    min_token_length: int = 2

    def validate(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        if self.min_token_length <= 0:
            raise ValueError(
                "min_token_length는 1 이상이어야 합니다."
            )


def _normalize_query(query: str) -> str:
    query = re.sub(r"\s+", " ", query.strip())

    if not query:
        raise KeywordSearchError(
            "검색 질문이 비어 있습니다."
        )

    return query


def _tokenize_query(
    query: str,
    *,
    min_token_length: int,
) -> list[str]:
    """
    한국어 형태소 분석기를 강제하지 않고,
    일반적인 공고문 검색어를 안전하게 추출한다.

    예:
    "계약금은 얼마인가요?"
    -> ["계약금은", "얼마인가요"]

    PostgreSQL LIKE 기반 검색에서 특정 문서에 하드코딩하지 않고
    모든 공고에 동일하게 적용하기 위한 최소 토큰화다.
    """

    tokens = re.findall(
        r"[0-9A-Za-z가-힣㎡%./-]+",
        query,
    )

    result: list[str] = []

    for token in tokens:
        token = token.strip()

        if len(token) < min_token_length:
            continue

        if token not in result:
            result.append(token)

    if not result:
        raise KeywordSearchError(
            "검색에 사용할 키워드를 추출하지 못했습니다."
        )

    return result


def search_keywords(
    *,
    announcement_id: int,
    query: str,
    config: KeywordSearchConfig | None = None,
) -> list[SearchResult]:
    """
    선택된 공고의 Active Chunk를 대상으로 Keyword Search를 수행한다.

    현재 단계의 목적:
    - Vector Search와 독립적으로 Keyword Search가 동작하는지 확인
    - Hybrid Search 전에 별도 검색 경로를 검증
    - 특정 announcement/document 하드코딩 금지

    검색 대상:
    1. Chunk.search_text
    2. Chunk.title
    3. Chunk.content

    점수:
    - search_text 정확 query 포함: 높은 가중치
    - title 정확 query 포함: 높은 가중치
    - content 정확 query 포함: 보조 가중치
    - 각 query token의 포함 개수를 누적

    이 구현은 1차 DB Keyword Retrieval용이며,
    이후 Hybrid Search 단계에서 Vector 결과와 결합한다.
    """

    if not isinstance(announcement_id, int) or announcement_id <= 0:
        raise KeywordSearchError(
            "announcement_id는 1 이상의 정수여야 합니다."
        )

    config = config or KeywordSearchConfig()
    config.validate()

    normalized_query = _normalize_query(query)

    tokens = _tokenize_query(
        normalized_query,
        min_token_length=config.min_token_length,
    )

    exact_pattern = f"%{normalized_query}%"

    params: dict[str, object] = {
        "announcement_id": announcement_id,
        "exact_pattern": exact_pattern,
        "top_k": config.top_k,
    }

    token_score_parts: list[str] = []
    token_match_parts: list[str] = []

    for index, token in enumerate(tokens):
        key = f"token_{index}"
        params[key] = f"%{token}%"

        token_score_parts.append(
            f"""
            (
                CASE
                    WHEN COALESCE(c.search_text, '') ILIKE :{key}
                    THEN 3.0
                    ELSE 0.0
                END
                +
                CASE
                    WHEN COALESCE(c.title, '') ILIKE :{key}
                    THEN 2.0
                    ELSE 0.0
                END
                +
                CASE
                    WHEN COALESCE(c.content, '') ILIKE :{key}
                    THEN 1.0
                    ELSE 0.0
                END
            )
            """
        )

        token_match_parts.append(
            f"""
            (
                COALESCE(c.search_text, '') ILIKE :{key}
                OR COALESCE(c.title, '') ILIKE :{key}
                OR COALESCE(c.content, '') ILIKE :{key}
            )
            """
        )

    token_score_sql = (
        "\n+\n".join(token_score_parts)
        if token_score_parts
        else "0.0"
    )

    token_match_sql = (
        "\nOR\n".join(token_match_parts)
        if token_match_parts
        else "FALSE"
    )

    sql = text(
        f"""
        SELECT
            c.id AS db_chunk_id,
            c.external_chunk_key,
            c.document_id,
            c.document_format,
            c.content_type,
            c.section_path,
            c.title,
            c.content,
            c.search_text,
            c.source_reference,

            (
                CASE
                    WHEN COALESCE(c.search_text, '')
                         ILIKE :exact_pattern
                    THEN 8.0
                    ELSE 0.0
                END
                +
                CASE
                    WHEN COALESCE(c.title, '')
                         ILIKE :exact_pattern
                    THEN 6.0
                    ELSE 0.0
                END
                +
                CASE
                    WHEN COALESCE(c.content, '')
                         ILIKE :exact_pattern
                    THEN 4.0
                    ELSE 0.0
                END
                +
                {token_score_sql}
            ) AS keyword_score

        FROM system_state ss

        JOIN announcements a
          ON a.collection_run_id
           = ss.active_collection_run_id

        JOIN chunks c
          ON c.announcement_id = a.id

        JOIN chunk_sets cs
          ON cs.id = c.chunk_set_id
         AND cs.is_active = TRUE

        JOIN processing_runs pr
          ON pr.id = cs.processing_run_id
         AND pr.is_active = TRUE

        WHERE a.id = :announcement_id
          AND c.status = 'completed'
          AND (
                COALESCE(c.search_text, '')
                ILIKE :exact_pattern

                OR COALESCE(c.title, '')
                ILIKE :exact_pattern

                OR COALESCE(c.content, '')
                ILIKE :exact_pattern

                OR {token_match_sql}
          )

        ORDER BY
            keyword_score DESC,
            c.id ASC

        LIMIT :top_k
        """
    )

    with SessionLocal() as db:
        rows = (
            db.execute(sql, params)
            .mappings()
            .all()
        )

    results: list[SearchResult] = []

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        score = float(
            row["keyword_score"]
            or 0.0
        )

        item = CorpusItem(
            vector_index=rank - 1,
            chunk_id=row[
                "external_chunk_key"
            ],
            document_id=str(
                row["document_id"]
            ),
            announcement_id=str(
                announcement_id
            ),
            chunk_order=None,
            chunk_type=row[
                "content_type"
            ],
            section_path=list(
                row["section_path"]
                or []
            ),
            title=row["title"],
            content=row["content"],
            search_text=(
                row["search_text"]
                or row["content"]
            ),
            source=(
                row["source_reference"]
                or {}
            ),
            raw_metadata={
                "db_chunk_id": (
                    row["db_chunk_id"]
                ),
                "document_format": (
                    row["document_format"]
                ),
                "retrieval": (
                    "keyword"
                ),
                "query_tokens": (
                    tokens
                ),
            },
        )

        results.append(
            SearchResult(
                vector_index=rank - 1,
                chunk_id=row[
                    "external_chunk_key"
                ],
                item=item,
                vector_score=None,
                vector_rank=None,
                fusion_score=score,
                fusion_rank=rank,
                matched_by={
                    "keyword"
                },
            )
        )

    return results
