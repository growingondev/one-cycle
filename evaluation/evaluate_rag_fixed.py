from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from openpyxl import load_workbook

from evaluation.fixed_rag.service import answer_question


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_DIR = (
    PROJECT_ROOT
    / "evaluation"
    / "datasets"
)

RESULT_DIR = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
)


DEFAULT_SHEET_NAME = "평가셋"
DEFAULT_RUN_NUMBER = "001"


# ============================================================
# 고정 평가 Dataset ↔ 문서 ID 매핑
# ============================================================

FIXED_DOCUMENT_IDS = {
    "GC": "DOC_GC_001",
    "BD": "DOC_BD_001",
}


# ============================================================
# Dataset
# ============================================================

def normalize_dataset_name(
    dataset: str,
) -> str:

    normalized = (
        dataset
        .strip()
        .upper()
    )

    if not normalized:
        raise ValueError(
            "dataset이 비어 있습니다."
        )

    if normalized not in FIXED_DOCUMENT_IDS:
        raise ValueError(
            "지원하지 않는 고정 평가 dataset입니다: "
            f"{normalized}\n"
            "사용 가능: "
            + ", ".join(
                sorted(
                    FIXED_DOCUMENT_IDS
                )
            )
        )

    return normalized


def dataset_input_path(
    dataset: str,
) -> Path:

    path = (
        DATASET_DIR
        / f"{dataset}_FINAL_V1.xlsx"
    )

    if not path.is_file():
        raise FileNotFoundError(
            "평가셋 Excel을 찾을 수 없습니다: "
            f"{path}"
        )

    return path


def output_path(
    dataset: str,
    run_id: str,
) -> Path:

    return (
        RESULT_DIR
        / (
            f"{dataset}_FINAL_V1_"
            f"FIXED_RUN_{run_id}_result.xlsx"
        )
    )


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


def require_columns(
    columns: dict[str, int],
    names: list[str],
) -> None:

    missing = [
        name
        for name in names
        if name not in columns
    ]

    if missing:
        raise ValueError(
            "필수 Excel 열이 없습니다: "
            + ", ".join(
                missing
            )
        )


# ============================================================
# Git
# ============================================================

def git_commit() -> str:

    try:
        return (
            subprocess.check_output(
                [
                    "git",
                    "rev-parse",
                    "--short",
                    "HEAD",
                ],
                cwd=PROJECT_ROOT,
                text=True,
            )
            .strip()
        )

    except Exception:
        return ""


# ============================================================
# Retrieval 결과 → Excel 문자열
# ============================================================

def format_evidence(
    evidence: list[dict],
) -> tuple[str, str]:

    chunk_ids: list[str] = []
    blocks: list[str] = []

    for rank, item in enumerate(
        evidence,
        start=1,
    ):
        chunk_id = str(
            item.get(
                "chunkId",
                "",
            )
        )

        section = str(
            item.get(
                "sectionTitle",
                "",
            )
            or ""
        )

        content = str(
            item.get(
                "content",
                "",
            )
            or ""
        )

        score = item.get(
            "score"
        )

        chunk_ids.append(
            chunk_id
        )

        try:
            score_text = (
                f"{float(score):.6f}"
            )

        except (
            TypeError,
            ValueError,
        ):
            score_text = ""

        blocks.append(
            "\n".join(
                [
                    (
                        f"[rank={rank} | "
                        f"chunkId={chunk_id} | "
                        f"section={section} | "
                        f"score={score_text}]"
                    ),
                    content,
                ]
            )
        )

    return (
        ", ".join(
            chunk_ids
        ),
        "\n\n---\n\n".join(
            blocks
        ),
    )


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "고정 평가 문서의 evaluation/outputs 산출물을 "
            "사용해 실제 RAG Generation 로직으로 "
            "답변을 수집합니다."
        )
    )

    parser.add_argument(
        "--dataset",
        required=True,
        help="GC 또는 BD",
    )

    parser.add_argument(
        "--xlsx",
        default=None,
        help=(
            "기본 평가셋이 아닌 다른 Excel을 "
            "사용할 경우 경로 지정"
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "결과 Excel 저장 경로를 "
            "직접 지정할 경우 사용"
        ),
    )

    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET_NAME,
    )

    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_NUMBER,
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--question-ids",
        default=None,
        help=(
            "일부 문항만 실행할 때 사용 "
            "예: Q001,Q002,Q010"
        ),
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================

