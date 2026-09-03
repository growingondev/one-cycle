from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from evaluation.dataset_resolver import (
    DEFAULT_SHEET_NAME,
    default_scored_path,
    resolve_result_xlsx,
)


# ============================================================
# RAGAS 설정
# ============================================================

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

DEFAULT_METRIC_TIMEOUT_SECONDS = int(
    os.getenv(
        "RAGAS_METRIC_TIMEOUT_SECONDS",
        "300",
    )
)

DEFAULT_RAGAS_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv(
        "RAGAS_REQUEST_TIMEOUT_SECONDS",
        str(
            DEFAULT_METRIC_TIMEOUT_SECONDS
        ),
    )
)

# Faithfulness는 retrieved_contexts가 길어질수록
# Judge 모델의 context window를 초과할 수 있으므로
# Faithfulness에 전달하는 Context만 별도로 제한한다.
#
# - Recall@K: 전체 retrieved_contexts 그대로 사용
# - Response Relevancy: 기존 방식 그대로
# - Factual Correctness: 기존 방식 그대로
# - Faithfulness: 상위 3개 Context, Context당 최대 2000자
FAITHFULNESS_MAX_CONTEXTS = int(
    os.getenv(
        "RAGAS_FAITHFULNESS_MAX_CONTEXTS",
        "3",
    )
)

FAITHFULNESS_MAX_CHARS_PER_CONTEXT = int(
    os.getenv(
        "RAGAS_FAITHFULNESS_MAX_CHARS_PER_CONTEXT",
        "2000",
    )
)


# ============================================================
# Recall 판정 기준
# ============================================================

NUMERIC_COVERAGE_THRESHOLD = 0.70
TOKEN_COVERAGE_THRESHOLD = 0.45

NO_NUMBER_TOKEN_THRESHOLD = 0.55
NO_NUMBER_SIMILARITY_THRESHOLD = 0.35

HIGH_SIMILARITY_THRESHOLD = 0.75


# ============================================================
# Excel
# ============================================================


def find_columns(
    ws,
) -> dict[str, int]:
    return {
        str(cell.value).strip(): cell.column
        for cell in ws[1]
        if cell.value is not None
    }


def ensure_column(
    ws,
    columns: dict[str, int],
    name: str,
) -> int:
    if name in columns:
        return columns[name]

    new_column = (
        ws.max_column
        + 1
    )

    ws.cell(
        row=1,
        column=new_column,
        value=name,
    )

    columns[name] = (
        new_column
    )

    return new_column


def to_float_or_none(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if math.isnan(number):
        return None

    return number


# ============================================================
# retrieved_contexts 분리
# ============================================================


def split_retrieved_contexts(
    value: Any,
) -> list[str]:
    """
    evaluate_rag.py에서 저장한 retrieved_contexts를
    Rank별 Context 리스트로 변환한다.
    """
    if value is None:
        return []

    text = str(
        value
    ).strip()

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

        lines = (
            part.splitlines()
        )

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
            contexts.append(
                part
            )

    return contexts


# ============================================================
# Recall용 텍스트 정규화
# ============================================================


def normalize_text(
    text: str,
) -> str:
    text = str(
        text
    ).lower()

    # 2026 -> 26
    text = re.sub(
        r"\b20(\d{2})\b",
        r"\1",
        text,
    )

    # 10시 -> 10:00
    text = re.sub(
        r"(\d{1,2})\s*시",
        r"\1:00",
        text,
    )

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    text = re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
    )

    return text


def normalize_number(
    value: str,
) -> str:
    value = value.strip()

    try:
        number = float(
            value
        )

        if number.is_integer():
            return str(
                int(number)
            )

        return str(
            number
        )

    except ValueError:
        return value


def extract_numbers(
    text: str,
) -> list[str]:
    text = str(
        text
    )

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
        normalize_number(
            number
        )
        for number in numbers
    ]


def extract_tokens(
    text: str,
) -> list[str]:
    text = str(
        text
    ).lower()

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

        result.append(
            token
        )

    return result


