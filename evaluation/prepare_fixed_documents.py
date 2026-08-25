from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# ============================================================
# 프로젝트 루트를 Python import 경로에 추가
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from pipeline.parser.format_detector import detect_actual_document_format

# ============================================================
# 기본 경로
# ============================================================

EVALUATION_DIR = PROJECT_ROOT / "evaluation"
SOURCE_ROOT = EVALUATION_DIR / "source_documents"
OUTPUT_ROOT = EVALUATION_DIR / "outputs"

PARSER_DIR = PROJECT_ROOT / "pipeline" / "parser"
NORMALIZER_DIR = PROJECT_ROOT / "pipeline" / "normalizer"
STRUCTURE_DIR = PROJECT_ROOT / "pipeline" / "structure"
CHUNKING_DIR = PROJECT_ROOT / "pipeline" / "chunking"
EMBEDDING_DIR = PROJECT_ROOT / "pipeline" / "embedding"

HWP_PARSER_PATH = PARSER_DIR / "hwp_parser.py"
HWPX_PARSER_PATH = PARSER_DIR / "hwpx_parser.py"
NORMALIZER_PATH = NORMALIZER_DIR / "document_normalizer.py"
STRUCTURE_RUNNER_PATH = STRUCTURE_DIR / "run_structure.py"
CHUNKING_RUNNER_PATH = CHUNKING_DIR / "run_chunking.py"
EMBEDDING_RUNNER_PATH = EMBEDDING_DIR / "run_embeddings.py"

HWP_JAR_PATH = (
    PARSER_DIR
    / "libs"
    / "hwp"
    / "hwplib-1.1.10.jar"
)

HWPX_JAR_PATH = (
    PARSER_DIR
    / "libs"
    / "hwpx"
    / "hwpxlib-1.0.8.jar"
)

PARSER_ALIAS_ROOT = (
    OUTPUT_ROOT
    / "_parser_aliases"
)


# ============================================================
# 고정 평가 Dataset 매핑
# ============================================================

FIXED_DATASETS = {
    "GC": "DOC_GC_001",
    "BD": "DOC_BD_001",
}


class FixedDocumentPreparationError(RuntimeError):
    """고정 평가 문서 처리 실패."""


# ============================================================
# 공통 함수
# ============================================================

def _run_command(
    command: list[str],
    *,
    stage: str,
) -> None:
    print()
    print("-" * 78)
    print(f"[{stage}]")
    print(" ".join(str(item) for item in command))
    print("-" * 78)

    env = os.environ.copy()

    current_pythonpath = (
        env.get("PYTHONPATH", "").strip()
    )

    if current_pythonpath:
        env["PYTHONPATH"] = (
            str(PROJECT_ROOT)
            + os.pathsep
            + current_pythonpath
        )
    else:
        env["PYTHONPATH"] = str(PROJECT_ROOT)

    try:
        subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            check=True,
        )

    except subprocess.CalledProcessError as exc:
        raise FixedDocumentPreparationError(
            f"{stage} 단계 실패: exit_code={exc.returncode}"
        ) from exc


def _dataset_document_id(
    dataset: str,
) -> str:
    dataset = dataset.strip().upper()

    document_id = FIXED_DATASETS.get(
        dataset
    )

    if document_id is None:
        raise FixedDocumentPreparationError(
            "지원하지 않는 dataset입니다: "
            f"{dataset}\n"
            "사용 가능: "
            + ", ".join(
                sorted(FIXED_DATASETS)
            )
        )

    return document_id


def _source_directory(
    document_id: str,
) -> Path:
    return (
        SOURCE_ROOT
        / document_id
    ).resolve()


def _document_output_root(
    document_id: str,
) -> Path:
    root = (
        OUTPUT_ROOT
        / document_id
    ).resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return root


def _find_source_documents(
    document_id: str,
) -> dict[str, list[Path]]:
    source_dir = _source_directory(
        document_id
    )

    if not source_dir.is_dir():
        raise FileNotFoundError(
            "고정 평가 원본 폴더가 없습니다: "
            f"{source_dir}"
        )

    documents: dict[
        str,
        list[Path],
    ] = {
        "hwp": [],
        "hwpx": [],
    }

    candidates = sorted(
        path
        for path
        in source_dir.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in {".hwp", ".hwpx"}
        )
    )

    if not candidates:
        raise FixedDocumentPreparationError(
            "HWP/HWPX 원본 문서가 없습니다: "
            f"{source_dir}"
        )

    for path in candidates:
        actual_format = (
            detect_actual_document_format(
                path
            )
        )

        if actual_format not in {
            "hwp",
            "hwpx",
        }:
            raise FixedDocumentPreparationError(
                "문서 내부 형식을 판별할 수 없습니다: "
                f"{path}"
            )

        documents[
            actual_format
        ].append(
            path
        )

    return documents