def main() -> None:

    args = parse_args()

    dataset = (
        normalize_dataset_name(
            args.dataset
        )
    )

    document_id = (
        FIXED_DOCUMENT_IDS[
            dataset
        ]
    )

    # --------------------------------------------------------
    # 평가셋 입력 경로
    # --------------------------------------------------------

    input_path = (
        Path(args.xlsx).resolve()
        if args.xlsx
        else dataset_input_path(
            dataset
        )
    )

    # --------------------------------------------------------
    # 결과 저장 경로
    # --------------------------------------------------------

    result_path = (
        Path(args.output).resolve()
        if args.output
        else output_path(
            dataset,
            args.run_id,
        )
    )

    # --------------------------------------------------------
    # Top-K 검사
    # --------------------------------------------------------

    if (
        args.top_k is not None
        and args.top_k <= 0
    ):
        raise ValueError(
            "--top-k는 1 이상이어야 합니다."
        )

    # --------------------------------------------------------
    # 일부 문항만 실행
    # --------------------------------------------------------

    selected_question_ids = None

    if args.question_ids:
        selected_question_ids = {
            item.strip()
            for item
            in args.question_ids.split(",")
            if item.strip()
        }

    # --------------------------------------------------------
    # 결과 폴더 생성
    # --------------------------------------------------------

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Excel 읽기
    # --------------------------------------------------------

    wb = load_workbook(
        input_path
    )

    if args.sheet not in wb.sheetnames:
        raise ValueError(
            f"'{args.sheet}' 시트가 없습니다."
        )

    ws = wb[
        args.sheet
    ]

    columns = (
        find_columns(
            ws
        )
    )

    require_columns(
        columns,
        [
            "question_id",
            "user_input",
            "retrieved_chunk_ids",
            "retrieved_contexts",
            "response",
            "run_id",
            "git_commit",
        ],
    )

    current_commit = (
        git_commit()
    )

    processed = 0

    # --------------------------------------------------------
    # 실행 정보
    # --------------------------------------------------------

    print(
        "=" * 78
    )

    print(
        "고정 문서 RAG 결과 수집"
    )

    print(
        f"dataset     : {dataset}"
    )

    print(
        f"document_id : {document_id}"
    )

    print(
        f"input       : {input_path}"
    )

    print(
        f"output      : {result_path}"
    )

    print(
        f"run_id      : {args.run_id}"
    )

    print(
        "source      : "
        f"evaluation/source_documents/"
        f"{document_id}"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # 질문 실행
    # ========================================================

    for row in range(
        2,
        ws.max_row + 1,
    ):

        # ----------------------------------------------------
        # question_id
        # ----------------------------------------------------

        question_id = str(
            ws.cell(
                row=row,
                column=columns[
                    "question_id"
                ],
            ).value
            or ""
        ).strip()

        # 지정한 문항이 아니면 Skip
        if (
            selected_question_ids
            and question_id
            not in selected_question_ids
        ):
            continue

        # ----------------------------------------------------
        # user_input
        # ----------------------------------------------------

        question = str(
            ws.cell(
                row=row,
                column=columns[
                    "user_input"
                ],
            ).value
            or ""
        ).strip()

        if not question:
            continue

        print(
            f"\n[{question_id}] "
            f"{question}"
        )

        started = (
            time.perf_counter()
        )

        # ====================================================
        # Fixed RAG 실행
        # ====================================================

        try:
            result = (
                answer_question(
                    dataset=dataset,
                    question=question,
                    top_k=args.top_k,
                )
            )

            evidence = (
                result.get(
                    "evidence",
                    [],
                )
            )

            chunk_ids, contexts = (
                format_evidence(
                    evidence
                )
            )

            # -----------------------------------------------
            # 검색 Chunk ID
            # -----------------------------------------------

            ws.cell(
                row=row,
                column=columns[
                    "retrieved_chunk_ids"
                ],
                value=chunk_ids,
            )

            # -----------------------------------------------
            # 검색 Context
            # -----------------------------------------------

            ws.cell(
                row=row,
                column=columns[
                    "retrieved_contexts"
                ],
                value=contexts,
            )

            # -----------------------------------------------
            # 생성 답변
            # -----------------------------------------------

            answer = str(
                result.get(
                    "answer",
                    "",
                )
            )

            ws.cell(
                row=row,
                column=columns[
                    "response"
                ],
                value=answer,
            )

            print(
                "  evidence : "
                f"{len(evidence)}개"
            )

            print(
                "  answer   : "
                f"{answer[:120]}"
            )

        # ====================================================
        # 실패
        # ====================================================

        except Exception as exc:

            print(
                "  [실패] "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            ws.cell(
                row=row,
                column=columns[
                    "response"
                ],
                value=(
                    "[FIXED_RAG_ERROR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

        # ----------------------------------------------------
        # 수행 시간
        # ----------------------------------------------------

        elapsed_ms = int(
            (
                time.perf_counter()
                - started
            )
            * 1000
        )

        if "elapsed_ms" in columns:
            ws.cell(
                row=row,
                column=columns[
                    "elapsed_ms"
                ],
                value=elapsed_ms,
            )

        # ----------------------------------------------------
        # Run ID
        # ----------------------------------------------------

        ws.cell(
            row=row,
            column=columns[
                "run_id"
            ],
            value=(
                f"FIXED_RUN_"
                f"{args.run_id}"
            ),
        )

        # ----------------------------------------------------
        # Git Commit
        # ----------------------------------------------------

        ws.cell(
            row=row,
            column=columns[
                "git_commit"
            ],
            value=current_commit,
        )

        # ----------------------------------------------------
        # 원본 고정 문서 경로
        # ----------------------------------------------------

        if "source_file" in columns:
            ws.cell(
                row=row,
                column=columns[
                    "source_file"
                ],
                value=(
                    "evaluation/"
                    "source_documents/"
                    f"{document_id}"
                ),
            )

        processed += 1

        # ----------------------------------------------------
        # 질문 하나 처리할 때마다 저장
        #
        # 평가 중간에 서버가 종료되어도
        # 이미 처리한 결과를 최대한 보존한다.
        # ----------------------------------------------------

        wb.save(
            result_path
        )

    # ========================================================
    # 완료
    # ========================================================

    print()

    print(
        "=" * 78
    )

    print(
        "고정 문서 RAG 결과 수집 완료"
    )

    print(
        f"처리 문항 수 : {processed}"
    )

    print(
        f"결과 파일   : {result_path}"
    )

    print(
        "=" * 78
    )


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:

        print(
            "\n사용자가 평가를 중단했습니다."
        )

        sys.exit(
            130
        )

    except Exception as exc:

        print(
            "\n고정 평가 실행 중 오류가 발생했습니다:\n"
            f"{exc}"
        )

        sys.exit(
            1
        )