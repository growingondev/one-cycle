from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


# ============================================================
# 기본 경로 / 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

DEFAULT_SHEET_NAME = "평가셋"

DEFAULT_RAGAS_BASE_URL = os.getenv(
    "RAGAS_API_BASE_URL",
    "http://127.0.0.1:8080/v1",
)

DEFAULT_RAGAS_API_KEY = os.getenv(
    "RAGAS_API_KEY",
    "no-key",
)

DEFAULT_RAGAS_MODEL = os.getenv(
    "RAGAS_MODEL",
    "",
).strip()

DEFAULT_EMBEDDING_MODEL = os.getenv(
    "RAGAS_EMBEDDING_MODEL",
    "BAAI/bge-m3",
)


# ============================================================
# Recall 판정 기준
# ============================================================
#
# 기존:
#   reference_text와 context의 문자열 유사도
#   threshold=0.75 이상 → HIT
#
# 변경:
#   1. 정규화 후 직접 포함 여부
#   2. 핵심 단어 포함률
#   3. 날짜/시간/금액 등 숫자 정보 포함률
#   4. 부분 문자열 유사도
#
# 를 함께 사용한다.
#
# ※ 최종적으로 gold_chunk_ids 기반 Recall을 사용하는 것이 가장
#    객관적이지만, 현재 평가셋 구조를 그대로 사용할 수 있도록
#    reference_text 기반 Hybrid Matching을 사용한다.
# ============================================================

NUMERIC_COVERAGE_THRESHOLD = 0.70
TOKEN_COVERAGE_THRESHOLD = 0.45

NO_NUMBER_TOKEN_THRESHOLD = 0.55
NO_NUMBER_SIMILARITY_THRESHOLD = 0.35

HIGH_SIMILARITY_THRESHOLD = 0.75


# ============================================================
# Dataset
# ============================================================


def normalize_dataset_name(value: str) -> str:
    dataset = value.strip().upper()

    aliases = {
        "GC": "GC",
        "GOCHANG": "GC",
        "고창": "GC",
        "HC": "HC",
        "HWACHEON": "HC",
        "화천": "HC",
    }

    if dataset not in aliases:
        raise ValueError(
            f"지원하지 않는 dataset입니다: {value}\n"
            "사용 가능: GC, HC"
        )

    return aliases[dataset]


def dataset_paths(
    dataset: str,
) -> tuple[Path, Path]:
    dataset = normalize_dataset_name(dataset)

    input_xlsx = (
        RESULTS_DIR
        / f"{dataset}_FINAL_V1_result.xlsx"
    )

    output_xlsx = (
        RESULTS_DIR
        / f"{dataset}_FINAL_V1_scored.xlsx"
    )

    return input_xlsx, output_xlsx


# ============================================================
# Excel
# ============================================================


def find_columns(
    ws,
) -> dict[str, int]:
    columns: dict[str, int] = {}

    for cell in ws[1]:
        if cell.value is not None:
            columns[
                str(cell.value).strip()
            ] = cell.column

    return columns


def ensure_column(
    ws,
    columns: dict[str, int],
    name: str,
) -> int:
    if name in columns:
        return columns[name]

    new_column = ws.max_column + 1

    ws.cell(
        row=1,
        column=new_column,
        value=name,
    )

    columns[name] = new_column

    return new_column


# ============================================================
# retrieved_contexts 분리
# ============================================================


def split_retrieved_contexts(
    value: Any,
) -> list[str]:
    """
    evaluate_rag.py에서 저장한 retrieved_contexts를
    개별 Rank Context로 분리한다.

    예:

    [rank=1 ...]
    내용...

    ---
    [rank=2 ...]
    내용...

    을

    [
        "내용...",
        "내용..."
    ]

    형태로 변환한다.
    """

    if value is None:
        return []

    text = str(value).strip()

    if not text:
        return []

    parts = re.split(
        r"\n\s*---\s*\n",
        text,
    )

    contexts: list[str] = []

    for part in parts:
        part = part.strip()

        if not part:
            continue

        lines = part.splitlines()

        # 첫 줄이 [rank=...] 메타데이터라면 제거
        if (
            lines
            and lines[0]
            .strip()
            .startswith("[rank=")
        ):
            part = "\n".join(
                lines[1:]
            ).strip()

        if part:
            contexts.append(part)

    return contexts


