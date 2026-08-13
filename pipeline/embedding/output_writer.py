from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .embedding_generator import GeneratedEmbeddings
from .models import LoadedChunkDocument
from .model_loader import ModelRuntimeInfo


class EmbeddingWriteError(RuntimeError):
    """임베딩 결과 저장에 실패했을 때 발생하는 오류."""


def resolve_output_directory(
    chunk_file: str | Path,
) -> Path:
    """
    chunks.json 경로에서 임베딩 결과 폴더를 계산한다.

    지원 구조:
        outputs/<announcement>/04_chunks/<format>/chunks.json

    반환:
        outputs/<announcement>/05_embeddings/<format>
    """

    chunk_path = Path(chunk_file).expanduser().resolve()

    parts = list(chunk_path.parts)

    try:
        chunk_stage_index = parts.index("04_chunks")
    except ValueError as exc:
        raise EmbeddingWriteError(
            "입력 경로에 '04_chunks' 폴더가 없습니다.\n"
            f"입력: {chunk_path}\n"
            "예상 경로: "
            "outputs/<announcement>/04_chunks/<format>/chunks.json"
        ) from exc

    parts[chunk_stage_index] = "05_embeddings"

    # 마지막 요소는 chunks.json이므로 제거한다.
    output_dir = Path(*parts[:-1])

    return output_dir


def _write_json_atomic(
    path: Path,
    data: dict[str, Any],
) -> None:
    """
    JSON을 임시 파일에 먼저 저장한 뒤 원자적으로 교체한다.

    저장 도중 프로세스가 종료돼 기존 파일이 깨지는 것을 줄인다.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            prefix=f".{path.stem}_",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            json.dump(
                data,
                temp_file,
                ensure_ascii=False,
                indent=2,
            )
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = Path(temp_file.name)

        temp_path.replace(path)

    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

        raise EmbeddingWriteError(
            f"JSON 저장에 실패했습니다: {path}"
        ) from exc


def _write_numpy_atomic(
    path: Path,
    vectors: np.ndarray,
) -> None:
    """
    NumPy 벡터 배열을 안전하게 저장한다.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".npy",
            prefix=f".{path.stem}_",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        np.save(
            temp_path,
            vectors,
            allow_pickle=False,
        )

        temp_path.replace(path)

    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

        raise EmbeddingWriteError(
            f"NumPy 임베딩 저장에 실패했습니다: {path}"
        ) from exc


def build_metadata_payload(
    document: LoadedChunkDocument,
    generated: GeneratedEmbeddings,
    runtime: ModelRuntimeInfo,
) -> dict[str, Any]:
    """
    metadata.json에 저장할 객체를 생성한다.
    """

    items: list[dict[str, Any]] = []

    for expected_index, item in enumerate(document.items):
        metadata = dict(item.metadata)

        # input_loader가 넣은 값과 실제 순서를 다시 일치시킨다.
        metadata["vector_index"] = expected_index
        metadata["chunk_id"] = item.chunk_id

        items.append(metadata)

    return {
        "schema_version": "embedding-metadata-v1",
        "created_at": datetime.now(
            timezone.utc,
        ).isoformat(),
        "model": {
            "name": runtime.model_name,
            "dimension": generated.dimension,
            "normalized": generated.normalized,
            "dtype": str(generated.vectors.dtype),
            "device": runtime.device,
            "device_name": runtime.device_name,
            "use_fp16": runtime.use_fp16,
        },
        "source": {
            "chunk_file": str(document.source_path),
            "document_id": document.document_id,
            "announcement_id": document.announcement_id,
            "chunk_count": document.chunk_count,
        },
        "items": items,
    }


