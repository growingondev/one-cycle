from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from evaluation.dataset_resolver import (
    default_scored_path,
    normalize_dataset_id,
    resolve_result_xlsx,
)


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



# ============================================================
# Recall 판정 기준
# ============================================================

NUMERIC_COVERAGE_THRESHOLD = 0.70
TOKEN_COVERAGE_THRESHOLD = 0.45

NO_NUMBER_TOKEN_THRESHOLD = 0.55
NO_NUMBER_SIMILARITY_THRESHOLD = 0.35

HIGH_SIMILARITY_THRESHOLD = 0.75


# ============================================================
# Dataset
# ============================================================

# Dataset ID는 소스에 하드코딩하지 않는다.
# evaluation/dataset_resolver.py의 규칙을 그대로 사용한다.
#
# 기본 결과 파일명 규칙:
#   <DATASET>_FINAL_V<version>_ACTUAL_RUN_<run>_result.xlsx
#
# --xlsx를 직접 지정하면 해당 파일을 사용하고,
# --dataset만 지정하면 evaluation/results/에서 해당 Dataset의
# 최신 ACTUAL_RUN result.xlsx를 자동 탐색한다.
#
# 따라서 새 Dataset을 추가할 때 evaluate_metrics.py의 alias를
# 수정할 필요가 없다.


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
    Rank별 Context 리스트로 변환한다.
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
    """
    Recall 비교용 정규화.
    """

    text = str(text).lower()

    # 2026 → 26
    text = re.sub(
        r"\b20(\d{2})\b",
        r"\1",
        text,
    )

    # 10시 → 10:00
    text = re.sub(
        r"(\d{1,2})\s*시",
        r"\1:00",
        text,
    )

    # 공백 제거
    text = re.sub(
        r"\s+",
        "",
        text,
    )

    # 한글 / 영어 / 숫자만 유지
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
    숫자 표기 통일.

    08 → 8
    08.0 → 8
    """

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
    """
    날짜 / 시간 / 금액 / 면적 / 나이 등의
    숫자 정보를 추출한다.
    """

    text = str(
        text
    )

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
        normalize_number(
            number
        )
        for number
        in numbers
    ]


# ============================================================
# 토큰 추출
# ============================================================


def extract_tokens(
    text: str,
) -> list[str]:
    """
    reference_text에서 의미 비교에 사용할
    핵심 토큰을 추출한다.
    """

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


# ============================================================
# Token Coverage
# ============================================================


def token_coverage(
    reference_text: str,
    context: str,
) -> float:
    """
    reference_text의 핵심 토큰 중
    context에 포함된 비율을 계산한다.
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
    reference_text의 숫자 정보가
    context 안에 얼마나 존재하는지 계산한다.

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
    긴 Context의 일부 구간이
    reference_text와 얼마나 유사한지 계산한다.
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


# ============================================================
# Evidence 판정
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
    Context 안에 reference_text의 정답 근거가
    존재하는지 판단한다.

    판정 순서
    --------
    1. 정규화 후 완전 포함
    2. 숫자 + 핵심 토큰 기반 사실 일치
    3. 숫자가 없는 문장의 의미 토큰 일치
    4. 높은 문자열 유사도
    5. 복합 Evidence 보완 판정
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
    # 1. 정규화 후 완전 포함
    # ========================================================

    if ref_norm in ctx_norm:
        return (
            True,
            1.0,
            "normalized_exact_containment",
        )

    # ========================================================
    # 개별 점수 계산
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
    # 2. 숫자 정보가 있는 정답
    # ========================================================

    if numeric_score is not None:

        # 숫자 대부분 + 핵심 단어 충분히 일치
        if (
            numeric_score
            >= NUMERIC_COVERAGE_THRESHOLD
            and word_score
            >= TOKEN_COVERAGE_THRESHOLD
        ):
            score = (
                0.55 * numeric_score
                + 0.35 * word_score
                + 0.10 * similarity
            )

            return (
                True,
                score,
                "numeric_fact_match",
            )

        # 숫자가 거의 전부 일치
        if (
            numeric_score >= 0.95
            and similarity >= 0.35
        ):
            score = (
                0.60 * numeric_score
                + 0.40 * similarity
            )

            return (
                True,
                score,
                "numeric_full_match",
            )

        # ----------------------------------------------------
        # 숫자 근거 보완 판정
        #
        # 날짜/시간/금액 등 핵심 숫자가 매우 잘 맞고,
        # 텍스트 쪽 근거도 조금이라도 있어야 HIT
        # ----------------------------------------------------

        if (
            numeric_score >= 0.80
            and (
                word_score >= 0.25
                or similarity >= 0.25
            )
        ):
            score = (
                0.60 * numeric_score
                + 0.25 * word_score
                + 0.15 * similarity
            )

            return (
                True,
                score,
                "numeric_evidence_match",
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
                0.70 * word_score
                + 0.30 * similarity
            )

            return (
                True,
                score,
                "semantic_token_match",
            )

        if (
            word_score >= 0.70
            and similarity >= 0.25
        ):
            score = (
                0.75 * word_score
                + 0.25 * similarity
            )

            return (
                True,
                score,
                "strong_token_match",
            )

    # ========================================================
    # 4. 문자열 자체가 매우 유사
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
    # 5. 복합 Evidence 보완 판정
    #
    # 숫자 하나만 우연히 겹치는 것을 막기 위해
    # 서로 다른 Evidence가 최소 2개 이상
    # 일정 수준 이상이어야 한다.
    # ========================================================

    evidence_count = 0

    if word_score >= 0.50:
        evidence_count += 1

    if similarity >= 0.40:
        evidence_count += 1

    if (
        numeric_score is not None
        and numeric_score >= 0.70
    ):
        evidence_count += 1

    if evidence_count >= 2:

        if numeric_score is None:
            final_score = (
                0.65 * word_score
                + 0.35 * similarity
            )

        else:
            final_score = (
                0.45 * numeric_score
                + 0.35 * word_score
                + 0.20 * similarity
            )

        if final_score >= 0.55:
            return (
                True,
                final_score,
                "multi_evidence_match",
            )

    # ========================================================
    # 6. 실패
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
    Recall@K 계산.

    1. Top-K의 Context를 개별적으로 검사
    2. 개별 Context에서 실패하면
       Top-K 전체를 합쳐서 다시 검사

    비교형 / 복합형 질문에서
    정답 근거가 여러 청크에 나뉜 경우 대응.
    """

    if not reference_text.strip():
        return (
            None,
            None,
            0.0,
            "no_reference_text",
        )

    top_k_contexts = contexts[:k]

    if not top_k_contexts:
        return (
            0,
            None,
            0.0,
            "no_contexts",
        )

    best_score = 0.0
    best_reason = "no_match"

    # ========================================================
    # 1. 개별 Context 검사
    # ========================================================

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

    # ========================================================
    # 2. Top-K Context 통합 검사
    # ========================================================

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
        best_score = combined_score
        best_reason = combined_reason

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

    # ========================================================
    # 3. Top-K 전체에서도 실패
    # ========================================================

    return (
        0,
        None,
        best_score,
        best_reason,
    )


# ============================================================
# 선택 평가 문항 파싱
# ============================================================


def parse_question_ids(
    value: str | None,
) -> set[str] | None:
    """
    --question-ids로 전달된 문항 ID를 set으로 변환한다.

    예:
    Q002,Q003,Q007
        ↓
    {"Q002", "Q003", "Q007"}

    옵션을 사용하지 않으면 None을 반환하여
    기존처럼 전체 문항을 평가한다.
    """

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


    if missing:
        raise RuntimeError(
            "RAGAS 평가에 필요한 "
            "패키지가 없습니다.\n\n"
            "다음 명령으로 설치하세요:\n\n"
            f"pip install {' '.join(missing)}"
        )


# ============================================================
# OneCycle Factual Correctness 보완 기준
# ============================================================

# Claim 분해와 NLI 판정에는 각 단계에서 필요한 지침만 분리하여 적용한다.
PROJECT_CLAIM_DECOMPOSITION_GUIDELINES = """
[OneCycle LH 공고문 claim 분해 기준]

입력 문장을 검증 가능한 최소 사실 단위로 분해하세요.

- 주택형, 공급계층, 대상, 날짜, 시작·종료 시간, 금액, 비율, 기간,
  모집 인원, 자격 조건, 예외 조건, 가능·불가능 결론을 서로 분리합니다.
- 하나의 claim에는 하나의 대상과 하나의 핵심 사실만 포함합니다.
- 날짜와 시간, 기본값과 전환값, 일반 기준과 예외 기준을 합치지 않습니다.
- 문장에 실제로 적힌 사실만 추출하며 추론하거나 새 사실을 만들지 않습니다.
- 인사말, 안내 문구, 근거 없는 수식어는 claim으로 만들지 않습니다.