# ============================================================
# Recall용 텍스트 정규화
# ============================================================


def normalize_text(
    text: str,
) -> str:
    """
    Recall 비교를 위한 정규화.

    다음과 같은 표기 차이를 줄인다.

    2026 → 26

    '26. 08. 24.(월)
    '26.08.24(월)

    등의 표현을 최대한 동일하게 비교한다.
    """

    text = str(text).lower()

    # --------------------------------------------------------
    # 2026년 → 26년
    # 2026 → 26
    # --------------------------------------------------------

    text = re.sub(
        r"\b20(\d{2})\b",
        r"\1",
        text,
    )

    # --------------------------------------------------------
    # 시간 표현 일부 통일
    #
    # 10시 → 10:00
    # --------------------------------------------------------

    text = re.sub(
        r"(\d{1,2})\s*시",
        r"\1:00",
        text,
    )

    # --------------------------------------------------------
    # 공백 제거
    # --------------------------------------------------------

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    # --------------------------------------------------------
    # 특수문자 제거
    #
    # 한글 / 영어 / 숫자만 유지
    # --------------------------------------------------------

    text = re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
    )

    return text


# ============================================================
# 숫자 정규화
# ============================================================


def normalize_number(
    value: str,
) -> str:
    """
    숫자를 비교하기 쉽게 정규화.

    예:

    08   → 8
    08.0 → 8
    """

    value = value.strip()

    try:
        number = float(value)

        if number.is_integer():
            return str(
                int(number)
            )

        return str(number)

    except ValueError:
        return value


def extract_numbers(
    text: str,
) -> list[str]:
    """
    reference/context에서 숫자 정보를 추출한다.

    날짜, 시간, 금액, 면적, 나이 등의
    핵심 정보를 비교하는 데 사용한다.

    예:

    '26.08.24 10:00~16:00

    →
    26, 8, 24, 10, 0, 16, 0
    """

    text = str(text)

    # 2026 → 26
    text = re.sub(
        r"\b20(\d{2})\b",
        r"\1",
        text,
    )

    numbers = re.findall(
        r"\d+(?:\.\d+)?",
        text,
    )

    return [
        normalize_number(number)
        for number in numbers
    ]


# ============================================================
# 토큰 추출
# ============================================================


def extract_tokens(
    text: str,
) -> list[str]:
    """
    reference_text의 의미 있는 단어를 추출한다.
    """

    text = str(text).lower()

    text = re.sub(
        r"\b20(\d{2})\b",
        r"\1",
        text,
    )

    tokens = re.findall(
        r"[가-힣]{2,}"
        r"|[A-Za-z]+"
        r"|\d+(?:\.\d+)?",
        text,
    )

    # 비교에 큰 의미가 없는 단어
    stopwords = {
        "및",
        "또는",
        "그리고",
        "경우",
        "현재",
        "기준",
        "관련",
        "대한",
        "통해",
        "있으며",
        "있음",
        "해당",
        "한다",
        "됩니다",
        "한다면",
    }

    result: list[str] = []

    for token in tokens:
        token = (
            token
            .strip()
            .lower()
        )

        if not token:
            continue

        if token in stopwords:
            continue

        result.append(token)

    return result


# ============================================================
# Token Coverage
# ============================================================


def token_coverage(
    reference_text: str,
    context: str,
) -> float:
    """
    reference_text의 핵심 토큰이
    context 안에 얼마나 존재하는지 계산한다.

    0.0 ~ 1.0
    """

    tokens = extract_tokens(
        reference_text
    )

    if not tokens:
        return 0.0

    context_norm = normalize_text(
        context
    )

    matched = 0

    for token in tokens:
        token_norm = normalize_text(
            token
        )

        if (
            token_norm
            and token_norm
            in context_norm
        ):
            matched += 1

    return (
        matched
        / len(tokens)
    )


# ============================================================
# Numeric Coverage
# ============================================================


