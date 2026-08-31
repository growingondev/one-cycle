from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR / "datasets"
RESULTS_DIR = BASE_DIR / "results"

DEFAULT_API_BASE_URL = os.getenv(
    "EVAL_API_BASE_URL",
    "http://127.0.0.1:8000",
)
DEFAULT_ENDPOINT = "/api/chat"
DEFAULT_SHEET_NAME = "평가셋"
DEFAULT_TIMEOUT_SECONDS = int(
    os.getenv("EVAL_TIMEOUT_SECONDS", "600")
)

# 코드 수정 후 재평가할 때 이 값만 001 -> 002 -> 003 으로 변경하세요.
DEFAULT_RUN_NUMBER = "001"


def normalize_dataset_name(value: str) -> str:
    dataset = value.strip().upper()

    aliases = {
        "GC": "GC",
        "GOCHANG": "GC",
        "고창": "GC",
        "BD": "BD",
        "BEONDONG": "BD",
        "서울 번동": "BD",
    }

    if dataset not in aliases:
        raise ValueError(
            f"지원하지 않는 dataset입니다: {value}\n"
            "사용 가능: GC, HC"
        )

    return aliases[dataset]


def dataset_paths(dataset: str) -> tuple[Path, Path, str]:
    dataset = normalize_dataset_name(dataset)

    input_xlsx = DATASETS_DIR / f"{dataset}_FINAL_V1.xlsx"
    output_xlsx = (
        RESULTS_DIR
        / f"{dataset}_FINAL_V1_RUN_{DEFAULT_RUN_NUMBER}_result.xlsx"
    )
    default_run_id = f"{dataset}_RUN_{DEFAULT_RUN_NUMBER}"

    return input_xlsx, output_xlsx, default_run_id


def get_git_info() -> tuple[str, str]:
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        branch = ""

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        commit = ""

    return branch, commit