예시:
"서류제출 기간은 2027년 1월 12일부터 1월 14일까지이며 마감은 18시입니다."
→ "서류제출 시작일은 2027년 1월 12일이다."
→ "서류제출 종료일은 2027년 1월 14일이다."
→ "서류제출 마감 시간은 18시이다."

"기본 월임대료는 187,000원이고 보증금 감액 시 264,000원입니다."
→ "기본 월임대료는 187,000원이다."
→ "보증금 감액 시 월임대료는 264,000원이다."
""".strip()


PROJECT_NLI_GUIDELINES = """
[OneCycle LH 공고문 사실 일치 판정 기준]

reference claim과 response claim의 표면 문자열이 아니라 의미, 대상, 조건,
핵심 값을 비교하세요.

1. 의미와 값이 같으면 표현·어순·존댓말·조사·띄어쓰기가 달라도 일치입니다.
2. 날짜, 시간, 금액은 단위를 정규화한 뒤 비교합니다.
   - 2027년 1월 12일 = 2027.01.12 = '27.1.12
   - 17:00 = 17시 = 오후 5시
   - 12,300만원 = 123,000,000원
   - 181,000원 = 181천원
3. 다음 LH 표현은 같은 의미입니다.
   - 예비자 = 예비입주자
   - 금회 모집 = 이번 모집
   - 월세 = 월임대료
   - 온라인 신청 = 인터넷 신청
   - 서류 대상자 = 서류제출대상자
4. reference의 핵심 사실이 긴 response의 중간이나 마지막에 있어도 일치입니다.
5. 질문과 모범답안에 모순되지 않는 추가 설명은 핵심 claim의 일치를 취소하지
   않습니다. 추가 설명 자체가 틀리면 그 claim만 불일치로 판정합니다.
6. 적용 대상이나 조건이 다르면 숫자가 같아도 불일치입니다.
   - 대학생과 청년
   - 기본 기준과 출산자녀 가산 기준
   - 기본 임대료와 보증금 전환 임대료
   - 서류제출대상자 발표와 최종 당첨자 발표
7. 기준값이 맞더라도 최종 가능·불가능 또는 초과·이하 결론이 틀리면
   결론 claim은 불일치입니다.

판정 예시:
- reference: "현장접수는 2027년 1월 12일 14시 이후 시작한다."
  response: "현장접수 시작은 2027년 1월 12일 오후 2시 이후입니다."
  → 일치
- reference: "기본 월임대료는 181,000원이다."
  response: "전환 임대료도 설명한 뒤 기본 월임대료는 181천원이라고 답했다."
  → 기본 월임대료 claim은 일치
- reference: "2억 4천만원은 기본 자산 기준 2억 3천만원을 초과한다."
  response: "기준을 초과한다고도 하고 예외 기준에서는 이하라고 결론냈다."
  → 초과 claim이 포함되어도 상충되는 결론 claim은 별도 불일치
""".strip()


# Answer Quality 평가 기준 버전.
# 실행 로그에서 실제 적용된 프롬프트를 확인하기 위해 별도로 기록한다.
ANSWER_QUALITY_PROMPT_VERSION = "V5.1-AUTO-GUARDRAILS"


# 실제 평가셋 문항과 정답값을 few-shot 예시에 사용하지 않는다.
ANSWER_QUALITY_PROMPT = """
당신은 LH 임대주택 공고문 질의응답의 품질을 판정하는 평가자입니다.

아래 입력의 역할은 서로 다릅니다.

- REQUIRED_FACTS: 질문에 반드시 답해야 하는 필수 정답 목록
- REFERENCE: 사람이 작성한 자연어 모범답안
- SOURCE_EVIDENCE: 공고문에서 사람이 지정한 원문 근거
- RESPONSE: 평가할 챗봇 답변

각 입력의 역할을 바꾸거나 혼동하지 마세요.

[입력 우선순위]

1. 필수 정답의 범위와 누락 여부는 REQUIRED_FACTS만을 기준으로 판정합니다.
2. REFERENCE는 REQUIRED_FACTS의 의미와 질문 맥락을 이해하는 보조 자료입니다.
3. SOURCE_EVIDENCE는 RESPONSE에 추가된 설명의 사실 여부를 확인하는
   근거로만 사용합니다.
4. SOURCE_EVIDENCE의 모든 내용을 RESPONSE가 답해야 하는 필수 사실로
   간주하지 마세요.
5. REQUIRED_FACTS와 다른 입력이 충돌하면 REQUIRED_FACTS를 필수 정답의
   기준으로 우선 적용하고, 판정 사유에 충돌 내용을 밝히세요.

[판정 순서]

1. REQUIRED_FACTS에 적힌 필수 사실을 항목별로 확인합니다.
2. 각 필수 사실이 RESPONSE에 실제로 포함되어 있는지 확인합니다.
3. 날짜, 시간, 금액, 비율, 연령, 기간, 대상, 조건과 결론을 비교합니다.
4. 각 핵심값에 대응하는 문구가 RESPONSE에 실제로 존재하는지 확인합니다.
5. 누락, 모호한 결론, 잘못된 적용 대상과 상충되는 추가 설명을 확인합니다.
6. 아래 기준에 따라 PASS, PARTIAL, FAIL 중 하나를 선택합니다.

[RESPONSE 실제 포함 여부 확인]

- REQUIRED_FACTS에만 있는 날짜, 시간, 금액 또는 조건을 RESPONSE에도 있다고
  추론하지 마세요.
- RESPONSE에 없는 값을 문맥이나 상식으로 보완하지 마세요.
- RESPONSE에 날짜만 있으면 시간이 포함된 것으로 판단하지 마세요.
- RESPONSE에 기준값만 있으면 가능·불가능 결론까지 말했다고 판단하지 마세요.
- 같은 숫자가 있어도 대상, 계층, 주택형, 일정 명칭 또는 적용 조건이 다르면
  완전히 일치한 것으로 판단하지 마세요.

[PASS]

다음 조건을 모두 만족하면 PASS입니다.

- 질문에서 요구한 핵심 사실과 결론이 모두 정확합니다.
- REQUIRED_FACTS의 모든 날짜, 시간, 금액, 대상, 조건과 결론이 RESPONSE에
  존재합니다.
- 핵심 정답이 답변의 중간이나 마지막에 있어도 인정합니다.
- 답변이 길거나 추가 설명이 있어도 핵심 정답과 모순되지 않으면 감점하지 않습니다.
- “직접적이지 않다”, “답변이 길다”, “부가 설명이 있다”는 이유만으로
  PARTIAL로 판정하지 않습니다.
- 날짜, 시간과 금액의 표기 단위가 달라도 실제 값이 같으면 인정합니다.
- 핵심값에 연결된 대상, 계층, 주택형과 일정 명칭이 정확합니다.
- 가능·불가능 또는 초과·이하를 묻는 질문에는 확정적인 결론이 있습니다.
- 추가 설명에 객관적으로 틀린 값, 잘못된 대상 또는 핵심 정답과 상충하는
  조건이 없습니다.

예:
- 2027년 1월 12일 = 2027.01.12
- 14:00 = 오후 2시
- 12,300만원 = 123,000,000원
- 181,000원 = 181천원

REQUIRED_FACTS의 필수 사실이 RESPONSE에 모두 포함되어 있고
서로 모순되지 않는다면 반드시 PASS로 판정하세요.

[PARTIAL]

다음 중 하나에 해당하면 PARTIAL입니다.

- 여러 핵심 사실 중 일부만 정확하고 나머지가 실제로 누락되었습니다.
- 기준값은 정확하지만 질문이 요구한 가능·불가능, 초과·이하 등의
  최종 결론이 빠졌습니다.
- 답변에 일부 관련 정보는 있지만 질문에 직접 필요한 핵심값이 빠졌습니다.
- “어려울 수 있습니다”, “가능할 수 있습니다”처럼 질문이 요구한 확정 결론을
  가능성 표현으로 모호하게 답했습니다.
- 정확한 핵심값은 포함했지만 일반 기준을 특정 예외 계층이나 대상에만
  적용되는 것처럼 잘못 한정했습니다.
- 정확한 날짜나 금액은 포함했지만 발표 종류, 계층, 주택형 또는 적용 조건을
  잘못 연결했습니다.
- 핵심 정답 일부는 정확하지만 추가 설명에 객관적으로 틀린 값, 잘못된 대상
  또는 핵심 정답과 상충하는 조건이 있습니다.
- 정답과 상충되는 설명이 있어도 질문에 대한 올바른 핵심 사실이 하나 이상
  명확하게 포함되어 있습니다.
