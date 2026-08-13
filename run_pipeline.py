from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from config.paths import (
    OUTPUT_ROOT,
    TEST_DOCUMENT_ROOT,
    ensure_document_output_paths,
)


BASE_DIR = Path(__file__).resolve().parent

PARSER_DIR = BASE_DIR / "pipeline" / "parser"
NORMALIZER_DIR = BASE_DIR / "pipeline" / "normalizer"
STRUCTURE_DIR = BASE_DIR / "pipeline" / "structure"
CHUNKING_DIR = BASE_DIR / "pipeline" / "chunking"
EMBEDDING_DIR = BASE_DIR / "pipeline" / "embedding"

TEST_DOCUMENT_DIR = TEST_DOCUMENT_ROOT
OUTPUT_DIR = OUTPUT_ROOT

HWP_PARSER_PATH = PARSER_DIR / "hwp_parser.py"
HWPX_PARSER_PATH = PARSER_DIR / "hwpx_parser.py"
COMPARE_PARSER_PATH = PARSER_DIR / "compare_parsers.py"
NORMALIZER_PATH = NORMALIZER_DIR / "document_normalizer.py"
STRUCTURE_RUNNER_PATH = STRUCTURE_DIR / "run_structure.py"
STRUCTURE_STEP1_PATH = STRUCTURE_DIR / "build_document_step1.py"
STRUCTURE_STEP2_PATH = STRUCTURE_DIR / "build_domain_step2.py"
STRUCTURE_STEP3_PATH = STRUCTURE_DIR / "build_table_step3.py"
CHUNKING_RUNNER_PATH = CHUNKING_DIR / "run_chunking.py"
EMBEDDING_RUNNER_PATH = EMBEDDING_DIR / "run_embeddings.py"

HWP_JAR_PATH = PARSER_DIR / "libs" / "hwp" / "hwplib-1.1.10.jar"
HWPX_JAR_PATH = PARSER_DIR / "libs" / "hwpx" / "hwpxlib-1.0.8.jar"


DocumentGroups = dict[str, dict[str, list[Path]]]


def ensure_directories() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_document_id(file_path: Path) -> str:
    relative_path = file_path.relative_to(TEST_DOCUMENT_DIR)

    if len(relative_path.parts) > 1:
        return relative_path.parts[0]

    return file_path.stem


def find_test_documents() -> dict[str, list[Path]]:
    if not TEST_DOCUMENT_DIR.exists():
        return {"hwp": [], "hwpx": []}

    hwp_files = sorted(
        path
        for path in TEST_DOCUMENT_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() == ".hwp"
    )
    hwpx_files = sorted(
        path
        for path in TEST_DOCUMENT_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() == ".hwpx"
    )

    return {
        "hwp": hwp_files,
        "hwpx": hwpx_files,
    }


def group_test_documents() -> DocumentGroups:
    documents = find_test_documents()
    groups: defaultdict[str, dict[str, list[Path]]] = defaultdict(
        lambda: {"hwp": [], "hwpx": []}
    )

    for document_format in ("hwp", "hwpx"):
        for file_path in documents[document_format]:
            document_id = get_document_id(file_path)
            groups[document_id][document_format].append(file_path)

    return dict(sorted(groups.items()))


def get_document_processing_status(
    data: dict[str, list[Path]],
) -> dict[str, object]:
    has_hwp = bool(data.get("hwp"))
    has_hwpx = bool(data.get("hwpx"))

    formats: list[str] = []
    if has_hwp:
        formats.append("hwp")
    if has_hwpx:
        formats.append("hwpx")

    return {
        "processable": has_hwp or has_hwpx,
        "comparable": has_hwp and has_hwpx,
        "formats": formats,
    }


