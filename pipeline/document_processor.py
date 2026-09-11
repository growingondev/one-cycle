from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config.paths import OUTPUT_ROOT

from backend.app.services.key_information_service import (
    upsert_key_information,
)
from backend.app.services.pipeline_persistence import (
    activate_processing_run,
    get_registered_document_context,
    mark_processing_run_failed,
    persist_document_outputs,
)

from pipeline.parser.format_detector import (
    detect_actual_document_format,
)


# ============================================================
# 경로
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

PARSER_ALIAS_ROOT = OUTPUT_ROOT / "_parser_aliases"




# ============================================================
# 예외
# ============================================================
class DocumentProcessingError(RuntimeError):
    """문서 처리 실패 정보를 Backend에 전달하기 위한 예외."""

    def __init__(
        self,
        *,
        document_id: int,
        stage: str,
        message: str,
        error_code: str | None = None,
    ) -> None:
        self.document_id = document_id
        self.stage = stage
        self.message = message
        self.error_code = (
            error_code
            or f"{stage.upper()}_FAILED"
        )

        super().__init__(
            f"[{stage}] document_id={document_id}: "
            f"{self.error_code}: {message}"
        )


# ============================================================
# 공통 실행
# ============================================================
def _run_command(
    command: list[str],
    *,
    stage: str,
    document_id: int,
) -> None:
    """하위 Python 단계를 실행하고 실패 시 stage 정보를 포함해 예외 처리."""

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
        env["PYTHONPATH"] = str(PROJECT_ROOT)

    try:
        subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage=stage,
            message=(
                "하위 프로세스 실행에 실패했습니다. "
                f"exit_code={error.returncode}"
            ),
        ) from error
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage=stage,
            message=str(error),
        ) from error


# ============================================================
# 원본 파일 경로
# ============================================================
def _resolve_source_path(
    context: dict[str, Any],
    document_id: int,
) -> Path:
    """Persistence context에서 실제 다운로드 파일 경로를 가져옵니다."""

    raw_path = context.get("storage_path")

    if not raw_path:
        raise DocumentProcessingError(
            document_id=document_id,
            stage="prepare",
            message=(
                "Document의 storage_path가 없습니다. "
                "get_registered_document_context()가 "
                "storage_path를 반환하도록 연결해야 합니다."
            ),
        )

    source_path = Path(str(raw_path)).expanduser()

    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path

    source_path = source_path.resolve()

    if not source_path.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="prepare",
            message=f"원본 문서 파일을 찾을 수 없습니다: {source_path}",
        )

    return source_path


# ============================================================
# 출력 경로
# ============================================================
def _document_output_root(
    announcement_key: str,
    document_id: int,
) -> Path:
    """pipeline_persistence.find_bundle()과 동일한 document 출력 root."""

    root = (
        OUTPUT_ROOT
        / str(announcement_key)
        / f"document_{document_id}"
    )
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    return root