def token_coverage(
    reference_text: str,
    context: str,
) -> float:
    tokens = extract_tokens(
        reference_text
    )

    if not tokens:
        return 0.0

    context_norm = (
        normalize_text(
            context
        )
    )

    matched = 0

    for token in tokens:
        token_norm = (
            normalize_text(
                token
            )
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


def number_coverage(
    reference_text: str,
    context: str,
) -> float | None:
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
        for number in reference_numbers
        if number
        in context_number_set
    )

    return (
        matched
        / len(reference_numbers)
    )


def partial_similarity(
    reference_text: str,
    context: str,
) -> float:
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

    if ref_norm in ctx_norm:
        return 1.0

    if (
        len(ctx_norm)
        <= len(ref_norm)
    ):
        return SequenceMatcher(
            None,
            ref_norm,
            ctx_norm,
        ).ratio()

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
            start
            + window_size
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

    if (
        len(ctx_norm)
        > window_size
    ):
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


def evidence_matches(
    reference_text: str,
    context: str,
) -> tuple[
    bool,
    float,
    str,
]:
    """
    현재 develop-api의 Hybrid Evidence Matching 로직을 유지한다.

    1. 정규화 완전 포함
    2. 숫자 + 핵심 토큰
    3. 숫자 없는 문장의 토큰/유사도
    4. 높은 문자열 유사도
    5. 복합 Evidence
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

    if ref_norm in ctx_norm:
        return (
            True,
            1.0,
            "normalized_exact_containment",
        )

    word_score = (
        token_coverage(
            reference_text,
            context,
        )
    )

    numeric_score = (
        number_coverage(
            reference_text,
            context,
        )
    )

    similarity = (
        partial_similarity(
            reference_text,
            context,
        )
    )

    if numeric_score is not None:
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

        if (
            numeric_score
            >= 0.80
            and (
                word_score
                >= 0.25
                or similarity
                >= 0.25
            )
        ):
            score = (
                0.60
                * numeric_score
                + 0.25
                * word_score
                + 0.15
                * similarity
            )

            return (
                True,
                score,
                "numeric_evidence_match",
            )

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

        if (
            word_score
            >= 0.70
            and similarity
            >= 0.25
        ):
            score = (
                0.75
                * word_score
                + 0.25
                * similarity
            )

            return (
                True,
                score,
                "strong_token_match",
            )

    if (
        similarity
        >= HIGH_SIMILARITY_THRESHOLD
    ):
        return (
            True,
            similarity,
            "high_text_similarity",
        )

    evidence_count = 0

    if word_score >= 0.50:
        evidence_count += 1

    if similarity >= 0.40:
        evidence_count += 1

    if (
        numeric_score is not None
        and numeric_score
        >= 0.70
    ):
        evidence_count += 1

    if evidence_count >= 2:
        if numeric_score is None:
            final_score = (
                0.65
                * word_score
                + 0.35
                * similarity
            )
        else:
            final_score = (
                0.45
                * numeric_score
                + 0.35
                * word_score
                + 0.20
                * similarity
            )

        if final_score >= 0.55:
            return (
                True,
                final_score,
                "multi_evidence_match",
            )

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
    if not reference_text.strip():
        return (
            None,
            None,
            0.0,
            "no_reference_text",
        )

    top_k_contexts = (
        contexts[:k]
    )

    if not top_k_contexts:
        return (
            0,
            None,
            0.0,
            "no_contexts",
        )

    best_score = 0.0
    best_reason = (
        "no_match"
    )

    for rank, context in enumerate(
        top_k_contexts,
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

    combined_context = "\n".join(
        top_k_contexts
    )

    (
        combined_matched,
        combined_score,
        combined_reason,
    ) = evidence_matches(
        reference_text,
        combined_context,
    )

    if combined_score > best_score:
        best_score = (
            combined_score
        )
        best_reason = (
            combined_reason
        )

    if combined_matched:
        return (
            1,
            None,
            combined_score,
            (
                f"combined_top_{k}_"
                f"{combined_reason}"
            ),
        )

    return (
        0,
        None,
        best_score,
        best_reason,
    )


def parse_question_ids(
    value: str | None,
) -> set[str] | None:
    if value is None:
        return None

    question_ids = {
        item.strip().upper()
        for item in value.split(",")
        if item.strip()
    }

    return (
        question_ids
        or None
    )


# ============================================================
# RAGAS
# ============================================================


def build_faithfulness_contexts(
    contexts: list[str],
) -> list[str]:
    """
    Faithfulness 평가에만 사용할 Context를 제한한다.

    기본값:
    - 검색 순위 상위 3개 Context만 사용
    - Context 1개당 최대 2000자

    Recall@K 계산에 사용하는 contexts 원본은 수정하지 않는다.
    Response Relevancy와 Factual Correctness 입력도 변경하지 않는다.
    """
    if not contexts:
        return []

    limited_contexts: list[str] = []

    for context in contexts[
        :FAITHFULNESS_MAX_CONTEXTS
    ]:
        context_text = str(
            context
        ).strip()

        if not context_text:
            continue

        limited_contexts.append(
            context_text[
                :FAITHFULNESS_MAX_CHARS_PER_CONTEXT
            ]
        )

    return limited_contexts


def check_ragas_packages() -> None:
    missing: list[str] = []

    try:
        import ragas  # noqa: F401
    except ImportError:
        missing.append("ragas")

    try:
        import openai  # noqa: F401
    except ImportError:
        missing.append("openai")

    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        missing.append(
            "sentence-transformers"
        )

    if missing:
        raise RuntimeError(
            "RAGAS 평가에 필요한 패키지가 없습니다.\n\n"
            "다음 명령으로 설치하세요:\n\n"
            f"pip install {' '.join(missing)}"
        )


async def build_ragas_scorers(
    *,
    base_url: str,
    api_key: str,
    model: str,
    embedding_model: str,
    adapt_factual_korean: bool,
    factual_only: bool,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    from openai import (
        AsyncOpenAI,
    )

    from ragas.embeddings import (
        HuggingFaceEmbeddings,
    )

    from ragas.llms import (
        llm_factory,
    )

    from ragas.metrics.collections import (
        AnswerRelevancy,
        Faithfulness,
        FactualCorrectness,
    )

    if not model:
        raise RuntimeError(
            "RAGAS 평가용 모델명이 없습니다.\n\n"
            "예:\n"
            "python evaluation/evaluate_metrics.py "
            "--dataset BD "
            "--ragas-model 모델명"
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=request_timeout_seconds,
        max_retries=1,
    )

    llm = llm_factory(
        model,
        client=client,
        max_tokens=4096,
    )

    embeddings = None

    if not factual_only:
        embeddings = (
            HuggingFaceEmbeddings(
                model=embedding_model,
            )
        )

    factual_correctness = (
        FactualCorrectness(
            llm=llm
        )
    )

    if adapt_factual_korean:
        print(
            "[RAGAS] FactualCorrectness "
            "한국어 Prompt adaptation 시작"
        )

        factual_correctness.prompt = (
            await factual_correctness.prompt.adapt(
                target_language="korean",
                llm=llm,
                adapt_instruction=True,
            )
        )

        factual_correctness.nli_prompt = (
            await factual_correctness.nli_prompt.adapt(
                target_language="korean",
                llm=llm,
                adapt_instruction=True,
            )
        )

        print(
            "[RAGAS] FactualCorrectness "
            "한국어 Prompt adaptation 완료"
        )

        print(
            "  Claim Prompt Language : "
            f"{factual_correctness.prompt.language}"
        )

        print(
            "  NLI Prompt Language   : "
            f"{factual_correctness.nli_prompt.language}"
        )

    scorers: dict[
        str,
        Any,
    ] = {
        "factual_correctness":
            factual_correctness,
    }

    if not factual_only:
        assert embeddings is not None

        scorers.update(
            {
                "faithfulness":
                    Faithfulness(
                        llm=llm
                    ),
                "response_relevancy":
                    AnswerRelevancy(
                        llm=llm,
                        embeddings=embeddings,
                    ),
            }
        )

    return scorers


async def score_one_with_ragas(
    *,
    scorers: dict[str, Any],
    user_input: str,
    reference: str,
    response: str,
    contexts: list[str],
    factual_only: bool,
    metric_timeout_seconds: int,
) -> tuple[
    dict[str, float | None],
    dict[str, float],
]:
    """
    metric별 독립 timeout을 적용한다.

    한 metric이 timeout/실패해도 None으로 처리하고
    나머지 metric 및 다음 문항을 계속 평가한다.
    """
    scores: dict[
        str,
        float | None,
    ] = {
        "faithfulness": None,
        "response_relevancy": None,
        "factual_correctness": None,
    }

    metric_times: dict[
        str,
        float,
    ] = {}

    async def safe_score(
        name: str,
        **kwargs,
    ) -> float | None:
        metric_start = (
            time.perf_counter()
        )

        try:
            result = await asyncio.wait_for(
                scorers[
                    name
                ].ascore(
                    **kwargs
                ),
                timeout=(
                    metric_timeout_seconds
                ),
            )

            value = result.value

            if value is None:
                return None

            value = float(
                value
            )

            if math.isnan(
                value
            ):
                return None

            return value

        except asyncio.TimeoutError:
            print(
                "    [RAGAS TIMEOUT] "
                f"{name}: "
                f"{metric_timeout_seconds}s 초과"
            )
            return None

        except Exception as exc:
            print(
                "    [RAGAS 경고] "
                f"{name} 실패: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

        finally:
            elapsed = (
                time.perf_counter()
                - metric_start
            )

            metric_times[
                name
            ] = elapsed

            print(
                "  [TIME] "
                f"{name:22s}: "
                f"{elapsed:8.2f}s"
            )

    if not factual_only:
        # Faithfulness에만 길이 제한된 Context를 사용한다.
        # 원본 contexts는 Recall 계산 등 다른 로직에 그대로 유지된다.
        faithfulness_contexts = (
            build_faithfulness_contexts(
                contexts
            )
        )

        print(
            "  [Faithfulness Context] "
            f"{len(contexts)}개 -> "
            f"{len(faithfulness_contexts)}개, "
            f"Context당 최대 "
            f"{FAITHFULNESS_MAX_CHARS_PER_CONTEXT}자"
        )

        scores[
            "faithfulness"
        ] = await safe_score(
            "faithfulness",
            user_input=user_input,
            response=response,
            retrieved_contexts=(
                faithfulness_contexts
            ),
        )

        scores[
            "response_relevancy"
        ] = await safe_score(
            "response_relevancy",
            user_input=user_input,
            response=response,
        )

    scores[
        "factual_correctness"
    ] = await safe_score(
        "factual_correctness",
        response=response,
        reference=reference,
    )

    return (
        scores,
        metric_times,
    )


# ============================================================
# 최종 통계
# ============================================================


def collect_final_statistics(
    *,
    ws,
    columns: dict[str, int],
    selected_question_ids: (
        set[str] | None
    ),
    factual_only: bool,
) -> dict[str, Any]:
    total_questions = 0
    answerable = 0

    recall_hits = {
        1: 0,
        3: 0,
        5: 0,
    }

    ragas_values: dict[
        str,
        list[float],
    ] = {
        "faithfulness": [],
        "response_relevancy": [],
        "factual_correctness": [],
    }

    for row in range(
        2,
        ws.max_row + 1,
    ):
        question_id = str(
            ws.cell(
                row=row,
                column=columns[
                    "question_id"
                ],
            ).value
            or ""
        ).strip().upper()

        if (
            selected_question_ids
            is not None
            and question_id
            not in selected_question_ids
        ):
            continue

        user_input = str(
            ws.cell(
                row=row,
                column=columns[
                    "user_input"
                ],
            ).value
            or ""
        ).strip()

        if not user_input:
            continue

        total_questions += 1

        r1 = to_float_or_none(
            ws.cell(
                row=row,
                column=columns[
                    "recall_at_1"
                ],
            ).value
        )

        r3 = to_float_or_none(
            ws.cell(
                row=row,
                column=columns[
                    "recall_at_3"
                ],
            ).value
        )

        r5 = to_float_or_none(
            ws.cell(
                row=row,
                column=columns[
                    "recall_at_5"
                ],
            ).value
        )

        if r1 is not None:
            answerable += 1
            recall_hits[1] += int(
                r1 >= 1.0
            )
            recall_hits[3] += int(
                (r3 or 0.0)
                >= 1.0
            )
            recall_hits[5] += int(
                (r5 or 0.0)
                >= 1.0
            )

        for metric_name in (
            "faithfulness",
            "response_relevancy",
            "factual_correctness",
        ):
            if (
                factual_only
                and metric_name
                != "factual_correctness"
            ):
                continue

            value = to_float_or_none(
                ws.cell(
                    row=row,
                    column=columns[
                        metric_name
                    ],
                ).value
            )

            if value is not None:
                ragas_values[
                    metric_name
                ].append(value)

    return {
        "total_questions":
            total_questions,
        "answerable":
            answerable,
        "recall_hits":
            recall_hits,
        "ragas_values":
            ragas_values,
    }


# ============================================================
# 전체 평가
# ============================================================


async def evaluate_metrics(
    args: argparse.Namespace,
) -> None:
    dataset, input_path = (
        resolve_result_xlsx(
            dataset=args.dataset,
            xlsx=args.xlsx,
        )
    )

    output_path = (
        Path(args.output)
        if args.output
        else default_scored_path(
            input_path
        )
    )

    if not output_path.is_absolute():
        output_path = (
            Path.cwd()
            / output_path
        ).resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Resume이면 기존 scored.xlsx를 입력으로 사용한다.
    workbook_path = (
        output_path
        if (
            args.resume
            and output_path.is_file()
        )
        else input_path
    )

    wb = load_workbook(
        workbook_path
    )

    try:
        if (
            args.sheet
            not in wb.sheetnames
        ):
            raise ValueError(
                f"'{args.sheet}' 시트가 없습니다. "
                f"현재 시트={wb.sheetnames}"
            )

        ws = wb[
            args.sheet
        ]

        columns = find_columns(
            ws
        )

        selected_question_ids = (
            parse_question_ids(
                args.question_ids
            )
        )

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
                "평가에 필요한 Excel 열이 없습니다: "
                + ", ".join(missing)
            )

        recall_method_col = (
            ensure_column(
                ws,
                columns,
                "recall_match_method",
            )
        )

        recall_rank_col = (
            ensure_column(
                ws,
                columns,
                "recall_matched_rank",
            )
        )

        recall_score_col = (
            ensure_column(
                ws,
                columns,
                "recall_match_score",
            )
        )

        ragas_status_col = (
            ensure_column(
                ws,
                columns,
                "ragas_status",
            )
        )

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
                    adapt_factual_korean=(
                        args.adapt_factual_korean
                    ),
                    factual_only=(
                        args.factual_only
                    ),
                    request_timeout_seconds=(
                        args.ragas_request_timeout
                    ),
                )
            )

        print("=" * 78)
        print("RAG 평가 지표 계산")
        print(
            f"dataset          : "
            f"{dataset}"
        )
        print(
            f"입력 파일       : "
            f"{workbook_path}"
        )
        print(
            f"출력 파일       : "
            f"{output_path}"
        )
        print(
            "Recall 방식      : "
            "Hybrid Evidence Matching "
            "+ Combined Top-K Context"
        )
        print(
            f"RAGAS            : "
            f"{'실행 안 함' if args.skip_ragas else '실행'}"
        )
        print(
            "Metric Timeout   : "
            f"{args.metric_timeout}s"
        )
        print(
            "Resume           : "
            f"{args.resume}"
        )
        print(
            "평가 모드       : "
            + (
                "Factual Correctness only"
                if args.factual_only
                else "RAGAS 핵심 3개 metrics"
            )
        )
        print(
            "Factual Prompt   : "
            + (
                "한국어 Adaptation"
                if args.adapt_factual_korean
                else "기본 Prompt"
            )
        )

        if selected_question_ids:
            print(
                "선택 문항       : "
                + ", ".join(
                    sorted(
                        selected_question_ids
                    )
                )
            )
        else:
            print(
                "선택 문항       : 전체"
            )

        print("=" * 78)

        processed = 0
        resume_skipped = 0
        found_question_ids: set[
            str
        ] = set()

        metric_time_totals: dict[
            str,
            float,
        ] = {
            "recall": 0.0,
            "faithfulness": 0.0,
            "response_relevancy": 0.0,
            "factual_correctness": 0.0,
        }

        evaluation_start = (
            time.perf_counter()
        )

        for row in range(
            2,
            ws.max_row + 1,
        ):
            question_id = str(
                ws.cell(
                    row=row,
                    column=columns[
                        "question_id"
                    ],
                ).value
                or ""
            ).strip().upper()

            if (
                selected_question_ids
                is not None
                and question_id
                not in selected_question_ids
            ):
                continue

            if selected_question_ids is not None:
                found_question_ids.add(
                    question_id
                )

            user_input = str(
                ws.cell(
                    row=row,
                    column=columns[
                        "user_input"
                    ],
                ).value
                or ""
            ).strip()

            if not user_input:
                continue

            # RAGAS 성공 문항 Resume Skip.
            # PARTIAL/FAILED/미평가는 다시 실행한다.
            if (
                args.resume
                and not args.rerun_success
                and not args.skip_ragas
            ):
                current_status = str(
                    ws.cell(
                        row=row,
                        column=ragas_status_col,
                    ).value
                    or ""
                ).strip()

                completed_statuses = {
                    "OK",
                    "OK - FACTUAL_ONLY",
                }

                if (
                    current_status
                    in completed_statuses
                ):
                    resume_skipped += 1
                    print(
                        f"[RESUME] {question_id}: "
                        "기존 RAGAS 성공 결과 유지"
                    )
                    continue

            reference = str(
                ws.cell(
                    row=row,
                    column=columns[
                        "reference"
                    ],
                ).value
                or ""
            ).strip()

            reference_text = str(
                ws.cell(
                    row=row,
                    column=columns[
                        "reference_text"
                    ],
                ).value
                or ""
            ).strip()

            retrieved_raw = (
                ws.cell(
                    row=row,
                    column=columns[
                        "retrieved_contexts"
                    ],
                ).value
            )

            response = str(
                ws.cell(
                    row=row,
                    column=columns[
                        "response"
                    ],
                ).value
                or ""
            ).strip()

            contexts = (
                split_retrieved_contexts(
                    retrieved_raw
                )
            )

            processed += 1

            question_start = (
                time.perf_counter()
            )

            print(
                f"\n[{processed:02d}] "
                f"{question_id}: "
                f"{user_input}"
            )

            # ------------------------------------------------
            # Recall@1 / @3 / @5
            # ------------------------------------------------
            recall_start = (
                time.perf_counter()
            )

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

            recall_elapsed = (
                time.perf_counter()
                - recall_start
            )

            metric_time_totals[
                "recall"
            ] += recall_elapsed

            print(
                "  [TIME] "
                f"{'recall@1/3/5':22s}: "
                f"{recall_elapsed:8.4f}s"
            )

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

            else:
                if r1 == 1:
                    final_rank = rank1
                    final_score = score1
                    final_reason = reason1
                    matched_scope = "Top-1"

                elif r3 == 1:
                    final_rank = rank3
                    final_score = score3
                    final_reason = reason3
                    matched_scope = "Top-3"

                elif r5 == 1:
                    final_rank = rank5
                    final_score = score5
                    final_reason = reason5
                    matched_scope = "Top-5"

                else:
                    final_rank = None
                    final_score = score5
                    final_reason = reason5
                    matched_scope = (
                        "Top-5 미탐지"
                    )

                ws.cell(
                    row=row,
                    column=recall_method_col,
                    value=(
                        "hybrid evidence match"
                        f" | scope={matched_scope}"
                        f" | reason={final_reason}"
                    ),
                )

                ws.cell(
                    row=row,
                    column=recall_rank_col,
                    value=final_rank,
                )

                ws.cell(
                    row=row,
                    column=recall_score_col,
                    value=round(
                        final_score,
                        4,
                    ),
                )

                print(
                    "  Recall@1/3/5   : "
                    f"{r1} / {r3} / {r5}"
                )
                print(
                    "  Match Scope    : "
                    f"{matched_scope}"
                )

                if final_rank is not None:
                    print(
                        "  Match Rank     : "
                        f"{final_rank}"
                    )
                elif (
                    r1 == 1
                    or r3 == 1
                    or r5 == 1
                ):
                    print(
                        "  Match Rank     : "
                        "복수 Context"
                    )
                else:
                    print(
                        "  Match Rank     : 없음"
                    )

                print(
                    "  Match Reason   : "
                    f"{final_reason}"
                )
                print(
                    "  Match Score    : "
                    f"{final_score:.4f}"
                )

            # ------------------------------------------------
            # RAGAS
            # ------------------------------------------------
            if args.skip_ragas:
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

                (
                    scores,
                    metric_times,
                ) = await score_one_with_ragas(
                    scorers=scorers,
                    user_input=user_input,
                    reference=reference,
                    response=response,
                    contexts=contexts,
                    factual_only=(
                        args.factual_only
                    ),
                    metric_timeout_seconds=(
                        args.metric_timeout
                    ),
                )

                for (
                    metric_name,
                    elapsed,
                ) in metric_times.items():
                    metric_time_totals[
                        metric_name
                    ] += elapsed

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

                if args.factual_only:
                    if (
                        scores[
                            "factual_correctness"
                        ]
                        is not None
                    ):
                        status = (
                            "OK - FACTUAL_ONLY"
                        )
                    else:
                        status = (
                            "FAILED - FACTUAL_ONLY"
                        )

                elif all(
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

            question_elapsed = (
                time.perf_counter()
                - question_start
            )

            print(
                "  [TIME] "
                f"{'QUESTION TOTAL':22s}: "
                f"{question_elapsed:8.2f}s"
            )

            # 문항 1개가 끝날 때마다 저장한다.
            # metric timeout이 발생해도 PARTIAL/FAILED 상태가 저장된다.
            wb.save(
                output_path
            )

        if selected_question_ids is not None:
            missing_question_ids = (
                selected_question_ids
                - found_question_ids
            )

            if missing_question_ids:
                print(
                    "\n[경고] Excel에서 찾지 못한 문항: "
                    + ", ".join(
                        sorted(
                            missing_question_ids
                        )
                    )
                )

        final_stats = (
            collect_final_statistics(
                ws=ws,
                columns=columns,
                selected_question_ids=(
                    selected_question_ids
                ),
                factual_only=(
                    args.factual_only
                ),
            )
        )

        evaluation_elapsed = (
            time.perf_counter()
            - evaluation_start
        )

        print(
            "\n"
            + "=" * 78
        )
        print("평가 완료")
        print(
            "이번 실행 처리 질문 : "
            f"{processed}"
        )
        print(
            "Resume Skip        : "
            f"{resume_skipped}"
        )
        print(
            "결과 내 전체 질문 : "
            f"{final_stats['total_questions']}"
        )

        answerable = int(
            final_stats[
                "answerable"
            ]
        )

        recall_hits = (
            final_stats[
                "recall_hits"
            ]
        )

        if answerable > 0:
            for k in (
                1,
                3,
                5,
            ):
                hits = int(
                    recall_hits[k]
                )

                recall_value = (
                    hits
                    / answerable
                )

                print(
                    f"Recall@{k:<9d}: "
                    f"{hits}/{answerable} "
                    f"= {recall_value:.4f} "
                    f"({recall_value * 100:.1f}%)"
                )

        if not args.skip_ragas:
            print(
                "\n[RAGAS 평균]"
            )

            ragas_values = (
                final_stats[
                    "ragas_values"
                ]
            )

            for metric_name in (
                "faithfulness",
                "response_relevancy",
                "factual_correctness",
            ):
                if (
                    args.factual_only
                    and metric_name
                    != "factual_correctness"
                ):
                    continue

                values = (
                    ragas_values[
                        metric_name
                    ]
                )

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
            "\n[이번 실행시간 요약]"
        )

        print(
            f"{'Recall@1/3/5 합계':26s}: "
            f"{metric_time_totals['recall']:.2f}s"
        )

        if not args.skip_ragas:
            for metric_name in (
                "faithfulness",
                "response_relevancy",
                "factual_correctness",
            ):
                if (
                    args.factual_only
                    and metric_name
                    != "factual_correctness"
                ):
                    continue

                print(
                    f"{metric_name:26s}: "
                    f"{metric_time_totals[metric_name]:.2f}s"
                )

        print(
            f"{'전체 평가시간':26s}: "
            f"{evaluation_elapsed:.2f}s "
            f"({evaluation_elapsed / 60:.1f}분)"
        )

        if processed > 0:
            print(
                f"{'이번 처리 문항당 평균':26s}: "
                f"{evaluation_elapsed / processed:.2f}s"
            )

        print(
            f"\n결과 파일       : "
            f"{output_path}"
        )
        print("=" * 78)

    finally:
        wb.close()


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
        default=None,
        help=(
            "평가셋 코드. GC/BD/DH/GP 등 어떤 코드도 "
            "코드 수정 없이 사용할 수 있습니다."
        ),
    )

    parser.add_argument(
        "--xlsx",
        default=None,
        help=(
            "평가 입력 Excel 경로. 생략하면 dataset의 "
            "가장 최근 ACTUAL_RUN result를 자동 탐색합니다."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "평가 결과 Excel 저장 경로. 생략하면 "
            "입력 result 이름의 _scored.xlsx를 사용합니다."
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
            "RAGAS는 실행하지 않고 Recall@K만 계산합니다."
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

    parser.add_argument(
        "--ragas-request-timeout",
        type=float,
        default=(
            DEFAULT_RAGAS_REQUEST_TIMEOUT_SECONDS
        ),
        help=(
            "OpenAI 호환 Judge HTTP 요청 timeout(초)."
        ),
    )

    parser.add_argument(
        "--metric-timeout",
        type=int,
        default=(
            DEFAULT_METRIC_TIMEOUT_SECONDS
        ),
        help=(
            "RAGAS metric 1개당 최대 대기시간(초). "
            "기본 300초. 초과 시 해당 metric만 실패 처리하고 "
            "다음 metric/문항으로 진행합니다."
        ),
    )

    parser.add_argument(
        "--factual-only",
        action="store_true",
        help=(
            "Factual Correctness만 계산합니다."
        ),
    )

    parser.add_argument(
        "--question-ids",
        default=None,
        help=(
            "Q002,Q003,Q007처럼 쉼표로 지정. "
            "생략하면 전체 문항."
        ),
    )

    parser.add_argument(
        "--adapt-factual-korean",
        action="store_true",
        help=(
            "FactualCorrectness claim/NLI prompt를 "
            "한국어로 adaptation합니다."
        ),
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "output scored.xlsx가 있으면 그 파일에서 이어서 실행합니다. "
            "ragas_status=OK 문항은 건너뛰고 "
            "PARTIAL/FAILED/미평가 문항을 다시 평가합니다."
        ),
    )

    parser.add_argument(
        "--rerun-success",
        action="store_true",
        help=(
            "--resume 상태에서도 기존 OK 문항을 다시 평가합니다."
        ),
    )

    args = parser.parse_args()

    if args.metric_timeout <= 0:
        parser.error(
            "--metric-timeout은 1 이상이어야 합니다."
        )

    if (
        args.ragas_request_timeout
        <= 0
    ):
        parser.error(
            "--ragas-request-timeout은 0보다 커야 합니다."
        )

    return args


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
            "\n사용자가 평가를 중단했습니다. "
            "완료된 문항은 결과 파일에 저장되어 있습니다."
        )
        sys.exit(130)

    except Exception as exc:
        print(
            "\n평가 중 오류가 발생했습니다:\n"
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()