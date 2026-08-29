from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from config.paths import OUTPUT_ROOT

from document_worker.api.schemas import (
    DocumentProcessRequest,
    DocumentProcessResponse,
)

from pipeline.parser.format_detector import (
    detect_actual_document_format,
)

from pipeline.embedding.input_loader import (
    ChunkLoadError,
    load_chunk_document,
)

from pipeline.key_information_extractor import (
    REQUIRED_FIELDS,
    extract_key_information,
)

from services.embedding.client import (
    EmbeddingClient,
    EmbeddingClientError,
)

# ============================================================
# 기본 경로
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PARSER_DIR = PROJECT_ROOT / "pipeline" / "parser"
NORMALIZER_DIR = PROJECT_ROOT / "pipeline" / "normalizer"

HWP_PARSER_PATH = PARSER_DIR / "hwp_parser.py"
HWPX_PARSER_PATH = PARSER_DIR / "hwpx_parser.py"

NORMALIZER_PATH = (
    NORMALIZER_DIR / "document_normalizer.py"
)

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
    OUTPUT_ROOT / "_parser_aliases"
)

STRUCTURE_DIR = PROJECT_ROOT / "pipeline" / "structure"

STRUCTURE_RUNNER_PATH = (
    STRUCTURE_DIR / "run_structure.py"
)


CHUNKING_DIR = PROJECT_ROOT / "pipeline" / "chunking"

CHUNKING_RUNNER_PATH = (
    CHUNKING_DIR / "run_chunking.py"
)


# ============================================================
# Worker 예외
# ============================================================

class DocumentWorkerServiceError(RuntimeError):
    """Document Worker 처리 중 발생하는 계약 가능한 오류."""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message

        super().__init__(message)


# ============================================================
# 원본 파일 확인
# ============================================================

def _resolve_source_path(
    storage_path: str,
) -> Path:
    normalized_path = str(
        storage_path or ""
    ).strip()

    if not normalized_path:
        raise DocumentWorkerServiceError(
            status_code=422,
            error_code="DOCUMENT_REQUEST_INVALID",
            message="source.storage_path가 비어 있습니다.",
        )

    source_path = Path(
        normalized_path
    ).expanduser()

    if not source_path.is_file():
        raise DocumentWorkerServiceError(
            status_code=404,
            error_code="DOCUMENT_SOURCE_NOT_FOUND",
            message=(
                "원본 문서 파일을 찾을 수 없습니다: "
                f"{source_path}"
            ),
        )

    return source_path.resolve()


# ============================================================
# 실제 문서 형식 확인
# ============================================================

def _validate_document_format(
    *,
    source_path: Path,
    expected_format: str,
) -> str:
    actual_format = (
        detect_actual_document_format(
            source_path
        )
    )

    if actual_format not in {
        "hwp",
        "hwpx",
    }:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_FORMAT_VALIDATION_FAILED"
            ),
            message=(
                "실제 문서 형식을 HWP/HWPX로 "
                "판별하지 못했습니다: "
                f"{source_path}"
            ),
        )

    normalized_expected_format = (
        str(expected_format or "")
        .strip()
        .lower()
    )

    if (
        normalized_expected_format
        != actual_format
    ):
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_FORMAT_VALIDATION_FAILED"
            ),
            message=(
                "Backend가 전달한 문서 형식과 "
                "실제 파일 내부 형식이 다릅니다. "
                f"expected={normalized_expected_format}, "
                f"actual={actual_format}"
            ),
        )

    return actual_format


# ============================================================
# 출력 경로
# ============================================================