def number_coverage(
    reference_text: str,
    context: str,
) -> float | None:
    """
    reference_text에 있는 숫자 정보가
    context에도 얼마나 존재하는지 계산한다.

    날짜 / 시간 / 금액 / 나이 등에서 중요하다.

    reference_text에 숫자가 없다면 None.
    """

    reference_numbers = (
        extract_numbers(
            reference_text
        )
    )

    if not reference_numbers:
        return None

    context_numbers = (
        extract_numbers(
            context
        )
    )

    if not context_numbers:
        return 0.0

    context_number_set = set(
        context_numbers
    )

    matched = sum(
        1
        for number
        in reference_numbers
        if number
        in context_number_set
    )

    return (
        matched
        / len(reference_numbers)
    )


# ============================================================
# 부분 문자열 유사도
# ============================================================


def partial_similarity(
    reference_text: str,
    context: str,
) -> float:
    """
    긴 Context 안에 reference_text와 유사한
    부분이 존재하는지 확인한다.

    기존 SequenceMatcher를 유지하되
    전체 Context와만 비교하지 않고
    부분 구간을 비교한다.
    """

    ref_norm = normalize_text(
        reference_text
    )

    ctx_norm = normalize_text(
        context
    )

    if (
        not ref_norm
        or not ctx_norm
    ):
        return 0.0

    # reference가 context에 그대로 존재
    if ref_norm in ctx_norm:
        return 1.0

    # context가 reference보다 짧은 경우
    if len(ctx_norm) <= len(ref_norm):
        return SequenceMatcher(
            None,
            ref_norm,
            ctx_norm,
        ).ratio()

    # --------------------------------------------------------
    # 긴 context의 일부분과 reference 비교
    # --------------------------------------------------------

    window_size = max(
        len(ref_norm),
        int(
            len(ref_norm)
            * 2.0
        ),
    )

    step = max(
        1,
        len(ref_norm) // 5,
    )

    best_score = 0.0

    max_start = max(
        1,
        len(ctx_norm)
        - window_size
        + 1,
    )

    for start in range(
        0,
        max_start,
        step,
    ):
        candidate = ctx_norm[
            start:
            start + window_size
        ]

        score = SequenceMatcher(
            None,
            ref_norm,
            candidate,
        ).ratio()

        best_score = max(
            best_score,
            score,
        )

    # 마지막 부분도 한 번 비교
    if len(ctx_norm) > window_size:
        candidate = ctx_norm[
            -window_size:
        ]

        score = SequenceMatcher(
            None,
            ref_norm,
            candidate,
        ).ratio()

        best_score = max(
            best_score,
            score,
        )

    return best_score


# ============================================================
# 실제 Evidence 판정
# ============================================================