def build_report_payload(
    document: LoadedChunkDocument,
    generated: GeneratedEmbeddings,
    runtime: ModelRuntimeInfo,
    *,
    batch_size: int,
    max_length: int,
) -> dict[str, Any]:
    """
    embedding_report.json에 저장할 실행 리포트를 생성한다.
    """

    vectors = generated.vectors

    norms = np.linalg.norm(
        vectors,
        axis=1,
    )

    nan_count = int(
        np.isnan(vectors).sum()
    )
    infinity_count = int(
        np.isinf(vectors).sum()
    )
    zero_vector_count = int(
        np.sum(norms == 0)
    )

    return {
        "schema_version": "embedding-report-v1",
        "status": "success",
        "created_at": datetime.now(
            timezone.utc,
        ).isoformat(),
        "source_chunk_file": str(
            document.source_path
        ),
        "document_id": document.document_id,
        "announcement_id": document.announcement_id,
        "model_name": runtime.model_name,
        "device": runtime.device,
        "device_name": runtime.device_name,
        "torch_version": runtime.torch_version,
        "cuda_version": runtime.cuda_version,
        "use_fp16": runtime.use_fp16,
        "gpu_memory_gb": runtime.gpu_memory_gb,
        "chunk_count": document.chunk_count,
        "embedding_count": generated.count,
        "embedding_dimension": generated.dimension,
        "embedding_dtype": str(
            vectors.dtype
        ),
        "normalized": generated.normalized,
        "batch_size": batch_size,
        "max_length": max_length,
        "nan_count": nan_count,
        "infinity_count": infinity_count,
        "zero_vector_count": zero_vector_count,
        "norm_statistics": {
            "minimum": float(norms.min()),
            "maximum": float(norms.max()),
            "average": float(norms.mean()),
        },
        "elapsed_seconds": round(
            generated.elapsed_seconds,
            4,
        ),
        "average_seconds_per_chunk": round(
            generated.elapsed_seconds
            / max(generated.count, 1),
            6,
        ),
    }


def write_embedding_outputs(
    document: LoadedChunkDocument,
    generated: GeneratedEmbeddings,
    runtime: ModelRuntimeInfo,
    *,
    output_dir: str | Path | None = None,
    embeddings_filename: str = "embeddings.npy",
    metadata_filename: str = "metadata.json",
    report_filename: str = "embedding_report.json",
    batch_size: int,
    max_length: int,
) -> dict[str, Path]:
    """
    임베딩 결과를 저장한다.

    Returns:
        생성한 파일 경로 딕셔너리.
    """

    if output_dir is None:
        resolved_output_dir = resolve_output_directory(
            document.source_path
        )
    else:
        resolved_output_dir = (
            Path(output_dir)
            .expanduser()
            .resolve()
        )

    resolved_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    embeddings_path = (
        resolved_output_dir
        / embeddings_filename
    )
    metadata_path = (
        resolved_output_dir
        / metadata_filename
    )
    report_path = (
        resolved_output_dir
        / report_filename
    )

    if generated.count != document.chunk_count:
        raise EmbeddingWriteError(
            "청크 수와 벡터 수가 일치하지 않습니다. "
            f"chunks={document.chunk_count}, "
            f"embeddings={generated.count}"
        )

    metadata_payload = build_metadata_payload(
        document,
        generated,
        runtime,
    )

    report_payload = build_report_payload(
        document,
        generated,
        runtime,
        batch_size=batch_size,
        max_length=max_length,
    )

    _write_numpy_atomic(
        embeddings_path,
        generated.vectors,
    )
    _write_json_atomic(
        metadata_path,
        metadata_payload,
    )
    _write_json_atomic(
        report_path,
        report_payload,
    )

    print()
    print("[임베딩 결과 저장 완료]")
    print(f"출력 폴더     : {resolved_output_dir}")
    print(f"벡터 파일     : {embeddings_path.name}")
    print(f"메타데이터    : {metadata_path.name}")
    print(f"실행 리포트   : {report_path.name}")

    return {
        "output_dir": resolved_output_dir,
        "embeddings": embeddings_path,
        "metadata": metadata_path,
        "report": report_path,
    }