- 다중 질문에서 일부는 정확하지만 다른 일부에 대해 “확인할 수 없다”고
  답했습니다.
- 기본값과 전환값을 함께 제시했지만 둘의 구분이 불명확합니다.

답변이 길거나 추가 설명이 있다는 이유만으로 PARTIAL을 선택하지 마세요.

PARTIAL은 완전히 틀린 답변이 아닙니다. 질문에 필요한 핵심 사실 중
의미 있는 일부가 정확하지만 누락, 모호함 또는 오류가 함께 있는 경우입니다.

[FAIL]

다음 중 하나에 해당하면 FAIL입니다.

- 질문에 필요한 핵심 사실이 하나도 정확하게 포함되지 않았습니다.
- 핵심 날짜, 시간, 금액, 대상 또는 조건을 전부 잘못 답했습니다.
- 질문의 최종 결론과 반대되는 결론만 제시했습니다.
- 단일 사실 질문에서 다른 계층, 주택형, 일정 또는 금액만 답했습니다.
- 단일 사실 질문에서 정답이 존재하는데 “확인할 수 없다”, “알 수 없다”,
  “정보가 없다”고만 답했습니다.
- 답변이 질문과 관계없어 실질적인 정답을 제공하지 못했습니다.
- 다른 계층, 주택형, 일정 또는 예외 대상의 사실만 제시하고 QUESTION이
  요구한 대상의 값이나 결론은 하나도 제시하지 않았습니다.

RESPONSE에 올바른 핵심 사실이 하나 이상 포함되어 있다면 나머지 내용에
누락이나 오류가 있더라도 PARTIAL 가능성을 먼저 검토하세요.

단, QUESTION이 요구하지 않은 다른 계층, 주택형, 일정 또는 예외 대상의
사실은 질문에 대한 올바른 핵심 사실로 계산하지 마세요.

[최우선 판정 원칙]

1. 필수 사실의 범위는 REFERENCE나 SOURCE_EVIDENCE 전체가 아니라
   REQUIRED_FACTS가 결정합니다.

REFERENCE나 SOURCE_EVIDENCE에 질문보다 자세한 날짜, 출생일, 적용 근거 또는 보충 조건이
포함되어 있어도, QUESTION이 해당 세부정보를 요구하지 않았다면
RESPONSE의 필수 답변으로 간주하지 마세요.

QUESTION이 요구한 핵심 사실과 결론이 정확하면,
REFERENCE의 보충 설명을 생략했더라도 PASS로 판정하세요.

2. 다음 순서로 판정합니다.

- 모든 핵심 사실이 정확하고 오류가 없음 → PASS
- 정확한 핵심 사실이 하나 이상 있지만 누락·모호함·오류가 있음 → PARTIAL
- 정확한 핵심 사실이 없거나 전체 결론이 틀림 → FAIL

3. QUESTION에 예외 조건이 명시되지 않았다면 기본 기준으로 답해야 합니다.

RESPONSE가 일반 기준을 특정 예외 대상에 한정하거나 기본 기준과 다른
적용 대상을 제시하면 PASS로 판정하지 마세요. 올바른 핵심값도 포함되어
있다면 PARTIAL, 올바른 핵심값이 없다면 FAIL입니다.

예시 — PASS

QUESTION:
60세 이상만 신청할 수 있나요?

REFERENCE:
신청자는 만 60세 이상이어야 하며, 기준일에 따른 출생일 조건도 적용됩니다.

RESPONSE:
네, 만 60세 이상인 사람이 신청할 수 있습니다.

판정:
PASS

이유:
QUESTION은 최소 연령을 묻고 있습니다. RESPONSE가 만 60세 이상이라는
핵심 조건을 정확히 답했으므로 출생일 기준을 생략했더라도 PASS입니다.


예시 — PARTIAL

QUESTION:
총자산이 2억 4천만원이면 기본 자산 기준을 넘나요?

REFERENCE:
기본 자산 기준 2억 3천만원을 초과합니다.

RESPONSE:
기본 기준은 초과하지만 특정 예외 조건에서는 기준 이하입니다.

판정:
PARTIAL

이유:
기본 기준을 초과한다는 올바른 핵심 사실은 포함했지만, 질문에 없는 예외
조건과 반대 결론을 함께 제공하여 사용자를 혼동시키므로 PARTIAL입니다.

[추가 정보 처리]

- RESPONSE에만 존재하는 추가 정보를 REFERENCE의 필수 조건으로
  잘못 해석하지 마세요.
- RESPONSE의 추가 설명이 REFERENCE와 모순되지 않으면 감점하지 마세요.
- 추가 설명이 잘못됐거나 대상·조건을 오해하게 만들면 PASS가 아닙니다.
- 올바른 핵심 내용과 잘못된 추가 설명이 함께 있으면 PARTIAL입니다.
- 올바른 핵심 내용 없이 잘못된 설명만 있으면 FAIL입니다.

[추가 설명 감점 제한]

- 추가 설명이 있다는 이유만으로 PARTIAL로 판정하지 마세요.
- “사용자를 혼동시킬 수 있다”, “불필요하게 자세하다”, “질문보다 범위가
  넓다”는 추측만으로 감점하지 마세요.
- 추가 설명을 감점하려면 RESPONSE에서 객관적으로 틀린 문장,
  REFERENCE와 상충되는 조건 또는 잘못 연결된 대상을 구체적으로 찾을 수
  있어야 합니다.
- 추가 설명이 정확하고 핵심 정답과 모순되지 않으면 설명이 길거나 여러
  조건을 함께 안내하더라도 반드시 PASS입니다.
- 기본값을 명확히 제시한 뒤 전환값, 가산 기준 또는 예외 기준을 별도로
  구분하여 설명한 경우, 추가 정보가 정확하면 PASS입니다.
- 추가 정보가 실제로 틀렸는지 판단할 근거가 REFERENCE와 QUESTION에 없다면
  틀렸다고 추측하지 말고 핵심 정답의 충족 여부로 판정하세요.
- 판정 사유에서 구체적으로 잘못된 문구를 지적할 수 없다면 추가 설명을
  이유로 PARTIAL을 선택하지 마세요.

[정답 일부의 인정 범위]

- QUESTION이 요구하지 않은 다른 계층, 다른 주택형, 다른 일정 또는 예외
  조건의 정보는 질문에 대한 올바른 핵심 사실로 계산하지 마세요.
- RESPONSE에 관련 정보가 있더라도 QUESTION이 요구한 대상의 값이나 결론이
  하나도 없다면 PARTIAL이 아니라 FAIL입니다.
- QUESTION이 요구한 핵심값을 정확히 답한 뒤 다른 정확한 정보를 별도로
  안내한 경우에는 PASS입니다.

[대상·명칭·결론 확인]

- 일반 계층과 특정 예외 대상은 동일하지 않습니다.
- 기본 기준과 가산·완화 기준은 동일하지 않습니다.
- 기본 임대료와 보증금 전환 후 임대료는 동일하지 않습니다.
- 서류제출대상자 발표와 최종 당첨자 발표는 동일하지 않습니다.
- “신청할 수 없습니다”와 “신청이 어려울 수 있습니다”는 동일하지 않습니다.
- “신청할 수 있습니다”와 “신청할 수도 있습니다”는 동일하지 않습니다.

정답 숫자가 같아도 대상, 명칭 또는 결론이 다르면 PASS로 판정하지 마세요.

[판정 전 확인]

판정하기 전에 내부적으로 다음 세 가지를 확인하세요.

1. REQUIRED_FACTS에 명시된 질문의 필수 핵심값
2. RESPONSE에서 실제로 발견한 대응 문구와 값
3. 실제로 누락되거나 틀린 핵심값
4. 적용 대상, 계층, 주택형과 일정 명칭의 일치 여부
5. 가능·불가능 또는 초과·이하 결론의 확정성
6. 객관적으로 틀리거나 핵심 정답과 상충하는 추가 설명의 존재 여부

PASS를 선택하기 전에 REQUIRED_FACTS의 모든 핵심값에 대해 RESPONSE 안의
대응 문구를 실제로 확인하세요. 하나라도 누락됐거나 잘못 연결되어 있으면
PASS를 선택하지 마세요.

판정 사유에는 실제 REFERENCE와 RESPONSE의 내용을 근거로
어떤 핵심값이 일치하거나 누락되었는지 짧고 구체적으로 설명하세요.

추가 설명 때문에 PARTIAL 또는 FAIL을 선택했다면 RESPONSE의 어느 문구가
어떤 값·대상·조건과 객관적으로 충돌하는지 반드시 판정 사유에 밝히세요.

[SOURCE_EVIDENCE 사용 기준]