def evidence_matches(
    reference_text: str,
    context: str,
) -> tuple[
    bool,
    float,
    str,
]:
    """
    Context가 정답 근거를 포함하는지 판정한다.

    Returns
    -------
    matched
        True / False

    score
        진단용 점수

    reason
        어떤 방식으로 매칭되었는지
    """

    ref_norm = normalize_text(
        reference_text
    )

    ctx_norm = normalize_text(
        context
    )

    if (
        not ref_norm
        or not ctx_norm
    ):
        return (
            False,
            0.0,
            "empty",
        )

    # ========================================================
    # 1. 정규화 후 reference 전체가 Context에 포함
    #
    # 가장 신뢰도가 높은 방식
    # ========================================================

    if ref_norm in ctx_norm:
        return (
            True,
            1.0,
            "normalized_exact_containment",
        )

    # ========================================================
    # 각각의 보조 점수 계산
    # ========================================================

    word_score = token_coverage(
        reference_text,
        context,
    )

    numeric_score = number_coverage(
        reference_text,
        context,
    )

    similarity = partial_similarity(
        reference_text,
        context,
    )

    # ========================================================
    # 2. 날짜 / 금액 / 시간 등의 숫자가 있는 경우
    #
    # 숫자 정보는 RAG 질문에서 매우 중요하기 때문에
    # 숫자가 실제로 일치하는지를 우선적으로 본다.
    # ========================================================

    if numeric_score is not None:

        # 숫자 대부분이 일치하고
        # 핵심 단어도 일정 수준 이상 일치
        if (
            numeric_score
            >= NUMERIC_COVERAGE_THRESHOLD
            and word_score
            >= TOKEN_COVERAGE_THRESHOLD
        ):
            score = (
                0.55
                * numeric_score
                + 0.35
                * word_score
                + 0.10
                * similarity
            )

            return (
                True,
                score,
                "numeric_fact_match",
            )

        # 숫자가 거의 완전히 동일하고
        # 문장 유사성도 존재
        if (
            numeric_score
            >= 0.95
            and similarity
            >= 0.35
        ):
            score = (
                0.60
                * numeric_score
                + 0.40
                * similarity
            )

            return (
                True,
                score,
                "numeric_full_match",
            )

    # ========================================================
    # 3. 숫자가 없는 일반 문장
    # ========================================================

    if numeric_score is None:

        if (
            word_score
            >= NO_NUMBER_TOKEN_THRESHOLD
            and similarity
            >= NO_NUMBER_SIMILARITY_THRESHOLD
        ):
            score = (
                0.70
                * word_score
                + 0.30
                * similarity
            )

            return (
                True,
                score,
                "semantic_token_match",
            )

    # ========================================================
    # 4. 문자열 자체가 매우 유사한 경우
    # ========================================================

    if (
        similarity
        >= HIGH_SIMILARITY_THRESHOLD
    ):
        return (
            True,
            similarity,
            "high_text_similarity",
        )

    # ========================================================
    # 5. 일치하지 않음
    #
    # 그래도 디버깅을 위해 가장 높은 점수를 반환한다.
    # ========================================================

    candidates = [
        word_score,
        similarity,
    ]

    if numeric_score is not None:
        candidates.append(
            numeric_score
        )

    diagnostic_score = max(
        candidates
    )

    return (
        False,
        diagnostic_score,
        "no_match",
    )


# ============================================================
# Recall@K
# ============================================================


def recall_at_k(
    reference_text: str,
    contexts: list[str],
    k: int,
) -> tuple[
    int | None,
    int | None,
    float,
    str,
]:
    """
    Recall@K

    정답 근거(reference_text)가
    Top-K 검색 결과 안에 하나라도 존재하면:

        Recall@K = 1

    존재하지 않으면:

        Recall@K = 0

    reference_text가 없는 Unanswerable 질문은:

        None

    Returns
    -------
    recall
    matched_rank
    best_score
    match_reason
    """

    if not reference_text.strip():
        return (
            None,
            None,
            0.0,
            "no_reference_text",
        )

    best_score = 0.0
    best_reason = "no_match"

    for rank, context in enumerate(
        contexts[:k],
        start=1,
    ):
        (
            matched,
            score,
            reason,
        ) = evidence_matches(
            reference_text,
            context,
        )

        if score > best_score:
            best_score = score
            best_reason = reason

        if matched:
            return (
                1,
                rank,
                score,
                reason,
            )

    return (
        0,
        None,
        best_score,
        best_reason,
    )


# ============================================================
# RAGAS 패키지 확인
# ============================================================


def check_ragas_packages() -> None:
    missing: list[str] = []

    try:
        import ragas  # noqa: F401

    except ImportError:
        missing.append(
            "ragas"
        )

    try:
        import openai  # noqa: F401

    except ImportError:
        missing.append(
            "openai"
        )

    try:
        import sentence_transformers  # noqa: F401

    except ImportError:
        missing.append(
            "sentence-transformers"
        )

    if missing:
        raise RuntimeError(
            "RAGAS 평가에 필요한 "
            "패키지가 없습니다.\n\n"
            "다음 명령으로 설치하세요:\n\n"
            f"pip install {' '.join(missing)}"
        )


# ============================================================
# RAGAS Scorer 생성
# ============================================================