def print_document_summary() -> None:
    documents = find_test_documents()
    groups = group_test_documents()

    processable_count = sum(
        1
        for data in groups.values()
        if bool(get_document_processing_status(data)["processable"])
    )
    comparable_count = sum(
        1
        for data in groups.values()
        if bool(get_document_processing_status(data)["comparable"])
    )

    print()
    print("=" * 70)
    print("테스트 문서 자동 탐색 결과")
    print("=" * 70)
    print(f"HWP 파일  : {len(documents['hwp'])}개")
    print(f"HWPX 파일 : {len(documents['hwpx'])}개")
    print(f"문서 그룹 : {len(groups)}개")
    print(f"분석 가능 그룹 : {processable_count}개")
    print(f"HWP/HWPX 비교 가능 그룹 : {comparable_count}개")
    print()

    if not groups:
        print("[안내] 분석 가능한 HWP/HWPX 문서가 없습니다.")
        return

    for document_id, data in groups.items():
        status = get_document_processing_status(data)
        formats = ", ".join(status["formats"]) if status["formats"] else "없음"

        print(f"- {document_id}")
        print(f"    HWP       : {len(data['hwp'])}개" if data["hwp"] else "    HWP       : 없음")
        print(f"    HWPX      : {len(data['hwpx'])}개" if data["hwpx"] else "    HWPX      : 없음")
        print(f"    분석 형식 : {formats}")
        print(f"    분석 가능 : {'가능' if status['processable'] else '불가'}")
        print(f"    비교 가능 : {'가능' if status['comparable'] else '불가'}")
        print()


def validate_project_files() -> bool:
    if not TEST_DOCUMENT_DIR.exists():
        print()
        print("[ERROR] test_documents 폴더가 없습니다.")
        print(TEST_DOCUMENT_DIR)
        return False

    documents = find_test_documents()
    groups = group_test_documents()

    # Parser → Normalizer → Structure까지는 현재 필수 단계입니다.
    # Chunking/Embedding은 팀원이 아직 구현 중이어도 앞 단계 실행을 막지 않습니다.
    required_files = [
        NORMALIZER_PATH,
        STRUCTURE_RUNNER_PATH,
        STRUCTURE_STEP1_PATH,
        STRUCTURE_STEP2_PATH,
        STRUCTURE_STEP3_PATH,
    ]

    if documents["hwp"]:
        required_files.extend([HWP_PARSER_PATH, HWP_JAR_PATH])

    if documents["hwpx"]:
        required_files.extend([HWPX_PARSER_PATH, HWPX_JAR_PATH])

    has_comparable_document = any(
        bool(get_document_processing_status(data)["comparable"])
        for data in groups.values()
    )
    if has_comparable_document and not COMPARE_PARSER_PATH.exists():
        print()
        print("[안내] compare_parsers.py가 없어 HWP/HWPX 비교 단계는 건너뜁니다.")

    missing_files = [path for path in required_files if not path.exists()]

    if missing_files:
        print()
        print("[ERROR] 필수 파일을 찾을 수 없습니다.")
        for path in missing_files:
            print(f"- {path}")
        return False

    optional_files = {
        "청킹": [CHUNKING_RUNNER_PATH],
        "임베딩": [EMBEDDING_RUNNER_PATH],
    }
    for stage, paths in optional_files.items():
        missing_optional = [path for path in paths if not path.exists()]
        if missing_optional:
            print()
            print(f"[안내] {stage} 단계는 아직 실행할 수 없어 자동으로 건너뜁니다.")
            for path in missing_optional:
                print(f"- 없음: {path}")

    return True


def run_command(command: list[str]) -> bool:
    print()
    print("-" * 70)
    print("실행:")
    print(" ".join(str(item) for item in command))
    print("-" * 70)

    try:
        subprocess.run(
            command,
            cwd=str(BASE_DIR),
            check=True,
        )
        return True
    except subprocess.CalledProcessError as error:
        print()
        print("[ERROR] 실행 실패")
        print(f"Return Code: {error.returncode}")
        return False
    except Exception as error:
        print()
        print("[ERROR] 예외 발생")
        print(error)
        return False


