from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

# 파일 직접 실행과 모듈 실행을 모두 지원합니다.
# - python embedding/run_embeddings.py
# - python -m embedding.run_embeddings
if __package__ in (None, ""):
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.embedding.config import (
    BATCH_SIZE,
    DEVICE_INDEX,
    EMBEDDINGS_FILENAME,
    MAX_LENGTH,
    METADATA_FILENAME,
    MODEL_NAME,
    MODEL_PATH,
    NORMALIZE_EMBEDDINGS,
    REPORT_FILENAME,
    REQUIRE_CUDA,
    TEXT_FIELD,
    USE_FP16,
)
from pipeline.embedding.embedding_generator import (
    EmbeddingGenerationError,
    generate_embeddings,
)
from pipeline.embedding.input_loader import (
    ChunkLoadError,
    discover_chunk_files,
    load_multiple_chunk_documents,
)
from pipeline.embedding.model_loader import (
    ModelLoadError,
    clear_cuda_cache,
    load_bge_m3_model,
)
from pipeline.embedding.output_writer import (
    EmbeddingWriteError,
    write_embedding_outputs,
)
from pipeline.embedding.validator import (
    EmbeddingValidationError,
    validate_multiple_documents,
)

from backend.app.services.error_log_service import record_error


_LOGGED_ERROR_IDS: set[int] = set()


def log_embedding_error(
    *,
    error: Exception,
    source_path: Path | None = None,
    announcement_id: str | None = None,
) -> None:
    """
    임베딩 단계 예외를 Backend 공통 ErrorLog에 1회 기록합니다.

    현재 파일 기반 임베딩 실행에서는 DB의 document_id /
    processing_run_id가 없을 수 있으므로 가능한 정보만 기록합니다.

    같은 예외가 파일 단위 catch에서 기록된 뒤 상위 main catch로
    다시 전달되더라도 중복 ErrorLog가 생성되지 않도록 방지합니다.

    ErrorLog 저장 자체가 실패해도 원래 임베딩 오류 처리는 유지합니다.
    """
    error_identity = id(error)

    if error_identity in _LOGGED_ERROR_IDS:
        return

    try:
        location = (
            f" input={source_path}"
            if source_path is not None
            else ""
        )
        announcement = (
            f" announcement_id={announcement_id}"
            if announcement_id
            else ""
        )

        record_error(
            error_type="embedding",
            stage="embedding",
            message=f"{error}{announcement}{location}",
            error_code=type(error).__name__,
            stack_trace=traceback.format_exc(),
        )
        _LOGGED_ERROR_IDS.add(error_identity)

    except Exception as log_error:
        print(
            f"[WARNING] ErrorLog 기록 실패: {log_error}",
            file=sys.stderr,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "모든 청크 JSON의 embedding_text를 "
            "BGE-M3 dense vector로 변환합니다."
        )
    )

    parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        default=None,
        help=(
            "직접 지정할 하나 이상의 chunks.json 경로. "
            "생략하면 outputs 폴더에서 전체 파일을 자동 탐색합니다."
        ),
    )

    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help=(
            "자동 탐색할 outputs 폴더. "
            "기본값: 프로젝트 루트의 outputs"
        ),
    )

    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("hwp", "hwpx"),
        default=["hwp", "hwpx"],
        help="처리할 문서 형식. 기본값: hwp hwpx",
    )

    parser.add_argument(
        "--model",
        default=MODEL_NAME,
        help=f"임베딩 모델 ID. 기본값: {MODEL_NAME}",
    )

    parser.add_argument(
        "--model-path",
        default=MODEL_PATH,
        help=f"임베딩 모델 로컬 경로. 기본값: {MODEL_PATH}",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"임베딩 배치 크기. 기본값: {BATCH_SIZE}",
    )

    parser.add_argument(
        "--max-length",
        type=int,
        default=MAX_LENGTH,
        help=f"최대 토큰 길이. 기본값: {MAX_LENGTH}",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "각 chunks.json에서 앞쪽 N개 청크만 처리합니다. "
            "전체 문서 소량 테스트용입니다."
        ),
    )

    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="CUDA가 없어도 CPU 실행을 허용합니다.",
    )

    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="L2 벡터 정규화를 비활성화합니다.",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="한 파일 실패 후에도 나머지 파일을 계속 처리합니다.",
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    if args.batch_size <= 0:
        raise ValueError(
            "--batch-size는 1 이상이어야 합니다."
        )

    if args.max_length <= 0:
        raise ValueError(
            "--max-length는 1 이상이어야 합니다."
        )

    if args.limit is not None and args.limit <= 0:
        raise ValueError(
            "--limit은 1 이상이어야 합니다."
        )


def resolve_input_paths(
    args: argparse.Namespace,
) -> list[Path]:
    """
    직접 지정한 입력 또는 outputs 자동 탐색 결과를 반환한다.
    """

    if args.inputs:
        paths = [
            path.expanduser().resolve()
            for path in args.inputs
        ]
    else:
        paths = discover_chunk_files(
            args.outputs_root,
            formats=tuple(args.formats),
        )

    # 동일 경로가 여러 번 들어온 경우 제거하되 순서는 유지한다.
    unique_paths: list[Path] = []
    seen_paths: set[Path] = set()

    for path in paths:
        if path not in seen_paths:
            unique_paths.append(path)
            seen_paths.add(path)

    if not unique_paths:
        raise ChunkLoadError(
            "임베딩 입력 파일이 없습니다."
        )

    return unique_paths


def print_input_summary(paths: list[Path]) -> None:
    print()
    print("[임베딩 대상 파일]")

    for index, path in enumerate(paths, start=1):
        try:
            relative_path = path.relative_to(Path.cwd())
        except ValueError:
            relative_path = path

        print(f"{index:>2}. {relative_path}")