async def build_ragas_scorers(
    base_url: str,
    api_key: str,
    model: str,
    embedding_model: str,
) -> dict[str, Any]:

    from openai import AsyncOpenAI

    from ragas.llms import llm_factory

    from ragas.embeddings import (
        HuggingFaceEmbeddings,
    )

    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
        FactualCorrectness,
    )

    if not model:
        raise RuntimeError(
            "RAGAS 평가용 모델명이 없습니다.\n\n"
            "예:\n"
            "python evaluation/evaluate_metrics.py "
            "--dataset GC "
            "--ragas-model 모델명"
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    llm = llm_factory(
        model,
        client=client,
    )

    embeddings = HuggingFaceEmbeddings(
        model=embedding_model,
    )

    return {
        "context_precision":
            ContextPrecision(
                llm=llm
            ),

        "context_recall":
            ContextRecall(
                llm=llm
            ),

        "faithfulness":
            Faithfulness(
                llm=llm
            ),

        "response_relevancy":
            AnswerRelevancy(
                llm=llm,
                embeddings=embeddings,
            ),

        "factual_correctness":
            FactualCorrectness(
                llm=llm
            ),
    }


# ============================================================
# 문항 1개 RAGAS 평가
# ============================================================


async def score_one_with_ragas(
    scorers: dict[str, Any],
    user_input: str,
    reference: str,
    response: str,
    contexts: list[str],
) -> dict[str, float | None]:

    scores: dict[
        str,
        float | None,
    ] = {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "response_relevancy": None,
        "factual_correctness": None,
    }

    async def safe_score(
        name: str,
        **kwargs,
    ) -> float | None:

        try:
            result = await scorers[
                name
            ].ascore(
                **kwargs
            )

            value = result.value

            if value is None:
                return None

            value = float(value)

            if math.isnan(value):
                return None

            return value

        except Exception as exc:
            print(
                "    [RAGAS 경고] "
                f"{name} 실패: {exc}"
            )

            return None

    # --------------------------------------------------------
    # Context Precision
    # --------------------------------------------------------

    scores[
        "context_precision"
    ] = await safe_score(
        "context_precision",
        user_input=user_input,
        reference=reference,
        retrieved_contexts=contexts,
    )

    # --------------------------------------------------------
    # Context Recall
    # --------------------------------------------------------

    scores[
        "context_recall"
    ] = await safe_score(
        "context_recall",
        user_input=user_input,
        reference=reference,
        retrieved_contexts=contexts,
    )

    # --------------------------------------------------------
    # Faithfulness
    # --------------------------------------------------------

    scores[
        "faithfulness"
    ] = await safe_score(
        "faithfulness",
        user_input=user_input,
        response=response,
        retrieved_contexts=contexts,
    )

    # --------------------------------------------------------
    # Response Relevancy
    # --------------------------------------------------------

    scores[
        "response_relevancy"
    ] = await safe_score(
        "response_relevancy",
        user_input=user_input,
        response=response,
    )

    # --------------------------------------------------------
    # Factual Correctness
    # --------------------------------------------------------

    scores[
        "factual_correctness"
    ] = await safe_score(
        "factual_correctness",
        response=response,
        reference=reference,
    )

    return scores


# ============================================================
# 전체 평가
# ============================================================


async def evaluate_metrics(
    args: argparse.Namespace,
) -> None:

    dataset = normalize_dataset_name(
        args.dataset
    )

    (
        default_input,
        default_output,
    ) = dataset_paths(
        dataset
    )

    input_path = (
        Path(args.xlsx)
        if args.xlsx
        else default_input
    )

    output_path = (
        Path(args.output)
        if args.output
        else default_output
    )

    # ========================================================
    # 입력 파일 확인
    # ========================================================

    if not input_path.exists():
        raise FileNotFoundError(
            "평가 결과 파일을 "
            "찾을 수 없습니다:\n"
            f"{input_path}\n\n"
            "먼저 evaluate_rag.py를 "
            "실행하세요."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Excel 읽기
    # ========================================================

    wb = load_workbook(
        input_path
    )

    if (
        args.sheet
        not in wb.sheetnames
    ):
        raise ValueError(
            f"'{args.sheet}' "
            "시트가 없습니다.\n"
            f"현재 시트: "
            f"{wb.sheetnames}"
        )

    ws = wb[
        args.sheet
    ]

    columns = find_columns(
        ws
    )

    # ========================================================
    # 필요한 열 확인
    # ========================================================

    required = [
        "question_id",
        "user_input",
        "reference",
        "reference_text",
        "retrieved_contexts",
        "response",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "context_precision",
        "context_recall",
        "faithfulness",
        "response_relevancy",
        "factual_correctness",
    ]

    missing = [
        name
        for name in required
        if name not in columns
    ]

    if missing:
        raise ValueError(
            "평가에 필요한 Excel 열이 "
            "없습니다:\n"
            + ", ".join(missing)
        )

    # ========================================================
    # Recall 진단용 열
    # ========================================================

    recall_method_col = ensure_column(
        ws,
        columns,
        "recall_match_method",
    )

    # Top-5에서 실제로 몇 등에
    # 정답 근거가 검색되었는지 저장
    recall_rank_col = ensure_column(
        ws,
        columns,
        "recall_matched_rank",
    )

    # 디버깅용 점수
    recall_score_col = ensure_column(
        ws,
        columns,
        "recall_match_score",
    )

    ragas_status_col = ensure_column(
        ws,
        columns,
        "ragas_status",
    )

    # ========================================================
    # RAGAS 준비
    # ========================================================

    scorers = None

    if not args.skip_ragas:

        check_ragas_packages()

        scorers = (
            await build_ragas_scorers(
                base_url=(
                    args.ragas_base_url
                ),
                api_key=(
                    args.ragas_api_key
                ),
                model=(
                    args.ragas_model
                ),
                embedding_model=(
                    args.embedding_model
                ),
            )
        )

    # ========================================================
    # 시작 출력
    # ========================================================

    print(
        "=" * 78
    )

    print(
        "RAG 평가 지표 계산"
    )

    print(
        f"dataset          : "
        f"{dataset}"
    )

    print(
        f"입력 파일       : "
        f"{input_path}"
    )

    print(
        f"출력 파일       : "
        f"{output_path}"
    )

    print(
        "Recall 방식      : "
        "Hybrid Evidence Matching "
        "(텍스트 + 핵심 토큰 + 숫자 사실)"
    )

    print(
        f"RAGAS            : "
        f"{'실행 안 함' if args.skip_ragas else '실행'}"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # 통계 변수
    # ========================================================

    processed = 0

    answerable = 0

    recall_1_hits = 0
    recall_3_hits = 0
    recall_5_hits = 0

    ragas_values: dict[
        str,
        list[float],
    ] = {
        "context_precision": [],
        "context_recall": [],
        "faithfulness": [],
        "response_relevancy": [],
        "factual_correctness": [],
    }

    # ========================================================
    # 평가 문항 반복
    # ========================================================

    for row in range(
        2,
        ws.max_row + 1,
    ):

        # ----------------------------------------------------
        # question_id
        # ----------------------------------------------------

        question_id = ws.cell(
            row=row,
            column=columns[
                "question_id"
            ],
        ).value

        # ----------------------------------------------------
        # user_input
        # ----------------------------------------------------

        user_input = ws.cell(
            row=row,
            column=columns[
                "user_input"
            ],
        ).value

        if user_input is None:
            continue

        user_input = (
            str(user_input)
            .strip()
        )

        if not user_input:
            continue

        # ----------------------------------------------------
        # reference
        # ----------------------------------------------------

        reference = ws.cell(
            row=row,
            column=columns[
                "reference"
            ],
        ).value

        # ----------------------------------------------------
        # reference_text
        # ----------------------------------------------------

        reference_text = ws.cell(
            row=row,
            column=columns[
                "reference_text"
            ],
        ).value

        # ----------------------------------------------------
        # retrieved_contexts
        # ----------------------------------------------------

        retrieved_raw = ws.cell(
            row=row,
            column=columns[
                "retrieved_contexts"
            ],
        ).value

        # ----------------------------------------------------
        # response
        # ----------------------------------------------------

        response = ws.cell(
            row=row,
            column=columns[
                "response"
            ],
        ).value

        # ----------------------------------------------------
        # 문자열 정리
        # ----------------------------------------------------

        reference = (
            ""
            if reference is None
            else str(
                reference
            ).strip()
        )

        reference_text = (
            ""
            if reference_text is None
            else str(
                reference_text
            ).strip()
        )

        response = (
            ""
            if response is None
            else str(
                response
            ).strip()
        )

        contexts = (
            split_retrieved_contexts(
                retrieved_raw
            )
        )

        processed += 1

        # ====================================================
        # 문항 정보 출력
        # ====================================================

        print(
            f"\n[{processed:02d}] "
            f"{question_id}: "
            f"{user_input}"
        )

        # ====================================================
        # Recall@1
        # ====================================================

        (
            r1,
            rank1,
            score1,
            reason1,
        ) = recall_at_k(
            reference_text,
            contexts,
            1,
        )

        # ====================================================
        # Recall@3
        # ====================================================

        (
            r3,
            rank3,
            score3,
            reason3,
        ) = recall_at_k(
            reference_text,
            contexts,
            3,
        )

        # ====================================================
        # Recall@5
        # ====================================================

        (
            r5,
            rank5,
            score5,
            reason5,
        ) = recall_at_k(
            reference_text,
            contexts,
            5,
        )

        # ====================================================
        # Excel에 Recall 저장
        # ====================================================

        ws.cell(
            row=row,
            column=columns[
                "recall_at_1"
            ],
            value=r1,
        )

        ws.cell(
            row=row,
            column=columns[
                "recall_at_3"
            ],
            value=r3,
        )

        ws.cell(
            row=row,
            column=columns[
                "recall_at_5"
            ],
            value=r5,
        )

        # ====================================================
        # Unanswerable
        # ====================================================

        if r1 is None:

            ws.cell(
                row=row,
                column=recall_method_col,
                value=(
                    "N/A - "
                    "reference_text 없음"
                ),
            )

            ws.cell(
                row=row,
                column=recall_rank_col,
                value=None,
            )

            ws.cell(
                row=row,
                column=recall_score_col,
                value=None,
            )

            print(
                "  Recall@K       : N/A"
            )

        # ====================================================
        # Answerable
        # ====================================================

        else:

            answerable += 1

            recall_1_hits += (
                r1 or 0
            )

            recall_3_hits += (
                r3 or 0
            )

            recall_5_hits += (
                r5 or 0
            )

            # Top-5 결과를 기준으로
            # 매칭 방법/순위/점수 저장

            ws.cell(
                row=row,
                column=recall_method_col,
                value=(
                    "hybrid evidence match"
                    f" | reason={reason5}"
                ),
            )

            ws.cell(
                row=row,
                column=recall_rank_col,
                value=rank5,
            )

            ws.cell(
                row=row,
                column=recall_score_col,
                value=round(
                    score5,
                    4,
                ),
            )

            print(
                "  Recall@1/3/5   : "
                f"{r1} / "
                f"{r3} / "
                f"{r5}"
            )

            if rank5 is not None:

                print(
                    "  Match Rank     : "
                    f"{rank5}"
                )

                print(
                    "  Match Reason   : "
                    f"{reason5}"
                )

                print(
                    "  Match Score    : "
                    f"{score5:.4f}"
                )

            else:

                print(
                    "  Match          : "
                    "Top-5 내 근거 미탐지"
                )

                print(
                    "  Best Score     : "
                    f"{score5:.4f}"
                )

        # ====================================================
        # RAGAS
        # ====================================================

        if args.skip_ragas:

            # 이미 scored.xlsx에 RAGAS 결과가 존재하는 경우
            # 기존 결과를 지우지 않는다.
            #
            # ragas_status가 비어 있을 때만 SKIPPED 입력.

            current_status = ws.cell(
                row=row,
                column=ragas_status_col,
            ).value

            if current_status is None:
                ws.cell(
                    row=row,
                    column=ragas_status_col,
                    value="SKIPPED",
                )

        elif not response:

            ws.cell(
                row=row,
                column=ragas_status_col,
                value=(
                    "SKIPPED - "
                    "response 없음"
                ),
            )

        elif not contexts:

            ws.cell(
                row=row,
                column=ragas_status_col,
                value=(
                    "SKIPPED - "
                    "retrieved_contexts 없음"
                ),
            )

        else:

            assert scorers is not None

            scores = (
                await score_one_with_ragas(
                    scorers=scorers,
                    user_input=user_input,
                    reference=reference,
                    response=response,
                    contexts=contexts,
                )
            )

            for (
                metric_name,
                score,
            ) in scores.items():

                ws.cell(
                    row=row,
                    column=columns[
                        metric_name
                    ],
                    value=score,
                )

                if score is not None:

                    ragas_values[
                        metric_name
                    ].append(
                        score
                    )

            if all(
                value is not None
                for value
                in scores.values()
            ):
                status = "OK"

            elif any(
                value is not None
                for value
                in scores.values()
            ):
                status = "PARTIAL"

            else:
                status = "FAILED"

            ws.cell(
                row=row,
                column=ragas_status_col,
                value=status,
            )

        # ====================================================
        # 중간 저장
        #
        # 평가 중 오류가 발생해도 앞 문항의 결과가
        # 보존되도록 매 문항마다 저장한다.
        # ====================================================

        wb.save(
            output_path
        )

    # ========================================================
    # 최종 Recall 통계
    # ========================================================

    print(
        "\n"
        + "=" * 78
    )

    print(
        "평가 완료"
    )

    print(
        f"전체 처리 질문 : "
        f"{processed}"
    )

    if answerable > 0:

        recall1 = (
            recall_1_hits
            / answerable
        )

        recall3 = (
            recall_3_hits
            / answerable
        )

        recall5 = (
            recall_5_hits
            / answerable
        )

        print(
            f"Answerable 질문 : "
            f"{answerable}"
        )

        print(
            "Recall@1        : "
            f"{recall_1_hits}/"
            f"{answerable} "
            f"= {recall1:.4f} "
            f"({recall1 * 100:.1f}%)"
        )

        print(
            "Recall@3        : "
            f"{recall_3_hits}/"
            f"{answerable} "
            f"= {recall3:.4f} "
            f"({recall3 * 100:.1f}%)"
        )

        print(
            "Recall@5        : "
            f"{recall_5_hits}/"
            f"{answerable} "
            f"= {recall5:.4f} "
            f"({recall5 * 100:.1f}%)"
        )

    # ========================================================
    # RAGAS 평균
    # ========================================================

    if not args.skip_ragas:

        print(
            "\n[RAGAS 평균]"
        )

        for (
            metric_name,
            values,
        ) in ragas_values.items():

            if values:

                average = (
                    sum(values)
                    / len(values)
                )

                print(
                    f"{metric_name:22s}: "
                    f"{average:.4f} "
                    f"({len(values)}개)"
                )

            else:

                print(
                    f"{metric_name:22s}: "
                    "N/A"
                )

    print(
        f"\n결과 파일       : "
        f"{output_path}"
    )

    print(
        "=" * 78
    )


# ============================================================
# CLI
# ============================================================


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "evaluate_rag.py 결과를 읽어 "
            "Recall@K와 RAGAS 평가를 수행합니다."
        )
    )

    parser.add_argument(
        "--dataset",
        default="GC",
        help=(
            "평가셋 코드 "
            "(GC=고창율계, HC=화천신읍2)"
        ),
    )

    parser.add_argument(
        "--xlsx",
        default=None,
        help=(
            "평가 입력 Excel 경로. "
            "생략하면 dataset 기본 경로 사용."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "평가 결과 Excel 저장 경로. "
            "생략하면 dataset 기본 경로 사용."
        ),
    )

    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET_NAME,
    )

    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help=(
            "RAGAS 평가는 실행하지 않고 "
            "Recall@K만 계산합니다."
        ),
    )

    parser.add_argument(
        "--ragas-base-url",
        default=DEFAULT_RAGAS_BASE_URL,
    )

    parser.add_argument(
        "--ragas-api-key",
        default=DEFAULT_RAGAS_API_KEY,
    )

    parser.add_argument(
        "--ragas-model",
        default=DEFAULT_RAGAS_MODEL,
    )

    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================


def main() -> None:

    args = parse_args()

    try:

        asyncio.run(
            evaluate_metrics(
                args
            )
        )

    except KeyboardInterrupt:

        print(
            "\n사용자가 평가를 "
            "중단했습니다."
        )

        sys.exit(130)

    except Exception as exc:

        print(
            "\n평가 중 오류가 "
            "발생했습니다:\n"
            f"{exc}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()