def get_output_path(document_id: str, document_format: str) -> Path:
    if document_format not in {"hwp", "hwpx"}:
        raise ValueError(f"지원하지 않는 문서 형식입니다: {document_format}")

    paths = ensure_document_output_paths(document_id)
    return paths.parsed / f"{document_format}.json"


def parse_hwp_file(file_path: Path, document_id: str) -> bool:
    output_path = get_output_path(document_id, "hwp")

    print()
    print("[HWP 파싱]")
    print(f"문서 ID: {document_id}")
    print(f"입력: {file_path}")
    print(f"출력: {output_path}")

    return run_command(
        [
            sys.executable,
            str(HWP_PARSER_PATH),
            "--hwp_jar_path",
            str(HWP_JAR_PATH),
            "--file_path",
            str(file_path),
            "--output_path",
            str(output_path),
        ]
    )


def parse_hwpx_file(file_path: Path, document_id: str) -> bool:
    output_path = get_output_path(document_id, "hwpx")

    print()
    print("[HWPX 파싱]")
    print(f"문서 ID: {document_id}")
    print(f"입력: {file_path}")
    print(f"출력: {output_path}")

    return run_command(
        [
            sys.executable,
            str(HWPX_PARSER_PATH),
            "--hwpx_jar_path",
            str(HWPX_JAR_PATH),
            "--file_path",
            str(file_path),
            "--output_path",
            str(output_path),
        ]
    )



def run_parser_for_format(document_format: str) -> bool:
    groups = group_test_documents()

    targets = [
        (document_id, file_path)
        for document_id, data in groups.items()
        for file_path in data[document_format]
    ]

    if not targets:
        print()
        print(
            f"[안내] 분석할 "
            f"{document_format.upper()} 파일이 없습니다."
        )
        return True

    print()
    print("=" * 70)
    print(f"{document_format.upper()} 전체 파싱")
    print("=" * 70)
    print(f"대상: {len(targets)}개")

    success = 0
    fail = 0

    for document_id, file_path in targets:
        if document_format == "hwp":
            result = parse_hwp_file(
                file_path,
                document_id,
            )
        else:
            result = parse_hwpx_file(
                file_path,
                document_id,
            )

        if result:
            success += 1
        else:
            fail += 1

    print()
    print(
        f"{document_format.upper()} 파싱 완료 "
        f"- 성공: {success}, 실패: {fail}"
    )

    return fail == 0


def run_hwp_parser() -> bool:
    return run_parser_for_format("hwp")


def run_hwpx_parser() -> bool:
    return run_parser_for_format("hwpx")


def run_all_parsers() -> bool:
    hwp_ok = run_hwp_parser()
    hwpx_ok = run_hwpx_parser()

    return hwp_ok and hwpx_ok

def run_compare() -> None:
    if not COMPARE_PARSER_PATH.exists():
        print()
        print("[안내] compare_parsers.py가 없어 비교 단계를 건너뜁니다.")
        return

    groups = group_test_documents()
    comparison_targets: list[tuple[str, Path, Path]] = []

    for document_id, data in groups.items():
        status = get_document_processing_status(data)
        if not status["comparable"]:
            continue

        hwp_json = get_output_path(document_id, "hwp")
        hwpx_json = get_output_path(document_id, "hwpx")

        if hwp_json.exists() and hwpx_json.exists():
            comparison_targets.append((document_id, hwp_json, hwpx_json))

    if not comparison_targets:
        print()
        print("[안내] HWP/HWPX 비교 가능한 문서가 없습니다.")
        print("단일 형식 문서는 정상적으로 다음 단계로 진행합니다.")
        return

    print()
    print("=" * 70)
    print("HWP / HWPX Parser 결과 비교")
    print("=" * 70)

    for document_id, hwp_json, hwpx_json in comparison_targets:
        print()
        print(f"[비교] {document_id}")
        run_command(
            [
                sys.executable,
                str(COMPARE_PARSER_PATH),
                "--hwp",
                str(hwp_json),
                "--hwpx",
                str(hwpx_json),
            ]
        )