def _stage_paths(
    *,
    announcement_key: str,
    document_id: int,
    document_format: str,
) -> dict[str, Path]:
    root = _document_output_root(
        announcement_key,
        document_id,
    )

    parsed_dir = root / "01_parsed"
    normalized_dir = root / "02_normalized"
    structured_dir = root / "03_structured" / document_format
    chunks_dir = root / "04_chunks" / document_format
    embeddings_dir = root / "05_embeddings" / document_format

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
        "embedding_metadata": (
            embeddings_dir
            / "metadata.json"
        ),
        "embeddings": (
            embeddings_dir
            / "embeddings.npy"
        ),
    }


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
    """실제 형식과 확장자가 다를 때 Parser용 임시 별칭을 생성."""

    expected_suffix = f".{document_format}"

    if source_path.suffix.lower() == expected_suffix:
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
            raise DocumentProcessingError(
                document_id=document_id,
                stage="parser",
                message=(
                    "지원하지 않는 실제 문서 형식입니다: "
                    f"{document_format}"
                ),
            )

        _run_command(
            command,
            stage="parser",
            document_id=document_id,
        )

    if not parsed_output.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="parser",
            message=(
                "Parser 실행 후 결과 JSON이 생성되지 않았습니다: "
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
    _run_command(
        [
            sys.executable,
            str(NORMALIZER_PATH),
            "--input",
            str(parsed_input),
            "--output",
            str(normalized_output),
        ],
        stage="normalizer",
        document_id=document_id,
    )

    if not normalized_output.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="normalizer",
            message=(
                "Normalizer 결과가 생성되지 않았습니다: "
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
    _run_command(
        [
            sys.executable,
            str(STRUCTURE_RUNNER_PATH),
            "--input",
            str(normalized_input),
            "--output-dir",
            str(structured_dir),
        ],
        stage="structure",
        document_id=document_id,
    )

    if not structure_output.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="structure",
            message=(
                "최종 Structure 결과가 없습니다: "
                f"{structure_output}"
            ),
        )

    if not verification_output.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="verification",
            message=(
                "Verification 결과가 없습니다: "
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
        stage="chunking",
        document_id=document_id,
    )

    if not chunks_output.is_file():
        raise DocumentProcessingError(
            document_id=document_id,
            stage="chunking",
            message=(
                "Chunk 결과가 생성되지 않았습니다: "
                f"{chunks_output}"
            ),
        )


# ============================================================
# Embedding
# ============================================================
def _run_embedding(
    *,
    document_id: int,
    chunks_input: Path,
    metadata_output: Path,
    embeddings_output: Path,
) -> None:
    _run_command(
        [
            sys.executable,
            str(EMBEDDING_RUNNER_PATH),
            "--inputs",
            str(chunks_input),
        ],
        stage="embedding",
        document_id=document_id,
    )

    if (
        not metadata_output.is_file()
        or not embeddings_output.is_file()
    ):
        raise DocumentProcessingError(
            document_id=document_id,
            stage="embedding",
            message=(
                "Embedding 산출물이 생성되지 않았습니다. "
                f"metadata={metadata_output}, "
                f"vectors={embeddings_output}"
            ),
        )


# ============================================================
# 핵심정보 payload 검증/저장
# ============================================================
REQUIRED_KEY_INFORMATION_FIELDS = (
    "application_period",
    "eligibility",
    "supply_information",
    "income_asset_criteria",
    "required_documents",
    "winner_announcement",
    "contact_information",
)


def _validate_key_information_payload(
    payload: dict[str, Any],
    *,
    document_id: int,
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise DocumentProcessingError(
            document_id=document_id,
            stage="key_information",
            error_code="KEY_INFORMATION_VALIDATION_FAILED",
            message="핵심정보 추출 결과는 dict여야 합니다.",
        )

    normalized: dict[str, dict[str, Any]] = {}

    for field in REQUIRED_KEY_INFORMATION_FIELDS:
        if field not in payload:
            raise DocumentProcessingError(
                document_id=document_id,
                stage="key_information",
                error_code="KEY_INFORMATION_REQUIRED_FIELD_MISSING",
                message=f"핵심정보 필수 필드가 없습니다: {field}",
            )

        value = payload[field]

        if not isinstance(value, dict):
            raise DocumentProcessingError(
                document_id=document_id,
                stage="key_information",
                error_code="KEY_INFORMATION_VALIDATION_FAILED",
                message=(
                    f"{field} 값은 dict여야 합니다. "
                    f"actual={type(value).__name__}"
                ),
            )

        normalized[field] = value

    return normalized


def _save_key_information(
    *,
    document_id: int,
    announcement_id: int,
    processing_run_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = _validate_key_information_payload(
        payload,
        document_id=document_id,
    )

    try:
        return upsert_key_information(
            announcement_id=announcement_id,
            source_processing_run_id=processing_run_id,
            application_period=normalized[
                "application_period"
            ],
            eligibility=normalized[
                "eligibility"
            ],
            supply_information=normalized[
                "supply_information"
            ],
            income_asset_criteria=normalized[
                "income_asset_criteria"
            ],
            required_documents=normalized[
                "required_documents"
            ],
            winner_announcement=normalized[
                "winner_announcement"
            ],
            contact_information=normalized[
                "contact_information"
            ],
            extraction_status="completed",
            is_verified=False,
        )
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage="key_information",
            error_code="KEY_INFORMATION_PERSISTENCE_FAILED",
            message=(
                "핵심정보 DB 저장 실패: "
                f"{error}"
            ),
        ) from error


# ============================================================
# Backend용 document_id callable
# ============================================================
def _load_required_key_information_extractor(
    *,
    document_id: int,
):
    """MVP 필수 핵심정보 추출기를 로드합니다.

    추출기가 구현되지 않았거나 callable이 아니면 Pipeline을 실패시킵니다.
    """
    try:
        from pipeline.key_information_extractor import (
            extract_key_information,
        )
    except ImportError as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage="key_information",
            error_code="KEY_INFORMATION_EXTRACTOR_NOT_CONFIGURED",
            message=(
                "MVP 필수 핵심정보 추출기가 구현되지 않았습니다. "
                "pipeline/key_information_extractor.py의 "
                "extract_key_information()을 확인하세요."
            ),
        ) from error

    if not callable(extract_key_information):
        raise DocumentProcessingError(
            document_id=document_id,
            stage="key_information",
            error_code="KEY_INFORMATION_EXTRACTOR_NOT_CALLABLE",
            message="extract_key_information이 callable이 아닙니다.",
        )

    return extract_key_information


def _extract_required_key_information(
    *,
    document_id: int,
    structure_path: Path,
    verification_path: Path,
    context: dict[str, Any],
    processing_run_id: int,
) -> dict[str, dict[str, Any]]:
    """핵심정보 7개 필드를 반드시 추출하고 형식을 검증합니다."""

    try:
        extractor = _load_required_key_information_extractor(
            document_id=document_id,
        )

        payload = extractor(
            structure_path=structure_path,
            verification_path=verification_path,
            context={
                **context,
                "processing_run_id": processing_run_id,
            },
        )

    except DocumentProcessingError:
        raise
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage="key_information",
            error_code="KEY_INFORMATION_EXTRACTION_FAILED",
            message=(
                "핵심정보 추출 실패: "
                f"{error}"
            ),
        ) from error

    return _validate_key_information_payload(
        payload,
        document_id=document_id,
    )