- SOURCE_EVIDENCE는 평가 대상 공고문에서 추출한 정답 근거입니다.
- REQUIRED_FACTS는 질문에 대한 필수 답변의 충족 여부를 판단합니다.
- REFERENCE는 REQUIRED_FACTS의 의미와 질문 맥락을 이해하는 보조 자료입니다.
- SOURCE_EVIDENCE는 RESPONSE의 추가 설명이 원문과 일치하는지 확인하는 데
  사용합니다.
- RESPONSE의 추가 설명이 SOURCE_EVIDENCE와 명확히 모순되면 감점합니다.
- SOURCE_EVIDENCE에 관련 정보가 없다는 이유만으로 RESPONSE의 추가 설명을
  틀렸다고 추정하지 마세요.
- 검색된 retrieved_contexts가 아니라 사람이 지정한 reference_text를
  기준 근거로 사용합니다.

<QUESTION>
{question}
</QUESTION>

<REQUIRED_FACTS>
{required_facts}
</REQUIRED_FACTS>

<REFERENCE>
{reference}
</REFERENCE>

<SOURCE_EVIDENCE>
{reference_text}
</SOURCE_EVIDENCE>

<RESPONSE>
{response}
</RESPONSE>
""".strip()


class BoundDiscreteMetric:
    """DiscreteMetric에 평가용 LLM을 미리 결합한 얇은 래퍼."""

    def __init__(
        self,
        metric: Any,
        llm: Any,
    ) -> None:
        self.metric = metric
        self.llm = llm

    async def ascore(
        self,
        **kwargs: Any,
    ) -> Any:
        return await self.metric.ascore(
            llm=self.llm,
            **kwargs,
        )


def append_project_factual_guidelines(
    prompt_obj: Any,
    guidelines: str,
) -> Any:
    """
    RAGAS prompt 객체의 기존 instruction을 유지하면서
    OneCycle용 판정 기준을 뒤에 추가한다.

    RAGAS 버전에 따라 Pydantic model_copy 또는 일반 setattr을 사용한다.
    """
    current_instruction = str(
        getattr(
            prompt_obj,
            "instruction",
            "",
        )
        or ""
    ).strip()

    updated_instruction = (
        current_instruction
        + "\n\n"
        + guidelines
    ).strip()

    # Pydantic v2 계열
    if hasattr(
        prompt_obj,
        "model_copy",
    ):
        try:
            return prompt_obj.model_copy(
                update={
                    "instruction":
                        updated_instruction,
                }
            )
        except Exception:
            pass

    # 일반 객체 / mutable model
    try:
        setattr(
            prompt_obj,
            "instruction",
            updated_instruction,
        )
        return prompt_obj
    except Exception as exc:
        raise RuntimeError(
            "OneCycle Factual Correctness 보완 프롬프트를 "
            "RAGAS prompt 객체에 적용하지 못했습니다."
        ) from exc


# ============================================================
# RAGAS Scorer 생성
# ============================================================


async def build_ragas_scorers(
    base_url: str,
    api_key: str,
    model: str,
    adapt_factual_korean: bool = False,
    use_project_factual_prompt: bool = False,
    factual_only: bool = False,
    factual_mode: str = "f1",
    factual_atomicity: str = "low",
    factual_coverage: str = "low",
    use_answer_quality: bool = False,
    answer_quality_only: bool = False,
) -> dict[str, Any]:

    from openai import AsyncOpenAI

    from ragas.llms import (
        llm_factory,
    )

    from ragas.metrics.collections import Faithfulness, FactualCorrectness

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
        max_tokens=4096,
        temperature=0.0,
    )

    scorers: dict[str, Any] = {}

    # Answer Quality만 실행하는 경우에는 Factual Correctness를 만들지 않는다.
    # 이를 통해 보정 문항을 짧은 시간 안에 반복 검증할 수 있다.
    if not answer_quality_only:
        factual_correctness = FactualCorrectness(
            llm=llm,
            mode=factual_mode,
            atomicity=factual_atomicity,
            coverage=factual_coverage,
        )

    if adapt_factual_korean and not answer_quality_only:

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

    if use_project_factual_prompt and not answer_quality_only:

        factual_correctness.prompt = (
            append_project_factual_guidelines(
                factual_correctness.prompt,
                PROJECT_CLAIM_DECOMPOSITION_GUIDELINES,
            )
        )

        factual_correctness.nli_prompt = (
            append_project_factual_guidelines(
                factual_correctness.nli_prompt,
                PROJECT_NLI_GUIDELINES,
            )
        )

        print(
            "[RAGAS] OneCycle Factual Correctness "
            "보완 판정 기준 적용"
        )

    if not answer_quality_only:
        scorers["factual_correctness"] = factual_correctness

    if not factual_only and not answer_quality_only:
        scorers[
            "faithfulness"
        ] = Faithfulness(
            llm=llm
        )

    if use_answer_quality or answer_quality_only:
        from ragas.metrics import DiscreteMetric

        answer_quality = DiscreteMetric(
            name="answer_quality",
            prompt=ANSWER_QUALITY_PROMPT,
            allowed_values=[
                "PASS",
                "PARTIAL",
                "FAIL",
            ],
        )

        scorers["answer_quality"] = BoundDiscreteMetric(
            metric=answer_quality,
            llm=llm,
        )

        print(
            "[RAGAS] Answer Quality 프롬프트 적용: "
            f"{ANSWER_QUALITY_PROMPT_VERSION}"
        )

    return scorers


# ============================================================
# Answer Quality 자동 보정
# ============================================================


def extract_time_values(
    text: str,
) -> Counter[int]:
    """시간 표현을 자정 이후 분 단위로 정규화한다."""

    value = str(
        text
        or ""
    )

    times: list[int] = []
    occupied: list[tuple[int, int]] = []

    for match in re.finditer(
        r"(?<!\d)([01]?\d|2[0-3])\s*:\s*([0-5]\d)",
        value,
    ):
        hour = int(match.group(1))
        minute = int(match.group(2))
        times.append(hour * 60 + minute)
        occupied.append(match.span())

    for match in re.finditer(
        r"(?:(오전|오후)\s*)?([01]?\d|2[0-3])\s*시"
        r"(?:\s*([0-5]?\d)\s*분)?",
        value,
    ):
        if any(
            start <= match.start() < end
            for start, end in occupied
        ):
            continue

        meridiem = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3) or 0)

        if meridiem == "오후" and hour < 12:
            hour += 12
        elif meridiem == "오전" and hour == 12:
            hour = 0

        times.append(hour * 60 + minute)

    return Counter(times)


def format_time_value(
    minutes: int,
) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def contains_explicit_refusal(
    response: str,
) -> bool:
    normalized = re.sub(
        r"\s+",
        " ",
        str(response or "").strip(),
    )

    return any(
        pattern in normalized
        for pattern in REFUSAL_PATTERNS
    )


def extract_money_values(
    text: str,
) -> set[int]:
    """원·만원 표기를 원 단위 정수로 정규화한다."""

    value = str(text or "")
    amounts: set[int] = set()

    for match in re.finditer(
        r"(?<![\d,])(\d[\d,]*(?:\.\d+)?)\s*만원",
        value,
    ):
        number = float(
            match.group(1).replace(",", "")
        )
        amounts.add(round(number * 10_000))

    for match in re.finditer(
        r"(?<![\d,])(\d[\d,]*)\s*원",
        value,
    ):
        amounts.add(
            int(match.group(1).replace(",", ""))
        )

    return amounts


def reason_reports_correct_core(
    reason: str,
) -> bool:
    """판정 사유가 하나 이상의 올바른 핵심 사실을 인정하는지 확인한다."""

    value = str(reason or "")

    correct_patterns = (
        r"나머지\s+정보는\s+정확",
        r"(?:기준|정보|사실|내용)(?:만|을|를)?\s*일부\s*(?:포함|정확)",
        r"일부\s*(?:기준|정보|사실|내용).*?(?:포함|정확)",
        r"나이\s+조건은\s+정확",
        r"연령\s+조건은\s+정확",
        r"핵심\s+사실.*?하나\s+이상.*?(?:포함|정확)",
    )

    return any(
        re.search(pattern, value)
        for pattern in correct_patterns
    )


def reason_reports_objective_problem(
    reason: str,
) -> bool:
    """판정 사유가 실제 누락·오류를 명시했는지 제한적으로 확인한다."""

    value = str(reason or "")

    problem_patterns = (
        r"누락되었",
        r"누락됐",
        r"빠졌",
        r"제시하지 않았",
        r"포함하지 않았",
        r"명시하지 않았",
        r"잘못 연결",
        r"잘못 적용",
        r"부정확",
        r"서로 상충",
        r"명확히 모순",
    )

    return any(
        re.search(pattern, value)
        for pattern in problem_patterns
    )


def apply_answer_quality_guardrails(
    *,
    label: str | None,
    reason: str | None,
    question: str,
    required_facts: str,
    reference: str,
    response: str,
) -> tuple[str | None, str | None]:
    """LLM 판정의 객관적인 모순만 규칙 기반으로 보정한다."""

    if label not in {
        "PASS",
        "PARTIAL",
        "FAIL",
    }:
        return label, reason

    adjusted = label
    guard_messages: list[str] = []

    # 정답 전체를 거절하면 FAIL이다. 다중 질문에서 하나 이상의 올바른
    # 핵심 사실을 답하고 나머지만 확인 불가라고 한 경우에는 PARTIAL이다.
    if contains_explicit_refusal(response):
        if reason_reports_correct_core(reason or ""):
            adjusted = "PARTIAL"
            guard_messages.append(
                "일부 핵심 사실은 정확하지만 나머지를 확인 불가로 답함"
            )
        else:
            adjusted = "FAIL"
            guard_messages.append(
                "질문의 핵심 정답을 명시적으로 확인 불가라고 답함"
            )

    # 원·만원 환산값이 같은데 평가 모델이 단위 변환을 잘못하여 FAIL로
    # 판정한 경우, 다른 대상·조건 오류 가능성을 보존하기 위해 PARTIAL로만
    # 복원한다.
    if adjusted == "FAIL":
        required_money = extract_money_values(
            required_facts
        )
        response_money = extract_money_values(
            response
        )
        common_money = required_money & response_money
        reason_claims_money_error = bool(
            re.search(
                r"10배\s+차이|"
                r"금액.*?(?:잘못|불일치|다르)|"
                r"핵심값.*?(?:잘못|불일치|다르)",
                reason or "",
            )
        )

        if common_money and reason_claims_money_error:
            adjusted = "PARTIAL"
            normalized_money = ", ".join(
                f"{amount:,}원"
                for amount in sorted(common_money)
            )
            guard_messages.append(
                "원·만원 환산 결과 일치: "
                f"{normalized_money}"
            )

    if adjusted == "PASS":
        required_times = extract_time_values(
            required_facts
        )
        response_times = extract_time_values(
            response
        )
        missing_times = required_times - response_times

        if missing_times:
            adjusted = "PARTIAL"
            missing_text = ", ".join(
                format_time_value(value)
                for value in sorted(missing_times.elements())
            )
            guard_messages.append(
                "필수 시간 누락: "
                f"{missing_text}"
            )

    if adjusted == "PASS":
        eligibility_question = bool(
            re.search(
                r"신청\s*(?:할\s*수\s*)?(?:있|가능)|"
                r"자격",
                question,
            )
        )
        reference_has_caveat = bool(
            re.search(
                r"다른\s+.*(?:요건|자격).*충족|"
                r"함께\s+충족|"
                r"모든\s+.*(?:요건|자격)",
                required_facts + " " + reference,
            )
        )
        response_overclaims = bool(
            re.search(
                r"(?:네[,\s]*)?(?:신청|지원)\s*(?:이\s*)?가능",
                response,
            )
        )
        response_has_caveat = bool(
            re.search(
                r"다른\s+.*(?:요건|자격).*충족|"
                r"추가\s+.*(?:요건|자격)|"
                r"함께\s+충족|"
                r"모든\s+.*(?:요건|자격)",
                response,
            )
        )

        if (
            eligibility_question
            and reference_has_caveat
            and response_overclaims
            and not response_has_caveat
        ):
            adjusted = "PARTIAL"
            guard_messages.append(
                "일부 자격만 확인한 뒤 전체 신청 가능 여부를 단정함"
            )

    if adjusted == "PASS":
        authentication_question = (
            "금융인증서" in question
            and "공동인증서" in question
        )
        authentication_conflict = (
            "모바일" in response
            and "금융인증서" in response
            and "공동인증서" in response
            and "복사" in response
        )

        if authentication_question and authentication_conflict:
            adjusted = "PARTIAL"
            guard_messages.append(
                "금융인증서 단독 사용 답변과 공동인증서 복사 조건이 상충함"
            )

    if (
        adjusted == "PASS"
        and reason_reports_objective_problem(reason or "")
    ):
        adjusted = "PARTIAL"
        guard_messages.append(
            "판정 사유에 누락·오류가 있으나 PASS로 반환된 모순을 보정함"
        )

    if not guard_messages:
        return adjusted, reason

    guard_reason = (
        "[AUTO_GUARDRAIL] "
        + "; ".join(guard_messages)
    )
    combined_reason = (
        f"{reason}\n{guard_reason}"
        if reason
        else guard_reason
    )

    return adjusted, combined_reason


# ============================================================
# RAGAS 문항 1개 평가
# ============================================================


async def score_one_with_ragas(
    scorers: dict[str, Any],
    user_input: str,
    reference: str,
    required_facts: str,
    reference_text: str,
    response: str,
    contexts: list[str],
    factual_only: bool = False,
    run_faithfulness: bool = True,
    run_factual_correctness: bool = True,
    run_answer_quality: bool = False,
) -> tuple[
    dict[str, Any],
    dict[str, float],
]:

    scores: dict[str, Any] = {
        "faithfulness": None,
        "factual_correctness": None,
        "answer_quality": None,
        "answer_quality_reason": None,
    }

    metric_times: dict[str, float] = {}

    async def safe_score(
        name: str,
        **kwargs,
    ) -> float | None:

        metric_start = time.perf_counter()

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

        finally:
            elapsed = (
                time.perf_counter()
                - metric_start
            )

            metric_times[name] = elapsed

            print(
                "  [TIME] "
                f"{name:22s}: "
                f"{elapsed:8.2f}s"
            )

    async def safe_discrete_score(
        name: str,
        **kwargs: Any,
    ) -> tuple[str | None, str | None]:
        metric_start = time.perf_counter()

        try:
            result = await scorers[name].ascore(
                **kwargs,
            )

            value = str(
                getattr(result, "value", "")
                or ""
            ).strip().upper()

            reason = str(
                getattr(result, "reason", "")
                or ""
            ).strip()

            if value not in {
                "PASS",
                "PARTIAL",
                "FAIL",
            }:
                print(
                    "    [RAGAS 경고] "
                    f"{name}의 허용되지 않은 결과: {value!r}"
                )
                return None, reason or None

            return value, reason or None

        except Exception as exc:
            print(
                "    [RAGAS 경고] "
                f"{name} 실패: {exc}"
            )
            return None, None

        finally:
            elapsed = time.perf_counter() - metric_start
            metric_times[name] = elapsed

            print(
                "  [TIME] "
                f"{name:22s}: "
                f"{elapsed:8.2f}s"
            )

    if (
        not factual_only
        and run_faithfulness
    ):
        scores["faithfulness"] = await safe_score(
            "faithfulness",
            user_input=user_input,
            response=response,
            retrieved_contexts=contexts,
        )

    if run_factual_correctness:
        scores[
            "factual_correctness"
        ] = await safe_score(
            "factual_correctness",
            response=response,
            reference=reference,
        )

    if run_answer_quality:
        (
            scores["answer_quality"],
            scores["answer_quality_reason"],
        ) = await safe_discrete_score(
            "answer_quality",
            question=user_input,
            reference=reference,
            required_facts=required_facts,
            reference_text=reference_text,
            response=response,
        )

        (
            scores["answer_quality"],
            scores["answer_quality_reason"],
        ) = apply_answer_quality_guardrails(
            label=scores["answer_quality"],
            reason=scores["answer_quality_reason"],
            question=user_input,
            required_facts=required_facts,
            reference=reference,
            response=response,
        )

    return scores, metric_times


# ============================================================
# UNANSWERABLE / Correct Rejection
# ============================================================

REFUSAL_PATTERNS = (
    "제공된 LH 공고문에서 확인할 수 없습니다.",
    "확인할 수 없습니다",
    "확인되지 않습니다",
    "찾을 수 없습니다",
    "문서에서 확인할 수 없습니다",
    "문서에서 확인되지 않습니다",
    "공고문에서 확인할 수 없습니다",
    "공고문에서 확인되지 않습니다",
    "해당 정보가 없습니다",
    "관련 정보가 없습니다",
    "근거를 찾을 수 없습니다",
    "답변할 수 없습니다",
    "알 수 없습니다",
)


def score_correct_rejection(
    expected_behavior: str,
    response: str,
) -> tuple[int | None, str]:

    behavior = str(
        expected_behavior
        or ""
    ).strip().lower()

    if behavior not in {
        "refuse",
        "unanswerable",
    }:
        return (
            None,
            "N/A - answerable",
        )

    normalized = re.sub(
        r"\s+",
        " ",
        str(
            response
            or ""
        ).strip(),
    )

    if not normalized:
        return (
            0,
            "empty_response",
        )

    for pattern in REFUSAL_PATTERNS:
        if pattern in normalized:
            return (
                1,
                f"refusal_pattern={pattern}",
            )

    return (
        0,
        "no_refusal_pattern",
    )


# ============================================================
# 전체 평가
# ============================================================


async def evaluate_metrics(
    args: argparse.Namespace,
) -> None:

    # ========================================================
    # Dataset / 입력 결과 파일 자동 탐색
    # ========================================================

    dataset, input_path = resolve_result_xlsx(
        dataset=(
            normalize_dataset_id(args.dataset)
            if args.dataset
            else None
        ),
        xlsx=args.xlsx,
    )

    output_path = (
        Path(args.output).expanduser()
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
    # Excel 읽기 / 자동 Resume
    # ========================================================

    resume_source = input_path

    if (
        output_path.exists()
        and not args.rerun_success
    ):
        resume_source = output_path
        print(
            "[RESUME] 기존 출력 파일에서 이어서 평가합니다."
        )
        print(
            f"[RESUME] 파일: {resume_source}"
        )

    wb = load_workbook(
        resume_source
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
    # 선택 평가 문항
    # ========================================================

    selected_question_ids = (
        parse_question_ids(
            args.question_ids
        )
    )

    found_question_ids: set[str] = set()

    # ========================================================
    # 필수 열 확인
    # ========================================================

    required = [
        "question_id",
        "user_input",
        "reference",
        "reference_text",
        "retrieved_contexts",
        "response",
        "expected_behavior",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "faithfulness",
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
            + ", ".join(
                missing
            )
        )

    # required_facts는 V4.2에서 추가된 선택 입력 열이다.
    # 기존 결과 파일에는 이 열이 없을 수 있으므로 자동 생성하고,
    # 셀 값이 비어 있으면 문항별 reference를 폴백으로 사용한다.
    required_facts_col = ensure_column(
        ws,
        columns,
        "required_facts",
    )

    # ========================================================
    # Recall 진단용 열
    # ========================================================

    recall_method_col = ensure_column(
        ws,
        columns,
        "recall_match_method",
    )

    recall_rank_col = ensure_column(
        ws,
        columns,
        "recall_matched_rank",
    )

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

    # 기존 결과 파일 호환을 위해 response_relevancy 열은 유지한다.
    # 새 RUN에서는 계산하지 않고 빈칸으로 둔다.
    response_relevancy_col = ensure_column(
        ws,
        columns,
        "response_relevancy",
    )

    correct_rejection_col = ensure_column(
        ws,
        columns,
        "correct_rejection",
    )

    rejection_reason_col = ensure_column(
        ws,
        columns,
        "rejection_match_reason",
    )

    answer_quality_col = ensure_column(
        ws,
        columns,
        "answer_quality",
    )

    answer_quality_reason_col = ensure_column(
        ws,
        columns,
        "answer_quality_reason",
    )

    answer_quality_status_col = ensure_column(
        ws,
        columns,
        "answer_quality_status",
    )

    answer_quality_match_col = ensure_column(
        ws,
        columns,
        "answer_quality_human_match",
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
                adapt_factual_korean=(
                    args.adapt_factual_korean
                ),
                use_project_factual_prompt=(
                    args.use_project_factual_prompt
                ),
                factual_only=(
                    args.factual_only
                ),
                factual_mode=(
                    args.factual_mode
                ),
                factual_atomicity=(
                    args.factual_atomicity
                ),
                factual_coverage=(
                    args.factual_coverage
                ),
                use_answer_quality=(
                    args.answer_quality
                ),
                answer_quality_only=(
                    args.answer_quality_only
                ),
            )
        )

    # ========================================================
    # 시작 정보
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
        "Resume           : "
        + (
            "기존 성공 metric 자동 SKIP"
            if not args.rerun_success
            else "성공 metric도 강제 재실행"
        )
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
        "평가 모드       : "
        + (
            "Answer Quality only"
            if args.answer_quality_only
            else (
                "Factual Correctness only"
                if args.factual_only
                else "RAGAS 핵심 metrics"
            )
        )
    )

    print(
        "Factual Mode    : "
        f"{args.factual_mode}"
    )

    print(
        "Claim 설정      : "
        f"atomicity={args.factual_atomicity}, "
        f"coverage={args.factual_coverage}"
    )

    print(
        "Answer Quality  : "
        + (
            "실행"
            if args.answer_quality or args.answer_quality_only
            else "실행 안 함"
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

    print(
        "Project Criteria : "
        + (
            "적용"
            if args.use_project_factual_prompt
            else "미적용"
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

    print(
        "=" * 78
    )

    # ========================================================
    # 통계 변수
    # ========================================================

    processed = 0
    answerable = 0
    unanswerable = 0
    correct_rejection_hits = 0

    recall_1_hits = 0
    recall_3_hits = 0
    recall_5_hits = 0

    ragas_values: dict[
        str,
        list[float],
    ] = {
        "faithfulness": [],
        "factual_correctness": [],
    }

    metric_time_totals: dict[
        str,
        float,
    ] = {
        "recall": 0.0,
        "faithfulness": 0.0,
        "factual_correctness": 0.0,
        "answer_quality": 0.0,
    }

    answer_quality_counts = {
        "PASS": 0,
        "PARTIAL": 0,
        "FAIL": 0,
    }

    answer_quality_alignment_hits = 0
    answer_quality_alignment_total = 0

    def record_answer_quality_result(
        *,
        row: int,
        value: Any,
    ) -> None:
        nonlocal answer_quality_alignment_hits
        nonlocal answer_quality_alignment_total

        normalized_quality = str(
            value
            or ""
        ).strip().upper()

        if normalized_quality not in answer_quality_counts:
            return

        answer_quality_counts[
            normalized_quality
        ] += 1

        human_score_col = columns.get(
            "human_score"
        )

        if human_score_col is None:
            return

        human_score = ws.cell(
            row=row,
            column=human_score_col,
        ).value

        try:
            normalized_human_score = int(
                float(human_score)
            )
        except (TypeError, ValueError):
            return

        quality_to_human = {
            "PASS": 2,
            "PARTIAL": 1,
            "FAIL": 0,
        }

        is_match = int(
            quality_to_human[
                normalized_quality
            ]
            == normalized_human_score
        )

        ws.cell(
            row=row,
            column=answer_quality_match_col,
            value=is_match,
        )

        answer_quality_alignment_total += 1
        answer_quality_alignment_hits += is_match

    evaluation_start = time.perf_counter()

    # ========================================================
    # 문항 반복
    # ========================================================

    for row in range(
        2,
        ws.max_row + 1,
    ):

        question_id = ws.cell(
            row=row,
            column=columns[
                "question_id"
            ],
        ).value

        question_id = (
            ""
            if question_id is None
            else str(
                question_id
            ).strip().upper()
        )

        if (
            selected_question_ids is not None
            and question_id
            not in selected_question_ids
        ):
            continue

        if selected_question_ids is not None:
            found_question_ids.add(
                question_id
            )

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

        reference = ws.cell(
            row=row,
            column=columns[
                "reference"
            ],
        ).value

        required_facts_raw = ws.cell(
            row=row,
            column=required_facts_col,
        ).value

        reference_text = ws.cell(
            row=row,
            column=columns[
                "reference_text"
            ],
        ).value

        retrieved_raw = ws.cell(
            row=row,
            column=columns[
                "retrieved_contexts"
            ],
        ).value

        response = ws.cell(
            row=row,
            column=columns[
                "response"
            ],
        ).value

        reference = (
            ""
            if reference is None
            else str(
                reference
            ).strip()
        )

        required_facts = (
            ""
            if required_facts_raw is None
            else str(
                required_facts_raw
            ).strip()
        )

        # 하위 호환성: required_facts가 없는 기존 엑셀도 실행 가능하다.
        # 다만 정밀 보정 효과를 얻으려면 해당 열을 명시적으로 작성해야 한다.
        if not required_facts:
            required_facts = reference

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

        expected_behavior = str(
            ws.cell(
                row=row,
                column=columns[
                    "expected_behavior"
                ],
            ).value
            or ""
        ).strip().lower()

        existing_faithfulness = ws.cell(
            row=row,
            column=columns[
                "faithfulness"
            ],
        ).value

        existing_factual = ws.cell(
            row=row,
            column=columns[
                "factual_correctness"
            ],
        ).value

        existing_answer_quality = ws.cell(
            row=row,
            column=answer_quality_col,
        ).value

        has_faithfulness = (
            existing_faithfulness is not None
            and str(existing_faithfulness).strip() != ""
        )

        has_factual = (
            existing_factual is not None
            and str(existing_factual).strip() != ""
        )

        has_answer_quality = (
            existing_answer_quality is not None
            and str(existing_answer_quality).strip().upper()
            in {
                "PASS",
                "PARTIAL",
                "FAIL",
            }
        )

        # 최종 성능에서 제외된 Response Relevancy는
        # 기존 열만 유지하고 새 RUN에서는 빈칸으로 둔다.
        ws.cell(
            row=row,
            column=response_relevancy_col,
            value=None,
        )

        (
            correct_rejection,
            rejection_reason,
        ) = score_correct_rejection(
            expected_behavior,
            response,
        )

        ws.cell(
            row=row,
            column=correct_rejection_col,
            value=correct_rejection,
        )

        ws.cell(
            row=row,
            column=rejection_reason_col,
            value=rejection_reason,
        )

        if correct_rejection is not None:
            unanswerable += 1
            correct_rejection_hits += (
                correct_rejection
            )

        contexts = (
            split_retrieved_contexts(
                retrieved_raw
            )
        )

        processed += 1

        question_start = time.perf_counter()

        print(
            f"\n[{processed:02d}] "
            f"{question_id}: "
            f"{user_input}"
        )

        # ====================================================
        # Recall@1 / @3 / @5 실행시간 측정
        # ====================================================

        recall_start = time.perf_counter()

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

        # ====================================================
        # Recall 저장
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

            # 가장 작은 K에서 성공한 결과 기록
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

            # Console 출력
            print(
                "  Recall@1/3/5   : "
                f"{r1} / "
                f"{r3} / "
                f"{r5}"
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
                    "  Match Rank     : "
                    "없음"
                )

            print(
                "  Match Reason   : "
                f"{final_reason}"
            )

            print(
                "  Match Score    : "
                f"{final_score:.4f}"
            )

        # ====================================================
        # RAGAS
        # ====================================================

        if expected_behavior in {
            "refuse",
            "unanswerable",
        }:
            if not args.answer_quality_only:
                ws.cell(
                    row=row,
                    column=ragas_status_col,
                    value="SKIPPED - UNANSWERABLE",
                )
            if args.answer_quality or args.answer_quality_only:
                ws.cell(
                    row=row,
                    column=answer_quality_status_col,
                    value="SKIPPED - UNANSWERABLE",
                )

        elif args.skip_ragas:
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
            if not args.answer_quality_only:
                ws.cell(
                    row=row,
                    column=ragas_status_col,
                    value="SKIPPED - response 없음",
                )
            if args.answer_quality or args.answer_quality_only:
                ws.cell(
                    row=row,
                    column=answer_quality_status_col,
                    value="SKIPPED - response 없음",
                )

        elif (
            not contexts
            and not args.factual_only
            and not args.answer_quality_only
        ):
            ws.cell(
                row=row,
                column=ragas_status_col,
                value="SKIPPED - retrieved_contexts 없음",
            )

        else:
            assert scorers is not None

            run_faithfulness = (
                not args.factual_only
                and not args.answer_quality_only
                and (
                    args.rerun_success
                    or not has_faithfulness
                )
            )

            run_factual = (
                not args.answer_quality_only
                and (
                    args.rerun_success
                    or not has_factual
                )
            )

            run_answer_quality = (
                (
                    args.answer_quality
                    or args.answer_quality_only
                )
                and (
                    args.rerun_success
                    or not has_answer_quality
                )
            )

            if (
                not run_faithfulness
                and not run_factual
                and not run_answer_quality
            ):
                print(
                    "  [RESUME] 요청한 RAGAS metric이 "
                    "이미 존재 → RAGAS SKIP"
                )

                if args.answer_quality_only:
                    ws.cell(
                        row=row,
                        column=answer_quality_status_col,
                        value="OK - RESUMED/SKIPPED",
                    )
                else:
                    ws.cell(
                        row=row,
                        column=ragas_status_col,
                        value="OK - RESUMED/SKIPPED",
                    )

                if args.answer_quality:
                    ws.cell(
                        row=row,
                        column=answer_quality_status_col,
                        value="OK - RESUMED/SKIPPED",
                    )

                if (
                    not args.factual_only
                    and not args.answer_quality_only
                    and has_faithfulness
                ):
                    try:
                        ragas_values[
                            "faithfulness"
                        ].append(
                            float(existing_faithfulness)
                        )
                    except (TypeError, ValueError):
                        pass

                if not args.answer_quality_only and has_factual:
                    try:
                        ragas_values[
                            "factual_correctness"
                        ].append(
                            float(existing_factual)
                        )
                    except (TypeError, ValueError):
                        pass

                if (
                    (args.answer_quality or args.answer_quality_only)
                    and has_answer_quality
                ):
                    record_answer_quality_result(
                        row=row,
                        value=existing_answer_quality,
                    )

            else:
                if (
                    not args.factual_only
                    and not args.answer_quality_only
                    and has_faithfulness
                    and not run_faithfulness
                ):
                    print(
                        "  [RESUME] faithfulness 기존 값 유지"
                    )

                if (
                    not args.answer_quality_only
                    and has_factual
                    and not run_factual
                ):
                    print(
                        "  [RESUME] factual_correctness 기존 값 유지"
                    )

                scores, metric_times = await score_one_with_ragas(
                    scorers=scorers,
                    user_input=user_input,
                    reference=reference,
                    required_facts=required_facts,
                    reference_text=reference_text,
                    response=response,
                    contexts=contexts,
                    factual_only=args.factual_only,
                    run_faithfulness=run_faithfulness,
                    run_factual_correctness=run_factual,
                    run_answer_quality=run_answer_quality,
                )

                for metric_name, elapsed in metric_times.items():
                    metric_time_totals[
                        metric_name
                    ] += elapsed

                if run_faithfulness:
                    ws.cell(
                        row=row,
                        column=columns[
                            "faithfulness"
                        ],
                        value=scores[
                            "faithfulness"
                        ],
                    )

                if run_factual:
                    ws.cell(
                        row=row,
                        column=columns[
                            "factual_correctness"
                        ],
                        value=scores[
                            "factual_correctness"
                        ],
                    )

                if run_answer_quality:
                    ws.cell(
                        row=row,
                        column=answer_quality_col,
                        value=scores[
                            "answer_quality"
                        ],
                    )
                    ws.cell(
                        row=row,
                        column=answer_quality_reason_col,
                        value=scores[
                            "answer_quality_reason"
                        ],
                    )

                final_faithfulness = (
                    scores["faithfulness"]
                    if run_faithfulness
                    else existing_faithfulness
                )

                final_factual = (
                    scores["factual_correctness"]
                    if run_factual
                    else existing_factual
                )

                final_answer_quality = (
                    scores["answer_quality"]
                    if run_answer_quality
                    else existing_answer_quality
                )

                if not args.factual_only:
                    try:
                        if (
                            final_faithfulness is not None
                            and str(final_faithfulness).strip() != ""
                        ):
                            ragas_values[
                                "faithfulness"
                            ].append(
                                float(final_faithfulness)
                            )
                    except (TypeError, ValueError):
                        pass

                if not args.answer_quality_only:
                    try:
                        if (
                            final_factual is not None
                            and str(final_factual).strip() != ""
                        ):
                            ragas_values[
                                "factual_correctness"
                            ].append(
                                float(final_factual)
                            )
                    except (TypeError, ValueError):
                        pass

                if (
                    args.answer_quality
                    or args.answer_quality_only
                ):
                    record_answer_quality_result(
                        row=row,
                        value=final_answer_quality,
                    )

                if args.answer_quality_only:
                    answer_quality_status = (
                        "OK - ANSWER_QUALITY_ONLY"
                        if final_answer_quality is not None
                        and str(final_answer_quality).strip() != ""
                        else "FAILED - ANSWER_QUALITY_ONLY"
                    )
                elif args.factual_only:
                    status = (
                        "OK - FACTUAL_ONLY"
                        if final_factual is not None
                        and str(final_factual).strip() != ""
                        else "FAILED - FACTUAL_ONLY"
                    )
                else:
                    required_results = [
                        final_faithfulness,
                        final_factual,
                    ]

                    if args.answer_quality:
                        required_results.append(
                            final_answer_quality
                        )

                    completed_results = [
                        value is not None
                        and str(value).strip() != ""
                        for value in required_results
                    ]

                    if all(completed_results):
                        status = "OK"
                    elif any(completed_results):
                        status = "PARTIAL"
                    else:
                        status = "FAILED"

                if args.answer_quality_only:
                    ws.cell(
                        row=row,
                        column=answer_quality_status_col,
                        value=answer_quality_status,
                    )
                else:
                    ws.cell(
                        row=row,
                        column=ragas_status_col,
                        value=status,
                    )

                    if args.answer_quality:
                        ws.cell(
                            row=row,
                            column=answer_quality_status_col,
                            value=(
                                "OK"
                                if final_answer_quality is not None
                                and str(final_answer_quality).strip() != ""
                                else "FAILED"
                            ),
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

        # 중간 저장
        wb.save(
            output_path
        )

    # ========================================================
    # 선택 문항 확인
    # ========================================================

    if selected_question_ids is not None:

        missing_question_ids = (
            selected_question_ids
            - found_question_ids
        )

        if missing_question_ids:

            print(
                "\n[경고] Excel에서 "
                "찾지 못한 문항: "
                + ", ".join(
                    sorted(
                        missing_question_ids
                    )
                )
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
    # Correct Rejection Rate
    # ========================================================

    if unanswerable > 0:
        correct_rejection_rate = (
            correct_rejection_hits
            / unanswerable
        )

        print(
            "Correct Rejection : "
            f"{correct_rejection_hits}/"
            f"{unanswerable} "
            f"= {correct_rejection_rate:.4f} "
            f"({correct_rejection_rate * 100:.1f}%)"
        )

    # ========================================================
    # RAGAS 평균
    # ========================================================

    if not args.skip_ragas:

        if not args.answer_quality_only:
            print(
                "\n[RAGAS 평균]"
            )

        for (
            metric_name,
            values,
        ) in ragas_values.items():

            if args.answer_quality_only:
                continue

            if (
                args.factual_only
                and metric_name
                != "factual_correctness"
            ):
                continue

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

        if args.answer_quality or args.answer_quality_only:
            quality_total = sum(
                answer_quality_counts.values()
            )

            print(
                "\n[Answer Quality]"
            )

            for label in (
                "PASS",
                "PARTIAL",
                "FAIL",
            ):
                count = answer_quality_counts[label]
                rate = (
                    count / quality_total
                    if quality_total > 0
                    else 0.0
                )
                print(
                    f"{label:22s}: "
                    f"{count}/{quality_total} "
                    f"({rate * 100:.1f}%)"
                )

            if quality_total > 0:
                normalized_quality_score = (
                    answer_quality_counts["PASS"]
                    + 0.5
                    * answer_quality_counts["PARTIAL"]
                ) / quality_total

                print(
                    f"{'정규화 품질점수':22s}: "
                    f"{normalized_quality_score:.4f} "
                    f"({normalized_quality_score * 100:.1f}%)"
                )

            if answer_quality_alignment_total > 0:
                alignment_rate = (
                    answer_quality_alignment_hits
                    / answer_quality_alignment_total
                )

                print(
                    f"{'휴먼 판정 일치율':22s}: "
                    f"{answer_quality_alignment_hits}/"
                    f"{answer_quality_alignment_total} "
                    f"= {alignment_rate:.4f} "
                    f"({alignment_rate * 100:.1f}%)"
                )

    evaluation_elapsed = (
        time.perf_counter()
        - evaluation_start
    )

    print(
        "\n[실행시간 요약]"
    )

    print(
        f"{'Recall@1/3/5 합계':26s}: "
        f"{metric_time_totals['recall']:.2f}s"
    )

    if not args.skip_ragas:

        time_metric_names: list[str] = []

        if not args.answer_quality_only:
            if not args.factual_only:
                time_metric_names.append(
                    "faithfulness"
                )
            time_metric_names.append(
                "factual_correctness"
            )

        if args.answer_quality or args.answer_quality_only:
            time_metric_names.append(
                "answer_quality"
            )

        for metric_name in time_metric_names:

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
            f"{'문항당 평균시간':26s}: "
            f"{evaluation_elapsed / processed:.2f}s"
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
        default=None,
        help=(
            "평가셋 코드. 예: GC, BD, DH, GP. "
            "코드 목록은 하드코딩하지 않으며 새 Dataset도 사용할 수 있습니다. "
            "--xlsx를 함께 지정하면 해당 Dataset ID로 사용하고, "
            "--xlsx 없이 지정하면 evaluation/results/에서 "
            "<DATASET>_FINAL_V*_ACTUAL_RUN_*_result.xlsx를 자동 탐색합니다."
        ),
    )

    parser.add_argument(
        "--xlsx",
        default=None,
        help=(
            "평가 입력 Excel 경로. "
            "생략하면 --dataset 기준 최신 ACTUAL_RUN result.xlsx를 자동 탐색합니다."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "평가 결과 Excel 저장 경로. "
            "생략하면 입력 result.xlsx 기준 *_scored.xlsx로 자동 생성합니다."
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
            "Recall@K만 다시 계산합니다."
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
        "--factual-only",
        action="store_true",
        help=(
            "Faithfulness를 생략하고 "
            "Factual Correctness만 계산합니다. "
            "Judge 비교/디버깅용 빠른 평가 옵션입니다."
        ),
    )

    parser.add_argument(
        "--factual-mode",
        choices=[
            "f1",
            "precision",
            "recall",
        ],
        default="f1",
        help=(
            "Factual Correctness 계산 방식. "
            "f1=정확성과 정답 포함 범위 종합, "
            "precision=응답 사실의 정확성 중심, "
            "recall=모범답안 핵심 사실 포함 여부 중심. "
            "기본값은 f1입니다."
        ),
    )

    parser.add_argument(
        "--factual-atomicity",
        choices=[
            "low",
            "high",
        ],
        default="low",
        help=(
            "Factual Correctness claim 분해 세분화 수준. "
            "high는 날짜·시간·금액·조건을 더 작은 사실로 분리합니다. "
            "기본값 low는 기존 코드와 동일하며, "
            "OneCycle 개선 실험은 high를 명시해서 사용합니다."
        ),
    )

    parser.add_argument(
        "--factual-coverage",
        choices=[
            "low",
            "high",
        ],
        default="low",
        help=(
            "Factual Correctness claim 추출 범위. "
            "low는 질문과 무관한 부가 문구의 과도한 claim 생성을 줄입니다. "
            "OneCycle 권장값은 low입니다."
        ),
    )

    parser.add_argument(
        "--answer-quality",
        action="store_true",
        help=(
            "기존 Faithfulness와 Factual Correctness에 더해 "
            "질문·모범답안·응답을 직접 비교하는 "
            "PASS/PARTIAL/FAIL 평가를 실행합니다."
        ),
    )

    parser.add_argument(
        "--answer-quality-only",
        action="store_true",
        help=(
            "Faithfulness와 Factual Correctness를 실행하지 않고 "
            "PASS/PARTIAL/FAIL 평가만 실행합니다. "
            "휴먼 불일치 문항 보정 테스트에 사용합니다."
        ),
    )


    parser.add_argument(
        "--rerun-success",
        action="store_true",
        help=(
            "기존 출력 파일에 값이 있는 metric도 "
            "강제로 다시 계산합니다. "
            "기본값은 성공 metric 자동 SKIP입니다."
        ),
    )

    parser.add_argument(
        "--question-ids",
        default=None,
        help=(
            "평가할 question_id를 "
            "쉼표로 구분하여 지정합니다. "
            "예: Q002,Q003,Q007 "
            "생략하면 전체 문항을 평가합니다."
        ),
    )

    parser.add_argument(
        "--adapt-factual-korean",
        action="store_true",
        help=(
            "RAGAS FactualCorrectness의 "
            "claim 분해 prompt와 NLI prompt를 "
            "한국어로 adaptation합니다."
        ),
    )


    parser.add_argument(
        "--use-project-factual-prompt",
        action="store_true",
        help=(
            "한국어 adaptation 여부와 별개로 "
            "OneCycle LH 공고문용 Factual Correctness "
            "보완 판정 기준을 추가합니다. "
            "기본값은 미적용입니다."
        ),
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================


def main() -> None:

    args = parse_args()

    try:

        if not args.dataset and not args.xlsx:
            raise ValueError(
                "--dataset 또는 --xlsx 중 하나는 필요합니다."
            )

        if args.answer_quality_only and args.answer_quality:
            raise ValueError(
                "--answer-quality-only와 --answer-quality는 "
                "동시에 사용할 수 없습니다."
            )

        if args.factual_only and (
            args.answer_quality
            or args.answer_quality_only
        ):
            raise ValueError(
                "--factual-only는 Answer Quality 옵션과 "
                "동시에 사용할 수 없습니다."
            )

        if args.skip_ragas and (
            args.answer_quality
            or args.answer_quality_only
        ):
            raise ValueError(
                "Answer Quality는 RAGAS Judge를 사용하므로 "
                "--skip-ragas와 동시에 사용할 수 없습니다."
            )

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