def _stage_paths(
    *,
    document_id: str,
    document_format: str,
) -> dict[str, Path]:
    root = _document_output_root(
        document_id
    )

    parsed_dir = (
        root
        / "01_parsed"
    )

    normalized_dir = (
        root
        / "02_normalized"
    )

    structured_dir = (
        root
        / "03_structured"
        / document_format
    )

    chunks_dir = (
        root
        / "04_chunks"
        / document_format
    )

    embeddings_dir = (
        root
        / "05_embeddings"
        / document_format
    )

    for directory in (
        parsed_dir,
        normalized_dir,
        structured_dir,
        chunks_dir,
        embeddings_dir,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    return {
        "root": root,
        "parsed": (
            parsed_dir
            / f"{document_format}.json"
        ),
        "normalized": (
            normalized_dir
            / f"{document_format}.json"
        ),
        "structured_dir": (
            structured_dir
        ),
        "chunks": (
            chunks_dir
            / "chunks.json"
        ),
        "embeddings_dir": (
            embeddings_dir
        ),
        "embeddings": (
            embeddings_dir
            / "embeddings.npy"
        ),
        "embedding_metadata": (
            embeddings_dir
            / "metadata.json"
        ),
    }


@contextmanager
def _parser_compatible_input(
    source_path: Path,
    *,
    document_id: str,
    document_format: str,
) -> Iterator[Path]:
    """
    실제 문서 형식과 확장자가 다른 경우
    기존 Parser가 확장자 검사를 통과하도록
    평가 outputs 아래에 임시 alias를 만든다.
    """

    expected_suffix = (
        f".{document_format}"
    )

    if (
        source_path.suffix.lower()
        == expected_suffix
    ):
        yield source_path
        return

    alias_dir = (
        PARSER_ALIAS_ROOT
        / document_id
    )

    alias_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    alias_path = (
        alias_dir
        / (
            source_path.stem
            + expected_suffix
        )
    )

    try:
        shutil.copy2(
            source_path,
            alias_path,
        )

        yield alias_path

    finally:
        try:
            alias_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass


def _find_structured_input(
    structured_dir: Path,
) -> Path:
    candidates = [
        (
            structured_dir
            / "step4-1_value_normalized.json"
        ),
        (
            structured_dir
            / "step3-3_structured_tables.json"
        ),
    ]

    for path in candidates:
        if path.is_file():
            return path

    raise FixedDocumentPreparationError(
        "청킹에 사용할 최종 구조화 JSON을 "
        "찾을 수 없습니다: "
        f"{structured_dir}"
    )


# ============================================================
# Stage
# ============================================================

def _parse(
    *,
    source_path: Path,
    document_id: str,
    document_format: str,
    output_path: Path,
) -> None:
    with _parser_compatible_input(
        source_path,
        document_id=document_id,
        document_format=document_format,
    ) as parser_input:

        if document_format == "hwp":
            command = [
                sys.executable,
                str(HWP_PARSER_PATH),
                "--hwp_jar_path",
                str(HWP_JAR_PATH),
                "--file_path",
                str(parser_input),
                "--output_path",
                str(output_path),
            ]

        else:
            command = [
                sys.executable,
                str(HWPX_PARSER_PATH),
                "--hwpx_jar_path",
                str(HWPX_JAR_PATH),
                "--file_path",
                str(parser_input),
                "--output_path",
                str(output_path),
            ]

        _run_command(
            command,
            stage="parse",
        )


def _normalize(
    *,
    input_path: Path,
    output_path: Path,
) -> None:
    _run_command(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        stage="normalize",
    )


def _structure(
    *,
    input_path: Path,
    output_dir: Path,
) -> None:
    _run_command(
        [
            sys.executable,
            str(STRUCTURE_RUNNER_PATH),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        stage="structure",
    )


def _chunk(
    *,
    input_path: Path,
    output_path: Path,
    document_id: str,
) -> None:
    _run_command(
        [
            sys.executable,
            str(CHUNKING_RUNNER_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--announcement-id",
            document_id,
        ],
        stage="chunk",
    )


def _embed(
    *,
    chunks_path: Path,
) -> None:
    """
    기존 run_pipeline.py와 동일하게
    run_embeddings.py --inputs <chunks.json> 을 호출한다.

    run_embeddings.py는
    04_chunks/<format>/chunks.json 위치를 기준으로
    05_embeddings/<format>/ 산출물을 생성한다.
    """

    _run_command(
        [
            sys.executable,
            str(EMBEDDING_RUNNER_PATH),
            "--inputs",
            str(chunks_path),
        ],
        stage="embed",
    )


# ============================================================
# Document 처리
# ============================================================

def prepare_dataset(
    dataset: str,
    *,
    force: bool = False,
) -> None:
    dataset = (
        dataset
        .strip()
        .upper()
    )

    document_id = (
        _dataset_document_id(
            dataset
        )
    )

    documents = (
        _find_source_documents(
            document_id
        )
    )

    print()
    print("=" * 78)
    print(
        "고정 평가 문서 처리"
    )
    print("=" * 78)
    print(
        f"dataset   : {dataset}"
    )
    print(
        f"document  : {document_id}"
    )
    print(
        f"source    : "
        f"{_source_directory(document_id)}"
    )
    print(
        f"output    : "
        f"{_document_output_root(document_id)}"
    )
    print(
        "DB 저장   : 하지 않음"
    )
    print("=" * 78)

    processed_formats: list[str] = []

    for document_format in (
        "hwp",
        "hwpx",
    ):
        files = documents[
            document_format
        ]

        if not files:
            continue

        if len(files) > 1:
            raise FixedDocumentPreparationError(
                f"{document_id}에 실제 "
                f"{document_format.upper()} 문서가 "
                f"{len(files)}개 있습니다.\n"
                "고정 평가 문서 폴더에는 형식별 원본을 "
                "최대 1개만 두세요."
            )

        source_path = files[0]

        paths = _stage_paths(
            document_id=document_id,
            document_format=document_format,
        )

        if (
            not force
            and paths[
                "embeddings"
            ].is_file()
            and paths[
                "embedding_metadata"
            ].is_file()
            and paths[
                "chunks"
            ].is_file()
        ):
            print()
            print(
                f"[SKIP] {document_format.upper()} "
                "최종 산출물이 이미 존재합니다."
            )
            print(
                f"- {paths['chunks']}"
            )
            print(
                f"- {paths['embeddings']}"
            )

            processed_formats.append(
                document_format
            )
            continue

        _parse(
            source_path=source_path,
            document_id=document_id,
            document_format=document_format,
            output_path=paths[
                "parsed"
            ],
        )

        _normalize(
            input_path=paths[
                "parsed"
            ],
            output_path=paths[
                "normalized"
            ],
        )

        _structure(
            input_path=paths[
                "normalized"
            ],
            output_dir=paths[
                "structured_dir"
            ],
        )

        structured_input = (
            _find_structured_input(
                paths[
                    "structured_dir"
                ]
            )
        )

        _chunk(
            input_path=structured_input,
            output_path=paths[
                "chunks"
            ],
            document_id=document_id,
        )

        processed_formats.append(
            document_format
        )

    if not processed_formats:
        raise FixedDocumentPreparationError(
            "처리 가능한 문서 형식이 없습니다."
        )

    #
    # 기존 run_pipeline.py와 동일하게
    # 대표 임베딩은 HWPX 우선, 없으면 HWP를 사용한다.
    #
    representative_format = (
        "hwpx"
        if "hwpx" in processed_formats
        else "hwp"
    )

    representative_paths = (
        _stage_paths(
            document_id=document_id,
            document_format=representative_format,
        )
    )

    if (
        force
        or not representative_paths[
            "embeddings"
        ].is_file()
        or not representative_paths[
            "embedding_metadata"
        ].is_file()
    ):
        _embed(
            chunks_path=representative_paths[
                "chunks"
            ]
        )

    if not representative_paths[
        "embeddings"
    ].is_file():
        raise FixedDocumentPreparationError(
            "Embedding 실행은 끝났지만 "
            "embeddings.npy를 찾을 수 없습니다: "
            f"{representative_paths['embeddings']}"
        )

    print()
    print("=" * 78)
    print(
        "고정 평가 문서 준비 완료"
    )
    print("=" * 78)
    print(
        f"대표 형식 : "
        f"{representative_format}"
    )
    print(
        f"chunks    : "
        f"{representative_paths['chunks']}"
    )
    print(
        f"embedding : "
        f"{representative_paths['embeddings']}"
    )
    print("=" * 78)


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "evaluation/source_documents의 고정 평가 원본을 "
            "기존 Parser/Normalizer/Structure/Chunk/Embedding 코드로 "
            "처리하여 evaluation/outputs에 저장합니다. "
            "DB Persistence는 수행하지 않습니다."
        )
    )

    parser.add_argument(
        "--dataset",
        default="ALL",
        help=(
            "GC, BD 또는 ALL "
            "(기본값: ALL)"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "기존 최종 산출물이 있어도 "
            "처음부터 다시 처리합니다."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    requested = (
        args.dataset
        .strip()
        .upper()
    )

    if requested == "ALL":
        datasets = list(
            FIXED_DATASETS.keys()
        )
    else:
        datasets = [
            requested
        ]

    for dataset in datasets:
        prepare_dataset(
            dataset,
            force=args.force,
        )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\n사용자가 고정 문서 처리를 중단했습니다."
        )
        sys.exit(130)

    except Exception as exc:
        print()
        print(
            "[고정 평가 문서 처리 실패]"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
