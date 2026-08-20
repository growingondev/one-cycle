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


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

DEFAULT_SHEET_NAME = "평가셋"
DEFAULT_RECALL_THRESHOLD = 0.75

# evaluate_rag.py와 같은 값으로 맞추세요.
# 코드 수정 후 재평가할 때 001 -> 002 -> 003 으로 변경합니다.
DEFAULT_RUN_NUMBER = "001"

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


def dataset_paths(dataset: str) -> tuple[Path, Path]:
    dataset = normalize_dataset_name(dataset)

    input_xlsx = (
        RESULTS_DIR
        / f"{dataset}_FINAL_V1_RUN_{DEFAULT_RUN_NUMBER}_result.xlsx"
    )
    output_xlsx = (
        RESULTS_DIR
        / f"{dataset}_FINAL_V1_RUN_{DEFAULT_RUN_NUMBER}_scored.xlsx"
    )

    return input_xlsx, output_xlsx


def find_columns(ws) -> dict[str, int]:
    columns: dict[str, int] = {}

    for cell in ws[1]:
        if cell.value is not None:
            columns[str(cell.value).strip()] = cell.column

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


def split_retrieved_contexts(
    value: Any,
) -> list[str]:
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
            and lines[0].strip().startswith("[rank=")
        ):
            part = "\n".join(
                lines[1:]
            ).strip()

        if part:
            contexts.append(part)

    return contexts


def normalize_text(text: str) -> str:
    text = text.lower()

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


def extract_tokens(text: str) -> list[str]:
    tokens = re.findall(
        r"[0-9]+(?:[.,][0-9]+)*"
        r"|[가-힣]{2,}"
        r"|[A-Za-z]{2,}",
        text,
    )

    return [
        token.lower()
        for token in tokens
        if token.strip()
    ]


def evidence_match_score(
    reference_text: str,
    context: str,
) -> float:
    ref_norm = normalize_text(reference_text)
    ctx_norm = normalize_text(context)

    if not ref_norm or not ctx_norm:
        return 0.0

    if ref_norm in ctx_norm:
        return 1.0

    tokens = extract_tokens(reference_text)

    if tokens:
        matched = sum(
            1
            for token in tokens
            if normalize_text(token) in ctx_norm
        )
        token_score = matched / len(tokens)
    else:
        token_score = 0.0

    direct_ratio = SequenceMatcher(
        None,
        ref_norm,
        ctx_norm,
    ).ratio()

    similarity_score = direct_ratio

    if (
        len(ctx_norm) > len(ref_norm)
        and len(ref_norm) > 0
    ):
        window_size = max(
            len(ref_norm),
            int(len(ref_norm) * 1.8),
        )

        step = max(
            1,
            len(ref_norm) // 4,
        )

        best_partial = 0.0

        max_start = max(
            1,
            len(ctx_norm) - window_size + 1,
        )

        for start in range(
            0,
            max_start,
            step,
        ):
            candidate = ctx_norm[
                start:start + window_size
            ]

            ratio = SequenceMatcher(
                None,
                ref_norm,
                candidate,
            ).ratio()

            best_partial = max(
                best_partial,
                ratio,
            )

        similarity_score = max(
            direct_ratio,
            best_partial,
        )

    combined_score = (
        0.70 * token_score
        + 0.30 * similarity_score
    )

    return max(
        similarity_score,
        combined_score,
    )


def recall_at_k(
    reference_text: str,
    contexts: list[str],
    k: int,
    threshold: float,
) -> int | None:
    if not reference_text.strip():
        return None

    for context in contexts[:k]:
        score = evidence_match_score(
            reference_text,
            context,
        )

        if score >= threshold:
            return 1

    return 0


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
        missing.append("sentence-transformers")

    if missing:
        raise RuntimeError(
            "RAGAS 평가에 필요한 패키지가 없습니다.\n\n"
            "다음 명령으로 설치하세요:\n\n"
            f"pip install {' '.join(missing)}"
        )


async def build_ragas_scorers(
    base_url: str,
    api_key: str,
    model: str,
    embedding_model: str,
) -> dict[str, Any]:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings import HuggingFaceEmbeddings
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
            "--dataset GC --ragas-model 모델명"
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
        "context_precision": ContextPrecision(
            llm=llm
        ),
        "context_recall": ContextRecall(
            llm=llm
        ),
        "faithfulness": Faithfulness(
            llm=llm
        ),
        "response_relevancy": AnswerRelevancy(
            llm=llm,
            embeddings=embeddings,
        ),
        "factual_correctness": FactualCorrectness(
            llm=llm
        ),
    }