def process_document(
    document_id: int,
) -> dict[str, Any]:
    """DB Document 한 건을 전체 Pipeline으로 처리합니다.

    MVP 필수 처리 순서:
        Parser
        -> Normalizer
        -> Structure / Verification
        -> Chunk
        -> Embedding
        -> Persistence
        -> 핵심정보 7개 필드 추출
        -> upsert_key_information()
        -> activate_processing_run()

    핵심정보 추출기 미구현/실패 또는 DB 저장 실패 시
    해당 ProcessingRun은 활성화하지 않습니다.
    """

    if (
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id <= 0
    ):
        raise ValueError(
            "document_id는 1 이상의 정수여야 합니다."
        )

    # --------------------------------------------------------
    # 1. DB Document context
    # --------------------------------------------------------
    try:
        context = get_registered_document_context(
            document_id
        )
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_id,
            stage="prepare",
            message=str(error),
        ) from error

    announcement_key = str(
        context["announcement_key"]
    )
    announcement_db_id = int(
        context["announcement_db_id"]
    )
    document_db_id = int(
        context["document_db_id"]
    )
    original_filename = str(
        context["filename"]
    )

    source_path = _resolve_source_path(
        context,
        document_id,
    )

    # --------------------------------------------------------
    # 2. 실제 내부 형식 확인
    # --------------------------------------------------------
    try:
        document_format = (
            detect_actual_document_format(
                source_path
            )
        )
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_db_id,
            stage="format_detection",
            message=str(error),
        ) from error

    if document_format not in {
        "hwp",
        "hwpx",
    }:
        raise DocumentProcessingError(
            document_id=document_db_id,
            stage="format_detection",
            message=(
                "실제 내부 형식을 HWP/HWPX로 판별하지 못했습니다: "
                f"{source_path}"
            ),
        )

    db_format = str(
        context.get("format") or ""
    ).lower()

    if (
        db_format
        and db_format != document_format
    ):
        raise DocumentProcessingError(
            document_id=document_db_id,
            stage="format_detection",
            message=(
                "DB document_format과 실제 파일 형식이 다릅니다. "
                f"db={db_format}, actual={document_format}. "
                "Crawler 저장 형식을 확인하세요."
            ),
        )

    paths = _stage_paths(
        announcement_key=announcement_key,
        document_id=document_db_id,
        document_format=document_format,
    )

    # --------------------------------------------------------
    # 3. Parser
    # --------------------------------------------------------
    _run_parser(
        document_id=document_db_id,
        source_path=source_path,
        original_filename=original_filename,
        document_format=document_format,
        parsed_output=paths["parsed"],
    )

    # --------------------------------------------------------
    # 4. Normalizer
    # --------------------------------------------------------
    _run_normalizer(
        document_id=document_db_id,
        parsed_input=paths["parsed"],
        normalized_output=paths["normalized"],
    )

    # --------------------------------------------------------
    # 5. Structure + Verification
    # --------------------------------------------------------
    _run_structure(
        document_id=document_db_id,
        normalized_input=paths["normalized"],
        structured_dir=paths[
            "structured_dir"
        ],
        structure_output=paths[
            "structure"
        ],
        verification_output=paths[
            "verification"
        ],
    )

    # --------------------------------------------------------
    # 6. Chunk
    # --------------------------------------------------------
    _run_chunking(
        document_id=document_db_id,
        announcement_id=announcement_db_id,
        structure_input=paths["structure"],
        chunks_output=paths["chunks"],
    )

    # --------------------------------------------------------
    # 7. Embedding
    # --------------------------------------------------------
    _run_embedding(
        document_id=document_db_id,
        chunks_input=paths["chunks"],
        metadata_output=paths[
            "embedding_metadata"
        ],
        embeddings_output=paths[
            "embeddings"
        ],
    )

    # --------------------------------------------------------
    # 8. Pipeline Persistence
    # 여기서 ProcessingRun이 생성되며 기본 is_active=False 입니다.
    # --------------------------------------------------------
    try:
        persistence = persist_document_outputs(
            document_db_id
        )
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_db_id,
            stage="persistence",
            message=str(error),
        ) from error

    processing_run_id = int(
        persistence["processing_run_id"]
    )

    # --------------------------------------------------------
    # 9~10. 핵심정보 추출 + DB 저장 - MVP 필수
    #
    # 이 시점에는 ProcessingRun이 이미 생성되어 있고
    # is_active=False 상태입니다.
    #
    # 추출/검증/upsert 중 하나라도 실패하면:
    # - 새 ProcessingRun만 failed 처리
    # - verification_status=pass 유지
    # - 기존 active ProcessingRun 유지
    # - 기존 정상 KeyInformation 유지
    # - activate_processing_run() 호출 금지
    # --------------------------------------------------------
    try:
        key_information = (
            _extract_required_key_information(
                document_id=document_db_id,
                structure_path=paths["structure"],
                verification_path=paths[
                    "verification"
                ],
                context={
                    **context,
                    "document_format": document_format,
                    "output_root": str(paths["root"]),
                },
                processing_run_id=processing_run_id,
            )
        )

        key_information_result = (
            _save_key_information(
                document_id=document_db_id,
                announcement_id=announcement_db_id,
                processing_run_id=processing_run_id,
                payload=key_information,
            )
        )

    except DocumentProcessingError as error:
        try:
            mark_processing_run_failed(
                processing_run_id,
                stage="key_information",
                error_code=error.error_code,
                error_message=error.message,
                exit_code=1,
            )
        except Exception as status_error:
            raise DocumentProcessingError(
                document_id=document_db_id,
                stage="key_information",
                error_code="PROCESSING_RUN_FAILURE_RECORD_FAILED",
                message=(
                    f"원래 오류: {error.message} / "
                    "ProcessingRun 실패 상태 기록도 실패했습니다: "
                    f"{status_error}"
                ),
            ) from status_error

        raise

    except Exception as error:
        wrapped = DocumentProcessingError(
            document_id=document_db_id,
            stage="key_information",
            error_code="KEY_INFORMATION_UNKNOWN_FAILED",
            message=str(error),
        )

        try:
            mark_processing_run_failed(
                processing_run_id,
                stage="key_information",
                error_code=wrapped.error_code,
                error_message=wrapped.message,
                exit_code=1,
            )
        except Exception as status_error:
            raise DocumentProcessingError(
                document_id=document_db_id,
                stage="key_information",
                error_code="PROCESSING_RUN_FAILURE_RECORD_FAILED",
                message=(
                    f"원래 오류: {wrapped.message} / "
                    "ProcessingRun 실패 상태 기록도 실패했습니다: "
                    f"{status_error}"
                ),
            ) from status_error

        raise wrapped from error

    # --------------------------------------------------------
    # 11. ProcessingRun 활성화
    #
    # 핵심정보 추출 + upsert까지 성공한 경우에만 호출합니다.
    # --------------------------------------------------------
    try:
        activation = activate_processing_run(
            processing_run_id
        )
    except Exception as error:
        raise DocumentProcessingError(
            document_id=document_db_id,
            stage="activation",
            message=str(error),
        ) from error

    return {
        "success": True,
        "stage": "completed",
        "document_id": document_db_id,
        "announcement_id": (
            announcement_db_id
        ),
        "announcement_key": (
            announcement_key
        ),
        "document_format": (
            document_format
        ),
        "processing_run_id": (
            processing_run_id
        ),
        "key_information_id": (
            key_information_result["id"]
        ),
        "key_information_status": (
            key_information_result[
                "extraction_status"
            ]
        ),
        "output_root": str(
            paths["root"]
        ),
        "is_active": True,
        "activation": activation,
    }


# ============================================================
# Backend DOCUMENT_REPROCESSOR 연결용 공식 callable
# ============================================================
def reprocess_document(
    *,
    document_id: int,
) -> dict[str, Any]:
    """pipeline_gateway가 호출할 공식 문서 재처리 callable."""

    try:
        return process_document(
            document_id=document_id,
        )

    except DocumentProcessingError as error:
        return {
            "success": False,
            "document_id": error.document_id,
            "stage": error.stage,
            "error_code": error.error_code,
            "message": error.message,
        }

    except Exception as error:
        return {
            "success": False,
            "document_id": document_id,
            "stage": "unknown",
            "message": str(error),
        }