def _document_output_root(
    *,
    announcement_key: str,
    document_id: int,
) -> Path:
    root = (
        OUTPUT_ROOT
        / announcement_key
        / f"document_{document_id}"
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return root


def _prepare_stage_paths(
    *,
    announcement_key: str,
    document_id: int,
    document_format: str,
) -> dict[str, Path]:
    root = _document_output_root(
        announcement_key=announcement_key,
        document_id=document_id,
    )

    parsed_dir = (
        root / "01_parsed"
    )

    normalized_dir = (
        root / "02_normalized"
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

        "structured_dir": structured_dir,

        "structure": (
            structured_dir
            / "step4-1_value_normalized.json"
        ),

        "verification": (
            structured_dir
            / "step4-3_verification.json"
        ),

        "chunks": (
            chunks_dir
            / "chunks.json"
        ),

        "embeddings_dir": embeddings_dir,

        "embeddings": (
            embeddings_dir
            / "embeddings.npy"
        ),

        "embedding_metadata": (
            embeddings_dir
            / "metadata.json"
        ),

        "embedding_report": (
            embeddings_dir
            / "embedding_report.json"
        ),
    }

# ============================================================
# subprocess 공통 실행
# ============================================================

def _run_command(
    command: list[str],
    *,
    document_id: int,
    error_code: str,
    stage_name: str,
) -> None:
    env = os.environ.copy()

    current_pythonpath = env.get(
        "PYTHONPATH",
        "",
    ).strip()

    if current_pythonpath:
        env["PYTHONPATH"] = (
            str(PROJECT_ROOT)
            + os.pathsep
            + current_pythonpath
        )
    else:
        env["PYTHONPATH"] = str(
            PROJECT_ROOT
        )

    try:
        subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            check=True,
        )

    except subprocess.CalledProcessError as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=error_code,
            message=(
                f"{stage_name} 하위 프로세스 실행에 "
                "실패했습니다. "
                f"exit_code={error.returncode}, "
                f"document_id={document_id}"
            ),
        ) from error

    except Exception as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=error_code,
            message=str(error),
        ) from error


# ============================================================
# Parser 확장자 별칭
# ============================================================

