from __future__ import annotations

"""청킹 파이프라인 실행 진입점.

직접 전체 실행:
    python chunking/run_chunking.py

    프로젝트의 outputs/announcement_*/03_structured/{hwp,hwpx}/ 아래에서
    최종 구조화 JSON을 자동 탐색하고, 대응하는
    outputs/announcement_*/04_chunks/{hwp,hwpx}/chunks.json에 저장합니다.

단일 파일 실행:
    python chunking/run_chunking.py --input <구조화 JSON> --output <chunks.json>

폴더 일괄 실행:
    python chunking/run_chunking.py --input <구조화 JSON 폴더> --output <출력 폴더>

상위 run_pipeline.py에서도 동일한 --input/--output 인자로 호출할 수 있습니다.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# 이 파일을 ``python chunking/run_chunking.py`` 형태로 직접 실행해도
# ``chunking`` 패키지를 찾을 수 있도록 프로젝트 루트를 sys.path에 추가합니다.
CHUNKING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CHUNKING_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.chunking.chunker import StructureAwareChunker  # noqa: E402
from pipeline.chunking.config import ChunkingConfig  # noqa: E402


DEFAULT_INPUT_CANDIDATES = (
    "step4-1_value_normalized.json",
    "step3-3_structured_tables.json",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "구조화된 HWP/HWPX JSON을 검증하고, 계층·문단·표 구조를 이용해 "
            "검색 및 임베딩용 chunks.json을 생성합니다."
        )
    )
    parser.add_argument(
        "--input",
        help="입력 구조화 JSON 파일 또는 JSON 파일들이 있는 폴더",
    )
    parser.add_argument(
        "--output",
        help="출력 chunks.json 파일 또는 출력 폴더",
    )
    parser.add_argument(
        "--announcement-id",
        default=None,
        help="단일 파일 실행 시 청크에 저장할 공고 ID. 생략하면 문서명으로 생성",
    )
    parser.add_argument("--target-tokens", type=int, default=500)
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--min-tokens", type=int, default=80)
    parser.add_argument("--overlap-tokens", type=int, default=80)
    parser.add_argument(
        "--tokenizer",
        default=None,
        help="선택 사항: 로컬 Hugging Face 토크나이저 경로 또는 이름",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="입력 폴더 아래의 JSON을 재귀적으로 탐색",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="일괄 처리 중 첫 실패에서 즉시 종료",
    )
    return parser


def build_config(args: argparse.Namespace) -> ChunkingConfig:
    config = ChunkingConfig(
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        min_tokens=args.min_tokens,
        overlap_tokens=args.overlap_tokens,
        tokenizer_name_or_path=args.tokenizer,
    )
    config.validate()
    return config


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path] | None:
    """명시적 입력/출력 경로를 해석합니다.

    둘 다 생략되면 ``None``을 반환하고, main에서 프로젝트 outputs 폴더를
    자동 탐색하는 기본 실행 모드로 전환합니다.
    """
    if bool(args.input) != bool(args.output):
        raise ValueError("--input과 --output은 함께 지정해야 합니다.")

    if args.input and args.output:
        return Path(args.input).resolve(), Path(args.output).resolve()

    return None


def find_outputs_root() -> Path:
    """프로젝트의 산출물 루트를 찾습니다.

    현재 프로젝트 표준 폴더명은 ``outputs``입니다. 이전 이름인 ``output``도
    호환을 위해 보조 후보로 확인합니다.
    """
    candidates = (
        PROJECT_ROOT / "outputs",
        PROJECT_ROOT / "output",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[0]


def find_pipeline_targets(outputs_root: Path) -> list[tuple[Path, Path, str, str]]:
    """구조화 최종 결과와 대응하는 청킹 출력 경로를 찾습니다.

    반환값: ``(input_path, output_path, announcement_id, document_format)``

    입력 우선순위:
    1. step4-1_value_normalized.json
    2. step3-3_structured_tables.json (이전 결과 호환)
    """
    targets: list[tuple[Path, Path, str, str]] = []

    if not outputs_root.exists():
        return targets

    announcement_dirs = sorted(
        path
        for path in outputs_root.iterdir()
        if path.is_dir() and path.name.startswith("announcement_")
    )

    for announcement_dir in announcement_dirs:
        structured_root = announcement_dir / "03_structured"
        if not structured_root.exists():
            continue

        for document_format in ("hwp", "hwpx"):
            format_dir = structured_root / document_format
            if not format_dir.exists():
                continue

            input_path: Path | None = None
            for filename in DEFAULT_INPUT_CANDIDATES:
                candidate = format_dir / filename
                if candidate.exists() and candidate.is_file():
                    input_path = candidate
                    break

            if input_path is None:
                continue

            output_path = (
                announcement_dir
                / "04_chunks"
                / document_format
                / "chunks.json"
            )
            targets.append(
                (
                    input_path,
                    output_path,
                    announcement_dir.name,
                    document_format,
                )
            )

    return targets


def chunk_pipeline_outputs(
    *,
    chunker: StructureAwareChunker,
    outputs_root: Path,
    fail_fast: bool,
) -> int:
    """outputs 전체에서 구조화 결과를 찾아 청킹합니다."""
    targets = find_pipeline_targets(outputs_root)

    if not outputs_root.exists():
        print(
            f"[ERROR] outputs 폴더를 찾을 수 없습니다: {outputs_root}",
            file=sys.stderr,
        )
        return 2

    if not targets:
        print(
            "[ERROR] 청킹할 최종 구조화 JSON을 찾을 수 없습니다.",
            file=sys.stderr,
        )
        print(
            "탐색 경로: "
            f"{outputs_root}/announcement_*/03_structured/"
            "{hwp,hwpx}/step4-1_value_normalized.json",
            file=sys.stderr,
        )
        return 2

    print()
    print("=" * 70)
    print("전체 구조화 JSON 청킹")
    print("=" * 70)
    print(f"outputs 루트: {outputs_root}")
    print(f"대상 파일   : {len(targets)}개")
    for input_path, output_path, announcement_id, document_format in targets:
        print(
            f"- {announcement_id}/{document_format}: "
            f"{input_path.name} -> {output_path}"
        )

    success_count = 0
    failures: list[tuple[Path, str]] = []

    for input_path, output_path, announcement_id, _ in targets:
        try:
            chunk_one_file(
                chunker=chunker,
                input_path=input_path,
                output_path=output_path,
                announcement_id=announcement_id,
            )
            success_count += 1
        except Exception as error:
            failures.append((input_path, str(error)))
            print()
            print(f"[ERROR] 청킹 실패: {input_path}", file=sys.stderr)
            print(str(error), file=sys.stderr)
            if fail_fast:
                break

    print()
    print("=" * 70)
    print("전체 청킹 결과")
    print("=" * 70)
    print(f"성공: {success_count}")
    print(f"실패: {len(failures)}")

    if failures:
        for path, message in failures:
            print(f"- {path}: {message}", file=sys.stderr)
        return 1

    return 0


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")

    temporary_path.replace(path)


def print_result_summary(
    input_path: Path,
    output_path: Path,
    result: dict[str, Any],
) -> None:
    report = result.get("report", {})
    token_stats = report.get("token_stats", {})

    print()
    print("[청킹 완료]")
    print(f"입력          : {input_path}")
    print(f"출력          : {output_path}")
    print(f"총 청크 수    : {report.get('total_chunks', 0)}")
    print(f"청크 유형     : {report.get('chunk_types', {})}")
    print(f"최대 토큰 수  : {token_stats.get('max', 0)}")
    print(f"평균 토큰 수  : {token_stats.get('average', 0)}")
    print(f"최대 초과 청크: {token_stats.get('over_max_count', 0)}")

    warnings = report.get("warnings") or []
    source_warnings = report.get("source_value_normalization_warnings") or []
    if warnings:
        print(f"청킹 경고     : {len(warnings)}건")
    if source_warnings:
        print(f"원본 정규화 경고: {len(source_warnings)}건")


def chunk_one_file(
    *,
    chunker: StructureAwareChunker,
    input_path: Path,
    output_path: Path,
    announcement_id: str | None,
) -> dict[str, Any]:
    if input_path.suffix.lower() != ".json":
        raise ValueError(f"JSON 파일만 처리할 수 있습니다: {input_path}")
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    print()
    print("=" * 70)
    print("청킹 파이프라인 시작")
    print("=" * 70)
    print(f"입력: {input_path}")
    print(f"출력: {output_path}")
    print("단계: 입력 검증 → intro 처리 → section 재귀 순회 → 문단 청킹")
    print("      → 표 청킹 → 검색/임베딩 텍스트 생성 → 결과 검증 및 저장")

    # StructureAwareChunker 내부에서 다음 과정이 모두 순서대로 실행됩니다.
    # 1) StructuredJsonValidator 입력 검증
    # 2) intro 청킹
    # 3) sections/children 재귀 순회
    # 4) paragraph/table 분기 처리
    # 5) content/search_text/embedding_text 생성
    # 6) 청크 통계 및 경고 리포트 생성
    result = chunker.chunk_file(
        input_path,
        announcement_id=announcement_id,
    )

    validate_chunk_result(result, input_path=input_path)
    save_json(output_path, result)
    print_result_summary(input_path, output_path, result)
    return result


def validate_chunk_result(result: dict[str, Any], *, input_path: Path) -> None:
    """저장 전 최소 출력 계약을 검사합니다."""
    if not isinstance(result, dict):
        raise ValueError(f"청킹 결과가 객체가 아닙니다: {input_path}")

    chunks = result.get("chunks")
    report = result.get("report")
    document = result.get("document")

    if not isinstance(document, dict):
        raise ValueError("청킹 결과 document가 없습니다.")
    if not isinstance(chunks, list):
        raise ValueError("청킹 결과 chunks가 배열이 아닙니다.")
    if not isinstance(report, dict):
        raise ValueError("청킹 결과 report가 없습니다.")

    ids: set[str] = set()
    expected_order = 1
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"chunks[{index}]가 객체가 아닙니다.")

        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"chunks[{index}].chunk_id가 없습니다.")
        if chunk_id in ids:
            raise ValueError(f"중복 chunk_id가 있습니다: {chunk_id}")
        ids.add(chunk_id)

        if chunk.get("chunk_order") != expected_order:
            raise ValueError(
                f"chunk_order가 연속적이지 않습니다: "
                f"예상 {expected_order}, 실제 {chunk.get('chunk_order')}"
            )
        expected_order += 1

        if not str(chunk.get("content") or "").strip():
            raise ValueError(f"빈 content 청크가 있습니다: {chunk_id}")
        if not str(chunk.get("search_text") or "").strip():
            raise ValueError(f"빈 search_text 청크가 있습니다: {chunk_id}")
        if not str(chunk.get("embedding_text") or "").strip():
            raise ValueError(f"빈 embedding_text 청크가 있습니다: {chunk_id}")

    if report.get("total_chunks") != len(chunks):
        raise ValueError(
            "report.total_chunks와 실제 chunks 개수가 일치하지 않습니다."
        )


def find_json_files(input_dir: Path, *, recursive: bool) -> list[Path]:
    iterator = input_dir.rglob("*.json") if recursive else input_dir.glob("*.json")
    return sorted(path for path in iterator if path.is_file())


def make_batch_output_path(
    *,
    input_dir: Path,
    input_file: Path,
    output_dir: Path,
    recursive: bool,
) -> Path:
    if recursive:
        relative_parent = input_file.relative_to(input_dir).parent
        target_dir = output_dir / relative_parent
    else:
        target_dir = output_dir

    return target_dir / f"{input_file.stem}_chunks.json"


def chunk_directory(
    *,
    chunker: StructureAwareChunker,
    input_dir: Path,
    output_dir: Path,
    recursive: bool,
    fail_fast: bool,
) -> int:
    if not input_dir.exists():
        print(f"[ERROR] 입력 폴더를 찾을 수 없습니다: {input_dir}", file=sys.stderr)
        return 2

    files = find_json_files(input_dir, recursive=recursive)
    if not files:
        print(f"[ERROR] 처리할 JSON 파일이 없습니다: {input_dir}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    success_count = 0
    failures: list[tuple[Path, str]] = []

    print()
    print("=" * 70)
    print("JSON 일괄 청킹")
    print("=" * 70)
    print(f"입력 폴더: {input_dir}")
    print(f"출력 폴더: {output_dir}")
    print(f"대상 파일: {len(files)}개")

    for input_file in files:
        output_file = make_batch_output_path(
            input_dir=input_dir,
            input_file=input_file,
            output_dir=output_dir,
            recursive=recursive,
        )
        try:
            chunk_one_file(
                chunker=chunker,
                input_path=input_file,
                output_path=output_file,
                announcement_id=None,
            )
            success_count += 1
        except Exception as error:
            failures.append((input_file, str(error)))
            print()
            print(f"[ERROR] 청킹 실패: {input_file}", file=sys.stderr)
            print(str(error), file=sys.stderr)
            if fail_fast:
                break

    print()
    print("=" * 70)
    print("JSON 일괄 청킹 결과")
    print("=" * 70)
    print(f"성공: {success_count}")
    print(f"실패: {len(failures)}")

    if failures:
        for path, message in failures:
            print(f"- {path}: {message}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        resolved_paths = resolve_paths(args)
        config = build_config(args)
        chunker = StructureAwareChunker(config)

        # 인자가 없으면 프로젝트 표준 outputs 구조 전체를 자동 처리합니다.
        if resolved_paths is None:
            return chunk_pipeline_outputs(
                chunker=chunker,
                outputs_root=find_outputs_root(),
                fail_fast=args.fail_fast,
            )

        input_path, output_path = resolved_paths

        if input_path.is_file():
            chunk_one_file(
                chunker=chunker,
                input_path=input_path,
                output_path=output_path,
                announcement_id=args.announcement_id,
            )
            return 0

        if input_path.is_dir():
            return chunk_directory(
                chunker=chunker,
                input_dir=input_path,
                output_dir=output_path,
                recursive=args.recursive,
                fail_fast=args.fail_fast,
            )

        print(f"[ERROR] 입력 경로를 찾을 수 없습니다: {input_path}", file=sys.stderr)
        return 2

    except KeyboardInterrupt:
        print("\n[중단] 사용자 요청으로 청킹을 중단했습니다.", file=sys.stderr)
        return 130
    except Exception as error:
        print()
        print("[ERROR] 청킹 파이프라인 실행 실패", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())