def find_stage_files(
    *,
    stage_name: str,
    filename: str,
) -> list[Path]:
    files: list[Path] = []
    groups = group_test_documents()

    for document_id, data in groups.items():
        paths = ensure_document_output_paths(document_id)
        stage_root = getattr(paths, stage_name)

        for document_format in ("hwp", "hwpx"):
            if not data[document_format]:
                continue

            if stage_name in {"parsed", "normalized"}:
                path = stage_root / f"{document_format}.json"
            else:
                path = stage_root / document_format / filename

            if path.exists():
                files.append(path)

    return sorted(files)


def find_raw_json_files() -> list[Path]:
    return find_stage_files(stage_name="parsed", filename="")


def normalize_file(input_path: Path) -> bool:
    document_id = input_path.parent.parent.name
    paths = ensure_document_output_paths(document_id)
    output_path = paths.normalized / input_path.name

    print()
    print(f"[정규화] {document_id}")
    print(f"입력: {input_path}")
    print(f"출력: {output_path}")

    return run_command(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )



def run_all_items(
    *,
    title: str,
    files: list[Path],
    processor,
    empty_message: str,
) -> bool:
    if not files:
        print()
        print(empty_message)
        return False

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"대상: {len(files)}개")

    success = 0
    fail = 0

    for file_path in files:
        if processor(file_path):
            success += 1
        else:
            fail += 1

    print()
    print("=" * 70)
    print(f"{title} 완료")
    print(f"성공: {success}")
    print(f"실패: {fail}")
    print("=" * 70)

    return fail == 0


def normalize_all() -> bool:
    return run_all_items(
        title="전체 JSON 정규화",
        files=find_raw_json_files(),
        processor=normalize_file,
        empty_message=(
            "[안내] 정규화할 Parser JSON이 없습니다. "
            "먼저 Parser를 실행하세요."
        ),
    )

def find_normalized_json_files() -> list[Path]:
    return find_stage_files(stage_name="normalized", filename="")


def structure_file(input_path: Path) -> bool:
    document_id = input_path.parent.parent.name
    document_format = input_path.stem.lower()

    if document_format not in {"hwp", "hwpx"}:
        print()
        print(f"[ERROR] 알 수 없는 정규화 문서 형식입니다: {document_format}")
        return False

    paths = ensure_document_output_paths(document_id)
    output_dir = paths.structured / document_format
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print(f"[구조화] {document_id}")
    print(f"형식: {document_format}")
    print(f"입력: {input_path}")
    print(f"출력: {output_dir}")

    return run_command(
        [
            sys.executable,
            str(STRUCTURE_RUNNER_PATH),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ]
    )



def structure_all() -> bool:
    return run_all_items(
        title="전체 JSON 구조화",
        files=find_normalized_json_files(),
        processor=structure_file,
        empty_message=(
            "[안내] 구조화할 정규화 JSON이 없습니다. "
            "먼저 정규화를 실행하세요."
        ),
    )

def find_structured_json_files() -> list[Path]:
    """청킹에 사용할 Structure 최종 결과를 찾습니다.

    우선순위:
    1. Step 4 값 정규화 결과
    2. Step 3 구조화 결과(이전 실행 결과 호환용)
    """
    value_normalized = find_stage_files(
        stage_name="structured",
        filename="step4-1_value_normalized.json",
    )
    if value_normalized:
        return value_normalized

    return find_stage_files(
        stage_name="structured",
        filename="step3-3_structured_tables.json",
    )