@contextmanager
def _parser_compatible_input(
    source_path: Path,
    *,
    document_id: int,
    document_format: str,
) -> Iterator[Path]:
    """
    실제 내부 형식과 확장자가 다른 경우
    Parser용 임시 별칭 파일을 생성한다.
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
        / f"document_{document_id}"
    )

    alias_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    alias_path = (
        alias_dir
        / f"{source_path.stem}{expected_suffix}"
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
                missing_ok=True,
            )
        except OSError:
            pass


# ============================================================
# Parser
# ============================================================

def _run_parser(
    *,
    document_id: int,
    source_path: Path,
    original_filename: str,
    document_format: str,
    parsed_output: Path,
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
                "--original-filename",
                original_filename,
                "--output_path",
                str(parsed_output),
            ]

        elif document_format == "hwpx":
            command = [
                sys.executable,
                str(HWPX_PARSER_PATH),
                "--hwpx_jar_path",
                str(HWPX_JAR_PATH),
                "--file_path",
                str(parser_input),
                "--original-filename",
                original_filename,
                "--output_path",
                str(parsed_output),
            ]

        else:
            raise DocumentWorkerServiceError(
                status_code=500,
                error_code="DOCUMENT_PARSE_FAILED",
                message=(
                    "지원하지 않는 문서 형식입니다: "
                    f"{document_format}"
                ),
            )

        _run_command(
            command,
            document_id=document_id,
            error_code="DOCUMENT_PARSE_FAILED",
            stage_name="Parser",
        )

    if not parsed_output.is_file():
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_PARSE_FAILED",
            message=(
                "Parser 실행 후 결과 JSON이 "
                "생성되지 않았습니다: "
                f"{parsed_output}"
            ),
        )


# ============================================================
# Normalizer
# ============================================================

def _run_normalizer(
    *,
    document_id: int,
    parsed_input: Path,
    normalized_output: Path,
) -> None:
    """
    Parser JSON을 받아 Normalizer를 실행한다.
    """

    _run_command(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input",
            str(parsed_input),
            "--output",
            str(normalized_output),
        ],
        document_id=document_id,
        error_code="DOCUMENT_NORMALIZE_FAILED",
        stage_name="Normalizer",
    )

    if not normalized_output.is_file():
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_NORMALIZE_FAILED",
            message=(
                "Normalizer 실행 후 결과 JSON이 "
                "생성되지 않았습니다: "
                f"{normalized_output}"
            ),
        )
        

# ============================================================
# Structure / Verification
# ============================================================

def _run_structure(
    *,
    document_id: int,
    normalized_input: Path,
    structured_dir: Path,
    structure_output: Path,
    verification_output: Path,
) -> None:
    """
    Normalizer 결과를 받아
    Structure + Verification Pipeline을 실행한다.
    """

    _run_command(
        [
            sys.executable,
            str(STRUCTURE_RUNNER_PATH),
            "--input",
            str(normalized_input),
            "--output-dir",
            str(structured_dir),
        ],
        document_id=document_id,
        error_code="DOCUMENT_STRUCTURE_FAILED",
        stage_name="Structure",
    )

    if not structure_output.is_file():
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_STRUCTURE_FAILED",
            message=(
                "Structure 실행 후 최종 결과가 "
                "생성되지 않았습니다: "
                f"{structure_output}"
            ),
        )

    if not verification_output.is_file():
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_VERIFICATION_FAILED",
            message=(
                "Verification 결과가 "
                "생성되지 않았습니다: "
                f"{verification_output}"
            ),
        )


# ============================================================
# Chunking
# ============================================================

def _run_chunking(
    *,
    document_id: int,
    announcement_id: int,
    structure_input: Path,
    chunks_output: Path,
) -> None:
    """
    Structure 최종 결과를 받아 Chunking을 실행한다.
    """

    _run_command(
        [
            sys.executable,
            str(CHUNKING_RUNNER_PATH),
            "--input",
            str(structure_input),
            "--output",
            str(chunks_output),
            "--announcement-id",
            str(announcement_id),
        ],
        document_id=document_id,
        error_code="DOCUMENT_CHUNKING_FAILED",
        stage_name="Chunking",
    )

    if not chunks_output.is_file():
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_CHUNKING_FAILED",
            message=(
                "Chunking 실행 후 chunks.json이 "
                "생성되지 않았습니다: "
                f"{chunks_output}"
            ),
        )


# ============================================================
# Embedding Service
# ============================================================

def _run_embedding_service(
    *,
    document_id: int,
    chunks_input: Path,
):
    """
    Chunking 결과인 chunks.json을 읽어
    Embedding Service에 HTTP 요청을 보내고
    Chunk 순서에 맞는 Vector 배열을 반환한다.

    Document Worker에서는 BGE-M3 모델을 직접 실행하지 않는다.
    """

    # --------------------------------------------------------
    # 1. chunks.json 로드
    # --------------------------------------------------------

    try:
        document = load_chunk_document(
            chunks_input
        )

    except ChunkLoadError as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_EMBEDDING_INPUT_FAILED"
            ),
            message=str(error),
        ) from error

    if not document.items:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_EMBEDDING_INPUT_FAILED"
            ),
            message=(
                "Embedding할 Chunk가 없습니다. "
                f"document_id={document_id}"
            ),
        )

    # --------------------------------------------------------
    # 2. Embedding API Request 구성
    # --------------------------------------------------------

    request_items = [
        {
            "id": item.chunk_id,
            "text": item.embedding_text,
        }
        for item in document.items
    ]

    # --------------------------------------------------------
    # 3. Embedding Service HTTP 호출
    # --------------------------------------------------------

    client = EmbeddingClient()

    try:
        embedding_map = (
            client.embed_items(
                request_items
            )
        )

    except EmbeddingClientError as error:
        raise DocumentWorkerServiceError(
            status_code=502,
            error_code=(
                "DOCUMENT_EMBEDDING_SERVICE_FAILED"
            ),
            message=(
                "Embedding Service 호출에 실패했습니다. "
                f"document_id={document_id}, "
                f"error={error}"
            ),
        ) from error

    # --------------------------------------------------------
    # 4. 응답을 Chunk ID 기준으로 다시 정렬
    # --------------------------------------------------------

    try:
        vectors = np.stack(
            [
                embedding_map[
                    item.chunk_id
                ]
                for item in document.items
            ],
            axis=0,
        ).astype(
            np.float32,
            copy=False,
        )

    except (
        KeyError,
        ValueError,
        TypeError,
    ) as error:
        raise DocumentWorkerServiceError(
            status_code=502,
            error_code=(
                "DOCUMENT_EMBEDDING_RESPONSE_INVALID"
            ),
            message=(
                "Embedding 응답을 Chunk ID 기준으로 "
                "정렬하지 못했습니다. "
                f"document_id={document_id}"
            ),
        ) from error

    # --------------------------------------------------------
    # 5. Vector Shape 검증
    # --------------------------------------------------------

    expected_shape = (
        document.chunk_count,
        1024,
    )

    if vectors.shape != expected_shape:
        raise DocumentWorkerServiceError(
            status_code=502,
            error_code=(
                "DOCUMENT_EMBEDDING_RESPONSE_INVALID"
            ),
            message=(
                "Embedding 결과 shape이 "
                "올바르지 않습니다. "
                f"expected={expected_shape}, "
                f"actual={vectors.shape}"
            ),
        )

    # --------------------------------------------------------
    # 6. NaN / Infinity 검증
    # --------------------------------------------------------

    if not np.isfinite(
        vectors
    ).all():
        raise DocumentWorkerServiceError(
            status_code=502,
            error_code=(
                "DOCUMENT_EMBEDDING_RESPONSE_INVALID"
            ),
            message=(
                "Embedding 결과에 "
                "NaN 또는 Infinity가 있습니다."
            ),
        )

    return (
        document,
        vectors,
    )


# ============================================================
# Embedding Artifact 저장
# ============================================================

def _write_embedding_artifacts(
    *,
    document,
    vectors: np.ndarray,
    embeddings_path: Path,
    metadata_path: Path,
    report_path: Path,
) -> None:
    """
    Embedding Service에서 반환받은 Vector를
    Document Worker Artifact로 저장한다.

    생성 파일:
    - embeddings.npy
    - metadata.json
    - embedding_report.json
    """

    output_dir = (
        embeddings_path.parent
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 1. embeddings.npy
    # --------------------------------------------------------

    try:
        np.save(
            embeddings_path,
            vectors,
            allow_pickle=False,
        )

    except Exception as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_EMBEDDING_ARTIFACT_FAILED"
            ),
            message=(
                "embeddings.npy 저장에 "
                "실패했습니다: "
                f"{embeddings_path}"
            ),
        ) from error

    # --------------------------------------------------------
    # 2. Metadata Item 구성
    # --------------------------------------------------------

    metadata_items: list[
        dict
    ] = []

    for vector_index, item in enumerate(
        document.items
    ):
        metadata = dict(
            item.metadata
        )

        metadata[
            "vector_index"
        ] = vector_index

        metadata[
            "chunk_id"
        ] = item.chunk_id

        metadata_items.append(
            metadata
        )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    # --------------------------------------------------------
    # 3. metadata.json
    # --------------------------------------------------------

    metadata_payload = {
        "schema_version": (
            "embedding-metadata-v1"
        ),
        "created_at": created_at,
        "model": {
            "name": "BAAI/bge-m3",
            "dimension": 1024,
            "normalized": True,
            "dtype": str(
                vectors.dtype
            ),
            "source": (
                "embedding-service"
            ),
        },
        "source": {
            "chunk_file": str(
                document.source_path
            ),
            "document_id": (
                document.document_id
            ),
            "announcement_id": (
                document.announcement_id
            ),
            "chunk_count": (
                document.chunk_count
            ),
        },
        "items": metadata_items,
    }

    try:
        with metadata_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                metadata_payload,
                file,
                ensure_ascii=False,
                indent=2,
            )

            file.write("\n")

    except OSError as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_EMBEDDING_ARTIFACT_FAILED"
            ),
            message=(
                "metadata.json 저장에 "
                "실패했습니다: "
                f"{metadata_path}"
            ),
        ) from error

    # --------------------------------------------------------
    # 4. Embedding 통계
    # --------------------------------------------------------

    norms = np.linalg.norm(
        vectors,
        axis=1,
    )

    # --------------------------------------------------------
    # 5. embedding_report.json
    # --------------------------------------------------------

    report_payload = {
        "schema_version": (
            "embedding-report-v1"
        ),
        "status": "success",
        "created_at": created_at,

        "source_chunk_file": str(
            document.source_path
        ),

        "document_id": (
            document.document_id
        ),

        "announcement_id": (
            document.announcement_id
        ),

        "model_name": (
            "BAAI/bge-m3"
        ),

        "embedding_source": (
            "embedding-service"
        ),

        "chunk_count": (
            document.chunk_count
        ),

        "embedding_count": int(
            vectors.shape[0]
        ),

        "embedding_dimension": int(
            vectors.shape[1]
        ),

        "embedding_dtype": str(
            vectors.dtype
        ),

        "normalized": True,

        "nan_count": int(
            np.isnan(
                vectors
            ).sum()
        ),

        "infinity_count": int(
            np.isinf(
                vectors
            ).sum()
        ),

        "zero_vector_count": int(
            np.sum(
                norms == 0
            )
        ),

        "norm_statistics": {
            "minimum": float(
                norms.min()
            ),
            "maximum": float(
                norms.max()
            ),
            "average": float(
                norms.mean()
            ),
        },
    }

    try:
        with report_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report_payload,
                file,
                ensure_ascii=False,
                indent=2,
            )

            file.write("\n")

    except OSError as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code=(
                "DOCUMENT_EMBEDDING_ARTIFACT_FAILED"
            ),
            message=(
                "embedding_report.json 저장에 "
                "실패했습니다: "
                f"{report_path}"
            ),
        ) from error

    # --------------------------------------------------------
    # 6. 최종 파일 존재 확인
    # --------------------------------------------------------

    expected_files = (
        embeddings_path,
        metadata_path,
        report_path,
    )

    for path in expected_files:
        if not path.is_file():
            raise DocumentWorkerServiceError(
                status_code=500,
                error_code=(
                    "DOCUMENT_EMBEDDING_ARTIFACT_FAILED"
                ),
                message=(
                    "Embedding Artifact가 "
                    "생성되지 않았습니다: "
                    f"{path}"
                ),
            )

# ============================================================
# Key Information Extraction
# ============================================================

def _run_key_information_extraction(
    *,
    document_id: int,
    announcement_id: int,
    announcement_key: str,
    structure_path: Path,
    verification_path: Path,
) -> dict[str, Any]:
    """
    Structure / Verification 결과에서
    Backend에 반환할 핵심정보 7개 필드를 추출한다.

    Document Worker는 추출 결과를 응답으로 반환하며,
    DB 저장은 Backend의 책임으로 유지한다.
    """

    context = {
        "document_id": document_id,
        "announcement_id": announcement_id,
        "announcement_key": announcement_key,
    }

    try:
        result = extract_key_information(
            structure_path=structure_path,
            verification_path=verification_path,
            context=context,
        )

    except Exception as error:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_KEY_INFORMATION_FAILED",
            message=(
                "Key Information Extraction에 실패했습니다. "
                f"document_id={document_id}, "
                f"error={error}"
            ),
        ) from error

    if not isinstance(result, dict):
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_KEY_INFORMATION_FAILED",
            message=(
                "Key Information Extraction 결과가 "
                "객체가 아닙니다."
            ),
        )

    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if (
            field not in result
            or not isinstance(
                result[field],
                dict,
            )
        )
    ]

    if missing_fields:
        raise DocumentWorkerServiceError(
            status_code=500,
            error_code="DOCUMENT_KEY_INFORMATION_FAILED",
            message=(
                "Key Information 필수 필드가 "
                "누락되었거나 형식이 잘못되었습니다: "
                f"{missing_fields}"
            ),
        )

    return result


# ============================================================
# Document Worker 진입점
# ============================================================

def process_document(
    *,
    document_id: int,
    request: DocumentProcessRequest,
) -> DocumentProcessResponse:
    """
    현재 구현 단계:

    원본 파일 확인
    -> 실제 HWP/HWPX 형식 확인
    -> Parser
    -> Normalizer
    -> Structure / Verification
    -> Chunking
    -> Embedding Service
    -> Embedding Artifact 저장
    -> Key Information Extraction
    -> 최종 DocumentProcessResponse 반환
    """

    # --------------------------------------------------------
    # 1. 원본 파일 확인
    # --------------------------------------------------------

    source_path = _resolve_source_path(
        request.source.storage_path
    )

    # --------------------------------------------------------
    # 2. 실제 HWP/HWPX 형식 확인
    # --------------------------------------------------------

    document_format = (
        _validate_document_format(
            source_path=source_path,
            expected_format=(
                request.source.format
            ),
        )
    )

    # --------------------------------------------------------
    # 3. Artifact 경로 준비
    # --------------------------------------------------------

    paths = _prepare_stage_paths(
        announcement_key=(
            request.announcement_key
        ),
        document_id=document_id,
        document_format=document_format,
    )

    # --------------------------------------------------------
    # 4. Parser
    # --------------------------------------------------------

    _run_parser(
        document_id=document_id,
        source_path=source_path,
        original_filename=(
            request.source.filename
        ),
        document_format=document_format,
        parsed_output=paths["parsed"],
    )

    # --------------------------------------------------------
    # 5. Normalizer
    # --------------------------------------------------------

    _run_normalizer(
        document_id=document_id,
        parsed_input=paths["parsed"],
        normalized_output=(
            paths["normalized"]
        ),
    )
    
    # --------------------------------------------------------
    # 6. Structure / Verification
    # --------------------------------------------------------

    _run_structure(
        document_id=document_id,
        normalized_input=(
            paths["normalized"]
        ),
        structured_dir=(
            paths["structured_dir"]
        ),
        structure_output=(
            paths["structure"]
        ),
        verification_output=(
            paths["verification"]
        ),
    )
    
    
    # --------------------------------------------------------
    # 7. Chunking
    # --------------------------------------------------------

    _run_chunking(
        document_id=document_id,
        announcement_id=(
            request.announcement_id
        ),
        structure_input=(
            paths["structure"]
        ),
        chunks_output=(
            paths["chunks"]
        ),
    )


    # --------------------------------------------------------
    # 8. Embedding Service HTTP 연동
    # --------------------------------------------------------

    (
        embedding_document,
        embedding_vectors,
    ) = _run_embedding_service(
        document_id=document_id,
        chunks_input=(
            paths["chunks"]
        ),
    )

    # --------------------------------------------------------
    # 9. Embedding Artifact 저장
    # --------------------------------------------------------

    _write_embedding_artifacts(
        document=(
            embedding_document
        ),
        vectors=(
            embedding_vectors
        ),
        embeddings_path=(
            paths["embeddings"]
        ),
        metadata_path=(
            paths[
                "embedding_metadata"
            ]
        ),
        report_path=(
            paths[
                "embedding_report"
            ]
        ),
    )

    # --------------------------------------------------------
    # 10. Key Information Extraction
    # --------------------------------------------------------

    key_information = (
        _run_key_information_extraction(
            document_id=document_id,
            announcement_id=(
                request.announcement_id
            ),
            announcement_key=(
                request.announcement_key
            ),
            structure_path=(
                paths["structure"]
            ),
            verification_path=(
                paths["verification"]
            ),
        )
    )

    # --------------------------------------------------------
    # 11. 최종 Document Worker Response
    # --------------------------------------------------------

    return DocumentProcessResponse(
        document_id=document_id,
        announcement_id=(
            request.announcement_id
        ),
        announcement_key=(
            request.announcement_key
        ),
        status="completed",
        document_format=document_format,
        output_path=str(
            paths["root"]
        ),
        summary={
            "chunk_count": (
                embedding_document.chunk_count
            ),
            "embedding_count": int(
                embedding_vectors.shape[0]
            ),
        },
        key_information=(
            key_information
        ),
    )