def http_post_json(
    url: str,
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(
            f"HTTP {exc.code} 오류\n"
            f"URL: {url}\n"
            f"응답: {error_body}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"API 서버 연결 실패: {exc.reason}\n"
            f"URL: {url}"
        ) from exc


def find_columns(ws) -> dict[str, int]:
    result: dict[str, int] = {}

    for cell in ws[1]:
        if cell.value is not None:
            result[str(cell.value).strip()] = cell.column

    return result


def serialize_chunk_ids(
    evidence: list[dict[str, Any]],
) -> str:
    ids: list[str] = []

    for item in evidence:
        chunk_id = item.get(
            "chunkId",
            item.get("chunk_id"),
        )

        if chunk_id is not None:
            ids.append(str(chunk_id))

    return ", ".join(ids)


def serialize_contexts(
    evidence: list[dict[str, Any]],
) -> str:
    contexts: list[str] = []

    for rank, item in enumerate(
        evidence,
        start=1,
    ):
        chunk_id = item.get(
            "chunkId",
            item.get("chunk_id"),
        )

        section_title = item.get(
            "sectionTitle",
            item.get("section_title"),
        )

        content = item.get(
            "content",
            "",
        )

        score = item.get("score")

        parts = [f"rank={rank}"]

        if chunk_id is not None:
            parts.append(f"chunkId={chunk_id}")

        if section_title:
            parts.append(f"section={section_title}")

        if score is not None:
            parts.append(f"score={score}")

        header = "[" + " | ".join(parts) + "]"
        contexts.append(f"{header}\n{content}".strip())

    return "\n\n---\n\n".join(contexts)


def evaluate(
    input_xlsx: Path,
    output_xlsx: Path,
    announcement_id: int,
    api_base_url: str,
    endpoint: str,
    sheet_name: str,
    run_id: str,
    timeout: int,
    retry_count: int,
) -> None:
    if not input_xlsx.exists():
        raise FileNotFoundError(
            "평가셋 파일을 찾을 수 없습니다:\n"
            f"{input_xlsx}"
        )

    output_xlsx.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wb = load_workbook(input_xlsx)

    if sheet_name not in wb.sheetnames:
        raise ValueError(
            f"'{sheet_name}' 시트가 없습니다.\n"
            f"현재 시트: {wb.sheetnames}"
        )

    ws = wb[sheet_name]
    columns = find_columns(ws)

    required = [
        "question_id",
        "user_input",
        "retrieved_chunk_ids",
        "retrieved_contexts",
        "response",
        "run_id",
        "git_commit",
    ]

    missing = [
        name for name in required
        if name not in columns
    ]

    if missing:
        raise ValueError(
            "평가셋에 필요한 컬럼이 없습니다:\n"
            + ", ".join(missing)
        )

    branch, git_commit = get_git_info()

    api_url = (
        api_base_url.rstrip("/")
        + "/"
        + endpoint.lstrip("/")
    )

    total = 0
    success = 0
    failed = 0

    print("=" * 70)
    print("RAG 평가 자동 실행")
    print(f"입력 파일      : {input_xlsx}")
    print(f"출력 파일      : {output_xlsx}")
    print(f"API            : {api_url}")
    print(f"announcementId : {announcement_id}")
    print(f"run_id         : {run_id}")
    print(f"branch         : {branch or '(확인 불가)'}")
    print(f"git_commit     : {git_commit or '(확인 불가)'}")
    print("=" * 70)

    for row in range(2, ws.max_row + 1):
        question_id = ws.cell(
            row=row,
            column=columns["question_id"],
        ).value

        question = ws.cell(
            row=row,
            column=columns["user_input"],
        ).value

        if question is None:
            continue

        question = str(question).strip()

        if not question:
            continue

        total += 1

        print(
            f"\n[{total:02d}] "
            f"{question_id}: {question}"
        )

        payload = {
            "announcementId": announcement_id,
            "question": question,
        }

        response_json = None
        last_error: Exception | None = None

        for attempt in range(
            1,
            retry_count + 2,
        ):
            try:
                response_json = http_post_json(
                    api_url,
                    payload,
                    timeout,
                )
                last_error = None
                break

            except Exception as exc:
                last_error = exc

                print(
                    f"  요청 실패 "
                    f"({attempt}/{retry_count + 1}): "
                    f"{exc}"
                )

                if attempt <= retry_count:
                    time.sleep(2)

        ws.cell(
            row=row,
            column=columns["run_id"],
            value=run_id,
        )

        ws.cell(
            row=row,
            column=columns["git_commit"],
            value=git_commit,
        )

        if response_json is None:
            failed += 1

            ws.cell(
                row=row,
                column=columns["response"],
                value=f"[API ERROR] {last_error}",
            )

            wb.save(output_xlsx)
            continue

        answer = response_json.get("answer")

        if answer is None:
            answer = response_json.get(
                "response",
                "",
            )

        evidence = (
            response_json.get("evidence")
            or []
        )

        if not isinstance(evidence, list):
            evidence = []

        evidence = [
            item for item in evidence
            if isinstance(item, dict)
        ]

        chunk_ids = serialize_chunk_ids(evidence)
        contexts = serialize_contexts(evidence)

        ws.cell(
            row=row,
            column=columns["retrieved_chunk_ids"],
            value=chunk_ids,
        )

        ws.cell(
            row=row,
            column=columns["retrieved_contexts"],
            value=contexts,
        )

        ws.cell(
            row=row,
            column=columns["response"],
            value=(
                str(answer)
                if answer is not None
                else ""
            ),
        )

        success += 1

        print(f"  answer    : {str(answer)[:100]}")
        print(f"  evidence  : {len(evidence)}개")
        print(f"  chunk_ids : {chunk_ids or '(없음)'}")

        wb.save(output_xlsx)

    print("\n" + "=" * 70)
    print("평가 요청 완료")
    print(f"전체 질문 : {total}")
    print(f"성공      : {success}")
    print(f"실패      : {failed}")
    print(f"결과 파일 : {output_xlsx}")
    print("=" * 70)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "평가셋 질문을 /api/chat에 자동 전송하고 "
            "검색 결과와 답변을 Excel에 저장합니다."
        )
    )

    parser.add_argument(
        "--dataset",
        default="GC",
        help="평가셋 코드 (GC=고창율계, HC=화천신읍2)",
    )

    parser.add_argument(
        "--announcement-id",
        type=int,
        required=True,
        help="평가 대상 공고의 DB announcement ID",
    )

    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "생략하면 DEFAULT_RUN_NUMBER에 맞춰 "
            "GC_RUN_001, BD_RUN_001 형식으로 자동 설정"
        ),
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_API_BASE_URL,
    )

    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
    )

    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET_NAME,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )

    parser.add_argument(
        "--retry",
        type=int,
        default=1,
    )

    # 필요할 때만 수동 경로 지정 가능
    parser.add_argument(
        "--xlsx",
        default=None,
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        dataset = normalize_dataset_name(args.dataset)

        default_input, default_output, default_run_id = dataset_paths(
            dataset
        )

        input_xlsx = (
            Path(args.xlsx)
            if args.xlsx
            else default_input
        )

        output_xlsx = (
            Path(args.output)
            if args.output
            else default_output
        )

        run_id = (
            args.run_id
            if args.run_id
            else default_run_id
        )

        evaluate(
            input_xlsx=input_xlsx,
            output_xlsx=output_xlsx,
            announcement_id=args.announcement_id,
            api_base_url=args.base_url,
            endpoint=args.endpoint,
            sheet_name=args.sheet,
            run_id=run_id,
            timeout=args.timeout,
            retry_count=args.retry,
        )

    except KeyboardInterrupt:
        print("\n사용자가 평가를 중단했습니다.")
        sys.exit(130)

    except Exception as exc:
        print(
            "\n평가 실행 중 오류가 발생했습니다:\n"
            f"{exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