def chunk_file(input_path: Path) -> bool:
    document_format = input_path.parent.name.lower()
    document_id = input_path.parent.parent.parent.name

    if document_format not in {"hwp", "hwpx"}:
        print()
        print(f"[ERROR] 알 수 없는 구조화 문서 형식입니다: {document_format}")
        return False

    paths = ensure_document_output_paths(document_id)
    output_dir = paths.chunks / document_format
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "chunks.json"

    print()
    print(f"[청킹] {document_id}")
    print(f"형식: {document_format}")
    print(f"입력: {input_path}")
    print(f"출력: {output_path}")

    return run_command(
        [
            sys.executable,
            str(CHUNKING_RUNNER_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--announcement-id",
            document_id,
        ]
    )



def chunk_all() -> bool:
    if not CHUNKING_RUNNER_PATH.exists():
        print()
        print(
            "[ERROR] chunking/run_chunking.py가 없어 "
            "청킹 단계를 실행할 수 없습니다."
        )
        return False

    return run_all_items(
        title="전체 JSON 청킹",
        files=find_structured_json_files(),
        processor=chunk_file,
        empty_message=(
            "[안내] 청킹할 최종 구조화 JSON이 없습니다. "
            "먼저 구조화를 실행하세요."
        ),
    )

def embedding_result_exists(
    document_id: str,
    document_format: str,
) -> bool:
    paths = ensure_document_output_paths(document_id)
    embedding_dir = paths.embeddings / document_format

    return (
        (embedding_dir / "embeddings.npy").exists()
        and (embedding_dir / "metadata.json").exists()
    )


def find_chunk_json_files() -> list[Path]:
    """
    공고별 대표 Chunk JSON 하나만 선택합니다.

    우선순위:
    1. HWPX
    2. HWP

    Parser/Normalizer/Structure/Chunk 결과는 형식별로 모두 보존하지만,
    실제 검색용 임베딩은 공고당 대표 형식 하나만 생성합니다.
    """

    selected_files: list[Path] = []
    groups = group_test_documents()

    for document_id, data in groups.items():
        paths = ensure_document_output_paths(document_id)

        selected_path: Path | None = None

        if data["hwpx"]:
            hwpx_path = (
                paths.chunks
                / "hwpx"
                / "chunks.json"
            )
            if hwpx_path.exists():
                selected_path = hwpx_path

        elif data["hwp"]:
            hwp_path = (
                paths.chunks
                / "hwp"
                / "chunks.json"
            )
            if hwp_path.exists():
                selected_path = hwp_path

        if selected_path is not None:
            selected_files.append(selected_path)

    return sorted(selected_files)


def embed_all() -> bool:
    if not EMBEDDING_RUNNER_PATH.exists():
        print()
        print(
            "[ERROR] embedding/run_embeddings.py가 없어 "
            "임베딩 단계를 실행할 수 없습니다."
        )
        return False

    files = find_chunk_json_files()

    if not files:
        print()
        print(
            "[안내] 임베딩할 chunks.json이 없습니다. "
            "먼저 청킹을 실행하세요."
        )
        return False

    print()
    print("=" * 70)
    print("전체 Chunk Embedding")
    print("=" * 70)
    print(f"대상: {len(files)}개")

    for file_path in files:
        print(f"- {file_path}")

    command = [
        sys.executable,
        str(EMBEDDING_RUNNER_PATH),
        "--inputs",
        *[str(file_path) for file_path in files],
    ]

    result = run_command(command)

    print()
    print("=" * 70)

    if result:
        print("전체 Embedding 완료")
    else:
        print("[ERROR] Embedding Pipeline 실패")

    print("=" * 70)

    return result




def persist_pipeline_outputs() -> bool:
    backend_dir = BASE_DIR / "backend"

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from backend.app.services.pipeline_persistence import (
            persist_registered_outputs,
        )

        announcement_keys = (
            group_test_documents().keys()
        )

        result = persist_registered_outputs(
            announcement_keys
        )

    except Exception as error:
        print()
        print("=" * 70)
        print("[ERROR] DB Persistence 실패")
        print(error)
        print("=" * 70)
        return False

    print()
    print("=" * 70)
    print("DB Persistence 완료")
    print("=" * 70)

    print(
        "DB 등록 공고:",
        result["registered_keys"],
    )
    print(
        "Persistence 대상:",
        result["targets"],
    )

    for item in result["results"]:
        print()
        print(
            f"- {item['announcement_key']}"
        )
        print(
            "  processing_run_id:",
            item["processing_run_id"],
        )
        print(
            "  chunk_set_id:",
            item["chunk_set_id"],
        )
        print(
            "  chunks:",
            item["chunks"],
        )
        print(
            "  embeddings:",
            item["embeddings"],
        )
        print(
            "  deactivated_runs:",
            item["deactivated_runs"],
        )

    return True


def run_full_pipeline() -> bool:
    print()
    print("=" * 70)
    print("전체 Document Pipeline 시작")
    print("=" * 70)

    if not run_all_parsers():
        print("[ERROR] Parser 단계 실패 - Pipeline 중단")
        return False

    # HWP/HWPX 비교는 검증용 보조 단계이므로
    # 이후 처리의 필수 입력은 아닙니다.
    run_compare()

    if not normalize_all():
        print("[ERROR] Normalizer 단계 실패 - Pipeline 중단")
        return False

    if not structure_all():
        print("[ERROR] Structure 단계 실패 - Pipeline 중단")
        return False

    if not chunk_all():
        print("[ERROR] Chunking 단계 실패 - Pipeline 중단")
        return False

    if not embed_all():
        print("[ERROR] Embedding 단계 실패 - Pipeline 중단")
        return False

    if not persist_pipeline_outputs():
        print("[ERROR] DB Persistence 실패 - Pipeline 중단")
        return False

    print()
    print("=" * 70)
    print("전체 Document Pipeline 완료")
    print("=" * 70)

    return True

def print_menu() -> None:
    print()
    print("=" * 70)
    print("Hancom AI Document Pipeline")
    print("=" * 70)
    print("1. 테스트 문서 현황 확인")
    print("2. HWP 전체 파싱")
    print("3. HWPX 전체 파싱")
    print("4. 분석 가능한 문서 전체 파싱")
    print("5. HWP/HWPX 비교 가능한 문서 비교")
    print("6. Parser JSON 전체 정규화")
    print("7. 정규화 JSON 전체 구조화")
    print("8. 최종 구조화 JSON 전체 청킹")
    print("9. 공고별 대표 Chunk JSON 임베딩")
    print("10. 전체 Pipeline 실행")
    print("0. 종료")
    print("=" * 70)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HWP/HWPX 문서 처리 파이프라인 실행기"
    )
    parser.add_argument(
        "--stage",
        choices=[
            "menu", "status", "parse", "compare", "normalize",
            "structure", "chunk", "embed", "full",
        ],
        default="menu",
        help="실행할 단계. 기본값은 대화형 menu입니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    ensure_directories()

    if not validate_project_files():
        print()
        print("Pipeline을 실행할 수 없습니다.")
        raise SystemExit(1)

    actions = {
        "status": print_document_summary,
        "parse": run_all_parsers,
        "compare": run_compare,
        "normalize": normalize_all,
        "structure": structure_all,
        "chunk": chunk_all,
        "embed": embed_all,
        "full": run_full_pipeline,
    }

    if args.stage != "menu":
        result = actions[args.stage]()

        if result is False:
            raise SystemExit(1)

        return

    print_document_summary()

    while True:
        print_menu()
        choice = input("선택: ").strip()

        if choice == "1":
            print_document_summary()
        elif choice == "2":
            run_hwp_parser()
        elif choice == "3":
            run_hwpx_parser()
        elif choice == "4":
            run_all_parsers()
        elif choice == "5":
            run_compare()
        elif choice == "6":
            normalize_all()
        elif choice == "7":
            structure_all()
        elif choice == "8":
            chunk_all()
        elif choice == "9":
            embed_all()
        elif choice == "10":
            run_full_pipeline()
        elif choice == "0":
            print()
            print("Pipeline을 종료합니다.")
            break
        else:
            print()
            print("[안내] 올바른 번호를 입력하세요.")


if __name__ == "__main__":
    main()