def main() -> int:
    args = parse_args()

    try:
        validate_arguments(args)

        input_paths = resolve_input_paths(args)

        print("=" * 70)
        print("BGE-M3 전체 문서 임베딩 파이프라인")
        print("=" * 70)
        print(f"입력 파일 수   : {len(input_paths)}")
        print(f"모델           : {args.model}")
        print(f"처리 형식      : {', '.join(args.formats)}")
        print(f"배치 크기      : {args.batch_size}")
        print(f"최대 길이      : {args.max_length}")
        print(f"L2 정규화      : {not args.no_normalize}")

        if args.inputs is None:
            print(f"자동 탐색 루트 : {args.outputs_root.resolve()}")

        if args.limit is not None:
            print(f"테스트 제한    : 파일당 {args.limit}개")

        print_input_summary(input_paths)

        documents = load_multiple_chunk_documents(
            input_paths,
            text_field=TEXT_FIELD,
            limit_per_file=args.limit,
        )

        validation = validate_multiple_documents(documents)
        validation.raise_for_errors()

        if validation.warnings:
            print()
            print(
                f"[입력 검증 경고: "
                f"{len(validation.warnings)}개]"
            )

            for warning in validation.warnings[:20]:
                print(f"- {warning}")

            remaining = len(validation.warnings) - 20

            if remaining > 0:
                print(f"- 나머지 경고 {remaining}개 생략")

        total_chunks = sum(
            document.chunk_count
            for document in documents
        )

        print()
        print("[입력 검증 완료]")
        print(f"입력 파일 수   : {len(documents)}")
        print(f"총 청크 수     : {total_chunks}")

        # 모델은 8개 파일마다 다시 로드하지 않고 한 번만 로드한다.
        loaded_model = load_bge_m3_model(
            model_name=args.model,
            model_path=args.model_path,
            use_fp16=USE_FP16,
            require_cuda=(
                REQUIRE_CUDA and not args.allow_cpu
            ),
            device_index=DEVICE_INDEX,
        )

        succeeded = 0
        failed = 0
        total_embeddings = 0
        result_rows: list[dict[str, object]] = []

        for document_index, document in enumerate(
            documents,
            start=1,
        ):
            print()
            print("#" * 70)
            print(
                f"파일 임베딩 "
                f"[{document_index}/{len(documents)}]"
            )
            print("#" * 70)
            print(f"입력 파일      : {document.source_path}")
            print(f"document_id    : {document.document_id}")
            print(f"announcement_id: {document.announcement_id}")
            print(f"청크 수        : {document.chunk_count}")

            try:
                generated = generate_embeddings(
                    loaded_model,
                    document.items,
                    batch_size=args.batch_size,
                    max_length=args.max_length,
                    normalize_embeddings=(
                        not args.no_normalize
                        and NORMALIZE_EMBEDDINGS
                    ),
                )

                paths = write_embedding_outputs(
                    document,
                    generated,
                    loaded_model.runtime,
                    embeddings_filename=EMBEDDINGS_FILENAME,
                    metadata_filename=METADATA_FILENAME,
                    report_filename=REPORT_FILENAME,
                    batch_size=args.batch_size,
                    max_length=args.max_length,
                )

                succeeded += 1
                total_embeddings += generated.count

                result_rows.append(
                    {
                        "input": str(document.source_path),
                        "output": str(paths["output_dir"]),
                        "chunks": document.chunk_count,
                        "dimension": generated.dimension,
                        "status": "success",
                    }
                )

                print(f"완료 경로      : {paths['output_dir']}")

            except (
                EmbeddingGenerationError,
                EmbeddingValidationError,
                EmbeddingWriteError,
            ) as exc:
                log_embedding_error(
                    error=exc,
                    source_path=document.source_path,
                    announcement_id=document.announcement_id,
                )

                failed += 1

                result_rows.append(
                    {
                        "input": str(document.source_path),
                        "output": None,
                        "chunks": document.chunk_count,
                        "dimension": None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

                print()
                print("[파일 임베딩 실패]")
                print(f"입력: {document.source_path}")
                print(f"원인: {exc}")

                if not args.continue_on_error:
                    raise

            finally:
                clear_cuda_cache()

        print()
        print("=" * 70)
        print("전체 임베딩 결과")
        print("=" * 70)
        print(f"전체 입력 파일 : {len(documents)}")
        print(f"성공           : {succeeded}")
        print(f"실패           : {failed}")
        print(f"생성 벡터 수   : {total_embeddings}")

        print()
        print("[파일별 처리 결과]")

        for index, row in enumerate(result_rows, start=1):
            print(
                f"{index:>2}. "
                f"{row['status']} | "
                f"chunks={row['chunks']} | "
                f"{row['input']}"
            )

        return 0 if failed == 0 else 1

    except (
        ValueError,
        ChunkLoadError,
        EmbeddingValidationError,
        ModelLoadError,
        EmbeddingGenerationError,
        EmbeddingWriteError,
    ) as exc:
        log_embedding_error(
            error=exc,
        )

        print()
        print("[임베딩 파이프라인 실패]")
        print(exc)
        return 1

    except KeyboardInterrupt:
        print()
        print("사용자에 의해 실행이 중단되었습니다.")
        return 130

    except Exception as exc:
        log_embedding_error(
            error=exc,
        )

        print()
        print("[예상하지 못한 오류]")
        print(exc)
        traceback.print_exc()
        return 1

    finally:
        clear_cuda_cache()


if __name__ == "__main__":
    sys.exit(main())