async def score_one_with_ragas(
    scorers: dict[str, Any],
    user_input: str,
    reference: str,
    response: str,
    contexts: list[str],
) -> dict[str, float | None]:
    scores: dict[str, float | None] = {
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
            result = await scorers[name].ascore(
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
                f"    [RAGAS 경고] "
                f"{name} 실패: {exc}"
            )
            return None

    scores["context_precision"] = await safe_score(
        "context_precision",
        user_input=user_input,
        reference=reference,
        retrieved_contexts=contexts,
    )

    scores["context_recall"] = await safe_score(
        "context_recall",
        user_input=user_input,
        reference=reference,
        retrieved_contexts=contexts,
    )

    scores["faithfulness"] = await safe_score(
        "faithfulness",
        user_input=user_input,
        response=response,
        retrieved_contexts=contexts,
    )

    scores["response_relevancy"] = await safe_score(
        "response_relevancy",
        user_input=user_input,
        response=response,
    )

    scores["factual_correctness"] = await safe_score(
        "factual_correctness",
        response=response,
        reference=reference,
    )

    return scores


async def evaluate_metrics(
    args: argparse.Namespace,
) -> None:
    dataset = normalize_dataset_name(args.dataset)

    default_input, default_output = dataset_paths(
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

    if not input_path.exists():
        raise FileNotFoundError(
            "평가 결과 파일을 찾을 수 없습니다:\n"
            f"{input_path}\n\n"
            "먼저 evaluate_rag.py를 실행하세요."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wb = load_workbook(input_path)

    if args.sheet not in wb.sheetnames:
        raise ValueError(
            f"'{args.sheet}' 시트가 없습니다.\n"
            f"현재 시트: {wb.sheetnames}"
        )

    ws = wb[args.sheet]
    columns = find_columns(ws)

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
        name for name in required
        if name not in columns
    ]

    if missing:
        raise ValueError(
            "평가에 필요한 Excel 열이 없습니다:\n"
            + ", ".join(missing)
        )

    recall_method_col = ensure_column(
        ws,
        columns,
        "recall_match_method",
    )

    ragas_status_col = ensure_column(
        ws,
        columns,
        "ragas_status",
    )

    scorers = None

    if not args.skip_ragas:
        check_ragas_packages()

        scorers = await build_ragas_scorers(
            base_url=args.ragas_base_url,
            api_key=args.ragas_api_key,
            model=args.ragas_model,
            embedding_model=args.embedding_model,
        )

    print("=" * 78)
    print("RAG 평가 지표 계산")
    print(f"dataset          : {dataset}")
    print(f"입력 파일       : {input_path}")
    print(f"출력 파일       : {output_path}")
    print(f"Recall threshold: {args.recall_threshold}")
    print(
        "Recall 방식      : "
        "reference_text와 Top-K context 자동 비교"
    )
    print(
        f"RAGAS           : "
        f"{'실행 안 함' if args.skip_ragas else '실행'}"
    )
    print("=" * 78)

    processed = 0
    answerable = 0

    recall_1_hits = 0
    recall_3_hits = 0
    recall_5_hits = 0

    ragas_values: dict[str, list[float]] = {
        "context_precision": [],
        "context_recall": [],
        "faithfulness": [],
        "response_relevancy": [],
        "factual_correctness": [],
    }

    for row in range(
        2,
        ws.max_row + 1,
    ):
        question_id = ws.cell(
            row=row,
            column=columns["question_id"],
        ).value

        user_input = ws.cell(
            row=row,
            column=columns["user_input"],
        ).value

        if user_input is None:
            continue

        user_input = str(user_input).strip()

        if not user_input:
            continue

        reference = ws.cell(
            row=row,
            column=columns["reference"],
        ).value

        reference_text = ws.cell(
            row=row,
            column=columns["reference_text"],
        ).value

        retrieved_raw = ws.cell(
            row=row,
            column=columns["retrieved_contexts"],
        ).value

        response = ws.cell(
            row=row,
            column=columns["response"],
        ).value

        reference = (
            ""
            if reference is None
            else str(reference).strip()
        )

        reference_text = (
            ""
            if reference_text is None
            else str(reference_text).strip()
        )

        response = (
            ""
            if response is None
            else str(response).strip()
        )

        contexts = split_retrieved_contexts(
            retrieved_raw
        )

        processed += 1

        print(
            f"\n[{processed:02d}] "
            f"{question_id}: {user_input}"
        )

        r1 = recall_at_k(
            reference_text,
            contexts,
            1,
            args.recall_threshold,
        )

        r3 = recall_at_k(
            reference_text,
            contexts,
            3,
            args.recall_threshold,
        )

        r5 = recall_at_k(
            reference_text,
            contexts,
            5,
            args.recall_threshold,
        )

        ws.cell(
            row=row,
            column=columns["recall_at_1"],
            value=r1,
        )

        ws.cell(
            row=row,
            column=columns["recall_at_3"],
            value=r3,
        )

        ws.cell(
            row=row,
            column=columns["recall_at_5"],
            value=r5,
        )

        if r1 is None:
            ws.cell(
                row=row,
                column=recall_method_col,
                value="N/A - reference_text 없음",
            )

            print(
                "  Recall@K       : N/A"
            )
        else:
            answerable += 1

            recall_1_hits += r1
            recall_3_hits += r3
            recall_5_hits += r5

            ws.cell(
                row=row,
                column=recall_method_col,
                value=(
                    "reference_text ↔ "
                    "retrieved_contexts 자동 매칭 "
                    f"(threshold={args.recall_threshold})"
                ),
            )

            print(
                f"  Recall@1/3/5   : "
                f"{r1} / {r3} / {r5}"
            )

        if args.skip_ragas:
            ws.cell(
                row=row,
                column=ragas_status_col,
                value="SKIPPED",
            )

        elif not response:
            ws.cell(
                row=row,
                column=ragas_status_col,
                value="SKIPPED - response 없음",
            )

        elif not contexts:
            ws.cell(
                row=row,
                column=ragas_status_col,
                value="SKIPPED - retrieved_contexts 없음",
            )

        else:
            assert scorers is not None

            scores = await score_one_with_ragas(
                scorers=scorers,
                user_input=user_input,
                reference=reference,
                response=response,
                contexts=contexts,
            )

            for metric_name, score in scores.items():
                ws.cell(
                    row=row,
                    column=columns[metric_name],
                    value=score,
                )

                if score is not None:
                    ragas_values[
                        metric_name
                    ].append(score)

            if all(
                value is not None
                for value in scores.values()
            ):
                status = "OK"

            elif any(
                value is not None
                for value in scores.values()
            ):
                status = "PARTIAL"

            else:
                status = "FAILED"

            ws.cell(
                row=row,
                column=ragas_status_col,
                value=status,
            )

        wb.save(output_path)

    print("\n" + "=" * 78)
    print("평가 완료")
    print(f"전체 처리 질문 : {processed}")

    if answerable > 0:
        recall1 = recall_1_hits / answerable
        recall3 = recall_3_hits / answerable
        recall5 = recall_5_hits / answerable

        print(f"Answerable 질문 : {answerable}")
        print(
            f"Recall@1        : "
            f"{recall_1_hits}/{answerable} "
            f"= {recall1:.4f} ({recall1 * 100:.1f}%)"
        )
        print(
            f"Recall@3        : "
            f"{recall_3_hits}/{answerable} "
            f"= {recall3:.4f} ({recall3 * 100:.1f}%)"
        )
        print(
            f"Recall@5        : "
            f"{recall_5_hits}/{answerable} "
            f"= {recall5:.4f} ({recall5 * 100:.1f}%)"
        )

    if not args.skip_ragas:
        print("\n[RAGAS 평균]")

        for metric_name, values in ragas_values.items():
            if values:
                average = sum(values) / len(values)
                print(
                    f"{metric_name:22s}: "
                    f"{average:.4f} ({len(values)}개)"
                )
            else:
                print(
                    f"{metric_name:22s}: N/A"
                )

    print(f"\n결과 파일       : {output_path}")
    print("=" * 78)


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
        help="평가셋 코드 (GC=고창율계, HC=화천신읍2)",
    )

    parser.add_argument(
        "--xlsx",
        default=None,
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET_NAME,
    )

    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=DEFAULT_RECALL_THRESHOLD,
    )

    parser.add_argument(
        "--skip-ragas",
        action="store_true",
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


def main() -> None:
    args = parse_args()

    if not (
        0.0
        < args.recall_threshold
        <= 1.0
    ):
        print(
            "--recall-threshold는 "
            "0보다 크고 1 이하이어야 합니다."
        )
        sys.exit(2)

    try:
        asyncio.run(
            evaluate_metrics(args)
        )

    except KeyboardInterrupt:
        print(
            "\n사용자가 평가를 중단했습니다."
        )
        sys.exit(130)

    except Exception as exc:
        print(
            "\n평가 중 오류가 발생했습니다:\n"
            f"{exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
