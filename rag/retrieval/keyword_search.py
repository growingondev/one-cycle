from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from kiwipiepy import Kiwi
from sqlalchemy import text

from rag.db.session import SessionLocal
from rag.retrieval.models import CorpusItem, SearchResult


class BM25SearchError(RuntimeError):
    """DB BM25 Search 중 발생하는 오류."""


@dataclass(frozen=True)
class BM25SearchConfig:
    top_k: int = 20
    min_token_length: int = 1
    k1: float = 1.5
    b: float = 0.75

    def validate(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        if self.min_token_length <= 0:
            raise ValueError(
                "min_token_length는 1 이상이어야 합니다."
            )
        if self.k1 <= 0:
            raise ValueError("k1은 0보다 커야 합니다.")
        if not 0.0 <= self.b <= 1.0:
            raise ValueError("b는 0 이상 1 이하여야 합니다.")


# ------------------------------------------------------------
# Korean tokenizer
# ------------------------------------------------------------

# Kiwi는 모듈 로드 시 한 번만 생성한다.
# 질문/문서마다 Kiwi 객체를 새로 만들지 않는다.
_KIWI = Kiwi()

# BM25 검색에 불필요한 문법적 형태소만 제외한다.
#
# J*: 조사
# E*: 어미
# S*: 문장부호/기호
#
# 명사(N*), 동사/형용사(V*), 숫자(SN), 외국어(SL) 등
# 의미를 가진 형태소는 최대한 보존한다.
_EXCLUDED_POS_PREFIXES = (
    "J",
    "E",
)

_EXCLUDED_POS = {
    "SF",  # 종결 부호
    "SP",  # 쉼표/가운뎃점/콜론/빗금 등
    "SS",  # 따옴표/괄호
    "SSO", # 여는 괄호류
    "SSC", # 닫는 괄호류
    "SE",  # 줄임표
}


def _normalize_text(value: str | None) -> str:
    """
    BM25 검색 전 공통 문자열 정규화.

    - 앞뒤 공백 제거
    - 연속된 공백을 하나로 통일
    - 영문 소문자화

    특정 공고나 질문 표현에 종속된 동의어 치환은 하지 않는다.
    """
    return re.sub(
        r"\s+",
        " ",
        (value or "").strip(),
    ).lower()


def _should_keep_token(
    form: str,
    tag: str,
    *,
    min_token_length: int,
) -> bool:
    """
    Kiwi가 분석한 형태소 중 BM25 검색에 사용할 토큰인지 결정한다.

    특정 LH 공고 용어를 하드코딩하지 않고,
    조사/어미/문장부호처럼 검색 의미가 낮은 형태소만 제거한다.
    """
    token = form.strip().lower()

    if not token:
        return False

    # 조사와 어미 제거
    if tag.startswith(_EXCLUDED_POS_PREFIXES):
        return False

    # 문장부호 제거
    if tag in _EXCLUDED_POS:
        return False

    # 공백이나 기호만 있는 토큰 제거
    if not re.search(r"[0-9a-z가-힣㎡%]", token):
        return False

    # 숫자는 한 자리여도 중요할 수 있다.
    # 예: 1순위, 2인, 3호
    if tag == "SN":
        return True

    if len(token) < min_token_length:
        return False

    return True


def _tokenize(
    value: str | None,
    *,
    min_token_length: int,
) -> list[str]:
    """
    Kiwi 기반 한국어 BM25 토큰화.

    기존 방식:
        정규식으로 문자열 덩어리를 그대로 토큰화

    개선 방식:
        Kiwi 형태소 분석
        -> 조사/어미/문장부호 제거
        -> 의미 형태소 보존

    이 함수는 사용자 질문과 공고문 Chunk 양쪽에 동일하게 적용된다.
    """
    normalized = _normalize_text(value)

    if not normalized:
        return []

    analyzed = _KIWI.tokenize(normalized)

    result: list[str] = []

    for token in analyzed:
        form = token.form
        tag = token.tag

        if not _should_keep_token(
            form,
            tag,
            min_token_length=min_token_length,
        ):
            continue

        result.append(form.strip().lower())

    return result


def _build_document_text(row) -> str:
    """
    BM25 corpus는 Chunk.search_text를 우선 사용한다.

    search_text가 비어 있는 예외 데이터만 title + content로 대체한다.
    """
    search_text = _normalize_text(row["search_text"])
    if search_text:
        return search_text

    return " ".join(
        part
        for part in (
            _normalize_text(row["title"]),
            _normalize_text(row["content"]),
        )
        if part
    )


def _bm25_scores(
    *,
    query_tokens: list[str],
    documents: list[list[str]],
    k1: float,
    b: float,
) -> list[float]:
    """
    Okapi BM25

    IDF:
        log(1 + (N - df + 0.5) / (df + 0.5))

    score:
        Σ IDF(q) *
          tf(q,d) * (k1 + 1)
          -----------------------------------------
          tf(q,d) + k1 * (1 - b + b * dl / avgdl)
    """
    document_count = len(documents)

    if document_count == 0:
        return []

    document_lengths = [len(doc) for doc in documents]
    average_document_length = (
        sum(document_lengths) / document_count
    )

    if average_document_length <= 0:
        return [0.0] * document_count

    term_frequencies = [
        Counter(document)
        for document in documents
    ]

    document_frequencies: Counter[str] = Counter()

    for frequencies in term_frequencies:
        for token in frequencies:
            document_frequencies[token] += 1

    unique_query_tokens = list(dict.fromkeys(query_tokens))

    idf: dict[str, float] = {}

    for token in unique_query_tokens:
        df = document_frequencies.get(token, 0)
        idf[token] = math.log(
            1.0
            + (
                document_count - df + 0.5
            )
            / (
                df + 0.5
            )
        )

    scores: list[float] = []

    for frequencies, document_length in zip(
        term_frequencies,
        document_lengths,
    ):
        score = 0.0

        for token in unique_query_tokens:
            tf = frequencies.get(token, 0)

            if tf <= 0:
                continue

            denominator = (
                tf
                + k1
                * (
                    1.0
                    - b
                    + b
                    * document_length
                    / average_document_length
                )
            )

            score += (
                idf[token]
                * tf
                * (k1 + 1.0)
                / denominator
            )

        scores.append(score)

    return scores


def search_bm25(
    *,
    announcement_id: int,
    query: str,
    config: BM25SearchConfig | None = None,
) -> list[SearchResult]:
    """
    선택된 공고의 Active Chunk 전체를 가져와
    Kiwi 기반 BM25 lexical search를 수행한다.

    검색 corpus:
    - Chunk.search_text 우선
    - search_text가 없으면 title + content fallback

    BM25 원점수는 SearchResult.fusion_score에 임시 보관한다.
    Hybrid Search에서는 이 점수의 절대값을 직접 더하지 않고
    BM25 순위만 RRF에 사용한다.
    """
    if not isinstance(announcement_id, int) or announcement_id <= 0:
        raise BM25SearchError(
            "announcement_id는 1 이상의 정수여야 합니다."
        )

    config = config or BM25SearchConfig()
    config.validate()

    normalized_query = _normalize_text(query)

    if not normalized_query:
        raise BM25SearchError(
            "검색 질문이 비어 있습니다."
        )

    query_tokens = _tokenize(
        normalized_query,
        min_token_length=config.min_token_length,
    )

    if not query_tokens:
        raise BM25SearchError(
            "BM25 검색에 사용할 토큰을 추출하지 못했습니다."
        )

    sql = text(
        """
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
            c.source_reference

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

        ORDER BY c.id ASC
        """
    )

    with SessionLocal() as db:
        rows = (
            db.execute(
                sql,
                {"announcement_id": announcement_id},
            )
            .mappings()
            .all()
        )

    if not rows:
        return []

    documents = [
        _tokenize(
            _build_document_text(row),
            min_token_length=config.min_token_length,
        )
        for row in rows
    ]

    scores = _bm25_scores(
        query_tokens=query_tokens,
        documents=documents,
        k1=config.k1,
        b=config.b,
    )

    ranked = sorted(
        (
            (index, score)
            for index, score in enumerate(scores)
            if score > 0.0
        ),
        key=lambda pair: (
            -pair[1],
            rows[pair[0]]["db_chunk_id"],
        ),
    )[: config.top_k]

    results: list[SearchResult] = []

    for rank, (row_index, score) in enumerate(
        ranked,
        start=1,
    ):
        row = rows[row_index]

        item = CorpusItem(
            vector_index=rank - 1,
            chunk_id=row["external_chunk_key"],
            document_id=str(row["document_id"]),
            announcement_id=str(announcement_id),
            chunk_order=None,
            chunk_type=row["content_type"],
            section_path=list(
                row["section_path"] or []
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
                "db_chunk_id": row["db_chunk_id"],
                "document_format": row["document_format"],
                "retrieval": "bm25",
                "query_tokens": query_tokens,
                "bm25_score": float(score),
                "bm25_k1": config.k1,
                "bm25_b": config.b,
                "tokenizer": "kiwi",
            },
        )

        results.append(
            SearchResult(
                vector_index=rank - 1,
                chunk_id=row["external_chunk_key"],
                item=item,
                vector_score=None,
                vector_rank=None,
                fusion_score=float(score),
                fusion_rank=rank,
                matched_by={"bm25"},
            )
        )

    return results