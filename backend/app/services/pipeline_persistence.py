import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import numpy as np
from sqlalchemy import select

from config.paths import OUTPUT_ROOT
from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models import (
    Announcement,
    Chunk,
    ChunkSet,
    Document,
    DocumentStructure,
    Embedding,
    ProcessingRun,
)


WORKER_OUTPUT_ROOT = PurePosixPath("/app/outputs")


def load_json(path: Path):
    if not path.is_file():
        raise RuntimeError(f"파일이 없습니다: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise RuntimeError(f"JSON 최상위가 객체가 아닙니다: {path}")

    return data


def _validate_bundle_root_identity(
    *,
    document_dir_name: str,
    announcement_dir_name: str,
    announcement_key: str,
    document_id: int | None,
) -> None:
    if document_id is None:
        return

    expected_document_dir = (
        f"document_{document_id}"
    )

    if document_dir_name != expected_document_dir:
        raise RuntimeError(
            "Worker output_path의 Document 경로가 "
            "요청한 document_id와 다릅니다. "
            f"expected={expected_document_dir}, "
            f"actual={document_dir_name}"
        )

    if announcement_dir_name != str(
        announcement_key
    ):
        raise RuntimeError(
            "Worker output_path의 Announcement 경로가 "
            "요청한 announcement_key와 다릅니다. "
            f"expected={announcement_key}, "
            f"actual={announcement_dir_name}"
        )


def _resolve_worker_output_mapping(
    logical_path: PurePosixPath,
) -> Path | None:
    """
    Map a Worker container output path to a path visible
    to a host-side persistence process.

    Docker-to-Docker execution keeps using the original
    path when it is directly accessible.
    """

    if os.name != "nt":
        direct_path = Path(
            str(logical_path)
        ).resolve()

        if direct_path.exists():
            return None

    access_root_value = (
        settings.pipeline_output_host_path
        .strip()
    )

    if not access_root_value:
        return None

    try:
        relative_path = (
            logical_path.relative_to(
                WORKER_OUTPUT_ROOT
            )
        )
    except ValueError:
        return None

    if ".." in relative_path.parts:
        raise RuntimeError(
            "Worker output_path contains an unsafe "
            f"parent traversal: {logical_path}"
        )

    access_root = Path(
        access_root_value
    ).expanduser()

    if not access_root.is_absolute():
        raise RuntimeError(
            "PIPELINE_OUTPUT_HOST_PATH must be "
            f"an absolute path: {access_root}"
        )

    access_root = access_root.resolve()
    mapped_path = access_root.joinpath(
        *relative_path.parts
    ).resolve()

    try:
        mapped_path.relative_to(access_root)
    except ValueError as error:
        raise RuntimeError(
            "Mapped Worker output_path escapes "
            "PIPELINE_OUTPUT_HOST_PATH."
        ) from error

    return mapped_path


def _resolve_bundle_root(
    *,
    announcement_key: str,
    document_id: int | None,
    output_root_path: str | Path | None,
) -> Path:
    if output_root_path is None:
        root = OUTPUT_ROOT / announcement_key

        if document_id is not None:
            root = root / f"document_{document_id}"

        return root

    raw_path = str(
        output_root_path
    ).strip()

    if not raw_path:
        raise RuntimeError(
            "output_root_path가 비어 있습니다."
        )

    # Worker/Backend Docker 계약은 POSIX 절대경로를 사용한다.
    if raw_path.startswith("/"):
        logical_path = PurePosixPath(
            raw_path
        )

        _validate_bundle_root_identity(
            document_dir_name=logical_path.name,
            announcement_dir_name=(
                logical_path.parent.name
            ),
            announcement_key=announcement_key,
            document_id=document_id,
        )

        mapped_root = (
            _resolve_worker_output_mapping(
                logical_path
            )
        )

        if mapped_root is not None:
            return mapped_root

        # Windows host에서 /data/...를 Path.resolve()하면
        # C:\data\...로 잘못 해석되므로 암묵적으로 변환하지 않는다.
        if os.name == "nt":
            raise RuntimeError(
                "Docker POSIX output_path는 Windows host에서 "
                "직접 접근할 수 없습니다: "
                f"{raw_path}. "
                "API 통합은 Docker 환경에서 실행하거나, "
                "로컬 테스트에서는 Windows native 절대경로를 "
                "사용하세요."
            )

        return Path(
            raw_path
        ).resolve()

    root = Path(
        raw_path
    ).expanduser()

    if not root.is_absolute():
        raise RuntimeError(
            "output_root_path는 절대 경로여야 합니다: "
            f"{root}"
        )

    root = root.resolve()

    _validate_bundle_root_identity(
        document_dir_name=root.name,
        announcement_dir_name=root.parent.name,
        announcement_key=announcement_key,
        document_id=document_id,
    )

    return root


def find_bundle(
    announcement_key: str,
    document_id: int | None = None,
    output_root_path: str | Path | None = None,
):
    root = _resolve_bundle_root(
        announcement_key=announcement_key,
        document_id=document_id,
        output_root_path=output_root_path,
    )

    for document_format in ("hwpx", "hwp"):
        bundle = {
            "format": document_format,
            "root": root,
            "structure": (
                root
                / "03_structured"
                / document_format
                / "step4-1_value_normalized.json"
            ),
            "verification": (
                root
                / "03_structured"
                / document_format
                / "step4-3_verification.json"
            ),
            "chunks": (
                root
                / "04_chunks"
                / document_format
                / "chunks.json"
            ),
            "metadata": (
                root
                / "05_embeddings"
                / document_format
                / "metadata.json"
            ),
            "embeddings": (
                root
                / "05_embeddings"
                / document_format
                / "embeddings.npy"
            ),
        }

        required = (
            "structure",
            "verification",
            "chunks",
            "metadata",
            "embeddings",
        )

        if all(bundle[name].is_file() for name in required):
            return bundle

    raise RuntimeError(
        f"완성된 대표 문서 outputs가 없습니다: {announcement_key}"
    )


def validate_outputs(
    announcement_key: str,
    document_id: int | None = None,
    announcement_db_id: int | None = None,
    output_root_path: str | Path | None = None,
):
    bundle = find_bundle(
        announcement_key,
        document_id=document_id,
        output_root_path=output_root_path,
    )

    expected_announcement_id = (
        str(announcement_db_id)
        if announcement_db_id is not None
        else announcement_key
    )

    document_format = bundle["format"]

    structure = load_json(bundle["structure"])
    verification = load_json(bundle["verification"])
    chunks_payload = load_json(bundle["chunks"])
    metadata = load_json(bundle["metadata"])

    vectors = np.load(
        bundle["embeddings"],
        allow_pickle=False,
    )

    if verification.get("status") != "pass":
        raise RuntimeError(
            f"verification이 pass가 아닙니다: {verification.get('status')}"
        )

    structure_document = structure.get("document") or {}

    filename = structure_document.get("filename")

    if not filename:
        raise RuntimeError("Structure filename이 없습니다.")

    if (
        str(structure_document.get("format") or "").lower()
        != document_format
    ):
        raise RuntimeError("Structure format이 대표 문서 형식과 다릅니다.")

    chunk_document = chunks_payload.get("document") or {}
    chunks = chunks_payload.get("chunks") or []

    if str(chunk_document.get("announcement_id")) != expected_announcement_id:
        raise RuntimeError(
            "Chunk announcement_id가 다릅니다. "
            f"expected={expected_announcement_id}, "
            f"actual={chunk_document.get('announcement_id')}"
        )

    if (
        str(chunk_document.get("source_format") or "").lower()
        != document_format
    ):
        raise RuntimeError("Chunk source_format이 다릅니다.")

    if not chunks:
        raise RuntimeError("Chunk가 없습니다.")

    chunk_ids = [str(chunk.get("chunk_id") or "") for chunk in chunks]

    if any(not chunk_id for chunk_id in chunk_ids):
        raise RuntimeError("비어 있는 chunk_id가 있습니다.")

    if len(chunk_ids) != len(set(chunk_ids)):
        raise RuntimeError("중복 chunk_id가 있습니다.")


    model = metadata.get("model") or {}
    source = metadata.get("source") or {}
    items = metadata.get("items") or []

    if model.get("name") != "BAAI/bge-m3":
        raise RuntimeError(
            f"Embedding model이 다릅니다: {model.get('name')}"
        )

    if int(model.get("dimension") or 0) != 1024:
        raise RuntimeError("metadata dimension이 1024가 아닙니다.")

    if model.get("normalized") is not True:
        raise RuntimeError("Embedding normalized가 True가 아닙니다.")

    if str(source.get("announcement_id")) != expected_announcement_id:
        raise RuntimeError(
            "Embedding announcement_id가 다릅니다. "
            f"expected={expected_announcement_id}, "
            f"actual={source.get('announcement_id')}"
        )

    if int(source.get("chunk_count") or -1) != len(chunks):
        raise RuntimeError("Embedding chunk_count가 다릅니다.")

    if vectors.ndim != 2:
        raise RuntimeError(f"Embedding 배열 shape 오류: {vectors.shape}")

    if vectors.shape != (len(chunks), 1024):
        raise RuntimeError(
            f"Chunk/Embedding 크기 불일치: "
            f"chunks={len(chunks)}, vectors={vectors.shape}"
        )

    if len(items) != len(chunks):
        raise RuntimeError("metadata items 수가 Chunk 수와 다릅니다.")

    item_chunk_ids = [
        str(item.get("chunk_id") or "")
        for item in items
    ]

    if len(item_chunk_ids) != len(set(item_chunk_ids)):
        raise RuntimeError("metadata에 중복 chunk_id가 있습니다.")

    if set(item_chunk_ids) != set(chunk_ids):
        raise RuntimeError(
            "Chunk JSON과 Embedding metadata의 chunk_id가 다릅니다."
        )

    vector_indices = [
        item.get("vector_index")
        for item in items
    ]

    if not all(isinstance(index, int) for index in vector_indices):
        raise RuntimeError("잘못된 vector_index가 있습니다.")

    if sorted(vector_indices) != list(range(len(items))):
        raise RuntimeError("vector_index가 0부터 연속되지 않습니다.")

    if not np.isfinite(vectors).all():
        raise RuntimeError("Embedding에 NaN 또는 Inf가 있습니다.")

    norms = np.linalg.norm(vectors, axis=1)

    if not np.allclose(norms, 1.0, atol=1e-4):
        raise RuntimeError(
            f"L2 normalization 실패: "
            f"min={norms.min()}, max={norms.max()}"
        )

    return {
        "announcement_key": announcement_key,
        "format": document_format,
        "filename": filename,
        "schema_version": structure.get("schema_version"),
        "verification": verification.get("status"),
        "chunk_count": len(chunks),
        "model": model.get("name"),
        "dimension": vectors.shape[1],
        "embedding_count": vectors.shape[0],
        "norm_min": float(norms.min()),
        "norm_max": float(norms.max()),
    }


def get_registered_document_context(document_id: int):
    with SessionLocal() as db:
        row = db.execute(
            select(Announcement, Document)
            .join(
                Document,
                Document.announcement_id == Announcement.id,
            )
            .where(
                Document.id == document_id,
                Document.download_status == "completed",
            )
        ).one_or_none()

        if row is None:
            raise RuntimeError(
                "completed 상태의 Document를 찾을 수 없습니다. "
                f"document_id={document_id}"
            )

        announcement, document = row

        return {
            "announcement_key": announcement.source_announcement_id,
            "announcement_db_id": announcement.id,
            "document_db_id": document.id,
            "filename": document.original_filename,
            "format": document.document_format,
            "storage_path": (
                str(document.storage_path)
                if document.storage_path
                else None
            ),
        }


def validate_document_outputs(document_id: int):
    context = get_registered_document_context(document_id)

    summary = validate_outputs(
        context["announcement_key"],
        document_id=context["document_db_id"],
        announcement_db_id=context["announcement_db_id"],
    )

    if summary["filename"] != context["filename"]:
        raise RuntimeError(
            "Structure filename과 DB Document가 다릅니다. "
            f"db={context['filename']}, "
            f"output={summary['filename']}"
        )

    if summary["format"] != context["format"]:
        raise RuntimeError(
            "Structure format과 DB Document가 다릅니다. "
            f"db={context['format']}, "
            f"output={summary['format']}"
        )

    result = dict(summary)
    result.update(context)
    return result


def validate_registered_document(summary):
    with SessionLocal() as db:
        rows = db.execute(
            select(Announcement, Document)
            .join(
                Document,
                Document.announcement_id == Announcement.id,
            )
            .where(
                Announcement.source_announcement_id
                == summary["announcement_key"],
                Document.original_filename
                == summary["filename"],
                Document.document_format
                == summary["format"],
                Document.download_status == "completed",
            )
        ).all()

        if len(rows) != 1:
            raise RuntimeError(
                "등록된 Document가 정확히 1건이어야 합니다. "
                f"actual={len(rows)}"
            )

        announcement, document = rows[0]

        return {
            "announcement_db_id": announcement.id,
            "document_db_id": document.id,
        }



def sha256_file(path: Path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def sha256_text(text: str):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def count_structure_elements(data):
    total = len(data.get("intro") or [])

    def walk(sections):
        count = 0

        for section in sections:
            count += len(section.get("contents") or [])
            count += walk(section.get("children") or [])

        return count

    return total + walk(data.get("sections") or [])


def extract_source_block_ids(source):
    result = []

    for origin_path in source.get("origin_paths", []):
        if not isinstance(origin_path, list):
            continue

        for value in origin_path:
            if (
                isinstance(value, str)
                and value.startswith("block:")
                and value not in result
            ):
                result.append(value)

    return result


def build_source_table_id(source):
    table_index = source.get("table_index")

    if table_index is None:
        return None

    return f"table:{table_index}"


def persist_outputs(
    announcement_key,
    document_id: int | None = None,
    announcement_db_id: int | None = None,
    output_root_path: str | Path | None = None,
):
    summary = validate_outputs(
        announcement_key,
        document_id=document_id,
        announcement_db_id=announcement_db_id,
        output_root_path=output_root_path,
    )
    bundle = find_bundle(
        announcement_key,
        document_id=document_id,
        output_root_path=output_root_path,
    )

    structure = load_json(bundle["structure"])
    chunks_payload = load_json(bundle["chunks"])
    metadata = load_json(bundle["metadata"])

    vectors = np.load(
        bundle["embeddings"],
        allow_pickle=False,
    )

    chunks = chunks_payload.get("chunks") or []
    chunking = chunks_payload.get("chunking") or {}
    model = metadata.get("model") or {}
    items = metadata.get("items") or []

    with SessionLocal.begin() as db:
        rows = db.execute(
            select(Announcement, Document)
            .join(
                Document,
                Document.announcement_id == Announcement.id,
            )
            .where(
                Announcement.source_announcement_id
                == announcement_key,
                Document.original_filename
                == summary["filename"],
                Document.document_format
                == summary["format"],
                Document.download_status == "completed",
                *(
                    [Document.id == document_id]
                    if document_id is not None
                    else []
                ),
            )
        ).all()

        if len(rows) != 1:
            raise RuntimeError(
                "등록된 Document가 정확히 1건이어야 합니다. "
                f"actual={len(rows)}, document_id={document_id}"
            )

        announcement, document = rows[0]

        now = datetime.now(timezone.utc)

        processing_run = ProcessingRun(
            document_id=document.id,
            execution_status="succeeded",
            verification_status="pass",
            current_stage="embedding",
            pipeline_version="mvp-output-persistence-v1",
            output_root_path=str(bundle["root"]),
            exit_code=0,
            started_at=now,
            finished_at=now,
            is_active=False,
            activated_at=None,
        )

        db.add(processing_run)
        db.flush()

        document_structure = DocumentStructure(
            processing_run_id=processing_run.id,
            schema_version=str(
                structure.get("schema_version") or "unknown"
            ),
            structure_json=structure,
            element_count=count_structure_elements(structure),
            content_hash=sha256_file(bundle["structure"]),
        )

        db.add(document_structure)
        db.flush()

        chunk_config = {
            "tokenizer": chunking.get("tokenizer"),
            "target_tokens": chunking.get("target_tokens"),
            "max_tokens": chunking.get("max_tokens"),
            "min_tokens": chunking.get("min_tokens"),
            "overlap_tokens": chunking.get("overlap_tokens"),
        }

        chunk_set = ChunkSet(
            processing_run_id=processing_run.id,
            chunker_version=str(
                chunking.get("version") or "unknown"
            ),
            strategy=str(
                chunking.get("strategy") or "unknown"
            ),
            chunking_config=chunk_config,
            input_content_version=str(
                structure.get("schema_version") or "unknown"
            ),
            status="completed",
            is_active=False,
            chunk_count=len(chunks),
            error_message=None,
            started_at=now,
            finished_at=now,
            activated_at=None,
        )

        db.add(chunk_set)
        db.flush()

        chunk_by_key = {}

        for raw_chunk in chunks:
            source = raw_chunk.get("source") or {}

            content = str(raw_chunk["content"])
            embedding_text = str(
                raw_chunk["embedding_text"]
            )

            chunk_metadata = {
                "domain": raw_chunk.get("domain"),
                "entities": raw_chunk.get("entities", []),
                "chunking": raw_chunk.get("chunking", {}),
                "normalized_title": raw_chunk.get(
                    "normalized_title"
                ),
                "search_title": raw_chunk.get("search_title"),
                "section_id": raw_chunk.get("section_id"),
                "section_level": raw_chunk.get(
                    "section_level"
                ),
                "source_filename": raw_chunk.get(
                    "source_filename"
                ),
                "source_content_type": source.get(
                    "content_type"
                ),
                "logical_announcement_id": raw_chunk.get(
                    "announcement_id"
                ),
                "chunk_document_id": raw_chunk.get(
                    "document_id"
                ),
            }

            chunk = Chunk(
                chunk_set_id=chunk_set.id,
                announcement_id=announcement.id,
                document_id=document.id,
                external_chunk_key=str(
                    raw_chunk["chunk_id"]
                ),
                chunk_index=int(
                    raw_chunk["chunk_order"]
                ),
                document_format=summary["format"],
                content_type=str(
                    raw_chunk["chunk_type"]
                ),
                title=raw_chunk.get("title"),
                section_path=raw_chunk.get(
                    "section_path",
                    [],
                ),
                content=content,
                search_text=raw_chunk.get("search_text"),
                embedding_text=embedding_text,
                token_count=raw_chunk.get("token_count"),
                character_count=raw_chunk.get("char_count"),
                source_block_ids=extract_source_block_ids(
                    source
                ),
                source_table_id=build_source_table_id(
                    source
                ),
                source_page=None,
                source_reference=source,
                chunk_metadata=chunk_metadata,
                content_hash=sha256_text(content),
                status="completed",
            )

            db.add(chunk)

            chunk_by_key[
                chunk.external_chunk_key
            ] = chunk

        db.flush()


        seen_keys = set()

        for item in items:
            chunk_key = str(
                item.get("chunk_id") or ""
            )

            if not chunk_key:
                raise RuntimeError(
                    "Embedding metadata chunk_id가 없습니다."
                )

            if chunk_key in seen_keys:
                raise RuntimeError(
                    f"중복 metadata chunk_id: {chunk_key}"
                )

            seen_keys.add(chunk_key)

            chunk = chunk_by_key.get(chunk_key)

            if chunk is None:
                raise RuntimeError(
                    f"DB Chunk 매칭 실패: {chunk_key}"
                )

            vector_index = item.get("vector_index")

            if not isinstance(vector_index, int):
                raise RuntimeError(
                    f"잘못된 vector_index: {vector_index}"
                )

            vector = vectors[
                vector_index
            ].astype(
                np.float32,
                copy=False,
            )

            db.add(
                Embedding(
                    chunk_id=chunk.id,
                    model_name=str(model["name"]),
                    model_version="default",
                    dimension=1024,
                    normalized=True,
                    embedding_text_hash=sha256_text(
                        chunk.embedding_text
                    ),
                    embedding=vector.tolist(),
                    status="completed",
                    error_code=None,
                    error_message=None,
                )
            )

        db.flush()

        result = dict(summary)

        result.update(
            {
                "processing_run_id": processing_run.id,
                "document_structure_id": (
                    document_structure.id
                ),
                "chunk_set_id": chunk_set.id,
                "written_chunks": len(chunks),
                "written_embeddings": len(items),
                "is_active": False,
            }
        )

        return result





def persist_document_outputs(
    document_id: int,
    *,
    output_root_path: str | Path | None = None,
):
    context = get_registered_document_context(document_id)

    result = persist_outputs(
        context["announcement_key"],
        document_id=context["document_db_id"],
        announcement_db_id=context["announcement_db_id"],
        output_root_path=output_root_path,
    )

    result["announcement_db_id"] = context["announcement_db_id"]
    result["document_db_id"] = context["document_db_id"]
    return result

def mark_processing_run_failed(
    processing_run_id: int,
    *,
    stage: str,
    error_code: str | None = None,
    error_message: str | None = None,
    exit_code: int | None = 1,
):
    normalized_stage = str(stage or "").strip()

    if not normalized_stage:
        raise ValueError("stage는 필수입니다.")

    now = datetime.now(timezone.utc)

    with SessionLocal.begin() as db:
        target = db.get(
            ProcessingRun,
            processing_run_id,
        )

        if target is None:
            raise RuntimeError(
                f"ProcessingRun 없음: {processing_run_id}"
            )

        # 기존 정상 active ProcessingRun은 실패 상태로 바꾸지 않는다.
        if target.is_active:
            raise RuntimeError(
                "active ProcessingRun은 실패 처리할 수 없습니다."
            )

        target.execution_status = "failed"
        target.current_stage = normalized_stage
        target.error_stage = normalized_stage
        target.error_code = (
            str(error_code).strip()
            if error_code
            else None
        )
        target.error_message = (
            str(error_message)
            if error_message is not None
            else None
        )
        target.exit_code = exit_code
        target.finished_at = now
        target.is_active = False

        # verification_status는 수정하지 않는다.
        # 기존 active ProcessingRun 및 KeyInformation도 수정하지 않는다.

        db.flush()

        return {
            "processing_run_id": target.id,
            "document_id": target.document_id,
            "execution_status": target.execution_status,
            "verification_status": target.verification_status,
            "current_stage": target.current_stage,
            "error_stage": target.error_stage,
            "error_code": target.error_code,
            "is_active": target.is_active,
        }

def activate_processing_run(processing_run_id):
    now = datetime.now(timezone.utc)

    with SessionLocal.begin() as db:
        target = db.get(
            ProcessingRun,
            processing_run_id,
        )

        if target is None:
            raise RuntimeError(
                f"ProcessingRun 없음: {processing_run_id}"
            )

        if target.execution_status != "succeeded":
            raise RuntimeError(
                "ProcessingRun이 succeeded가 아닙니다."
            )

        if target.verification_status != "pass":
            raise RuntimeError(
                "verification이 pass가 아닙니다."
            )

        target_chunk_set = db.scalar(
            select(ChunkSet).where(
                ChunkSet.processing_run_id == target.id
            )
        )

        if target_chunk_set is None:
            raise RuntimeError("ChunkSet이 없습니다.")

        if target_chunk_set.status != "completed":
            raise RuntimeError(
                "ChunkSet이 completed가 아닙니다."
            )

        chunks = list(
            db.scalars(
                select(Chunk).where(
                    Chunk.chunk_set_id
                    == target_chunk_set.id
                )
            )
        )

        if len(chunks) != target_chunk_set.chunk_count:
            raise RuntimeError(
                "ChunkSet chunk_count와 실제 Chunk 수가 "
                "다릅니다."
            )

        embedding_count = 0

        for chunk in chunks:
            embedding = db.scalar(
                select(Embedding).where(
                    Embedding.chunk_id == chunk.id,
                    Embedding.status == "completed",
                )
            )

            if embedding is None:
                raise RuntimeError(
                    "Embedding이 없는 Chunk가 있습니다: "
                    f"{chunk.external_chunk_key}"
                )

            embedding_count += 1

        if embedding_count != len(chunks):
            raise RuntimeError(
                "Chunk와 Embedding 수가 다릅니다."
            )

        old_active_runs = list(
            db.scalars(
                select(ProcessingRun).where(
                    ProcessingRun.document_id
                    == target.document_id,
                    ProcessingRun.is_active.is_(True),
                    ProcessingRun.id != target.id,
                )
            )
        )

        for old_run in old_active_runs:
            old_run.is_active = False

        db.flush()

        target.is_active = True
        target.activated_at = now

        target_chunk_set.is_active = True
        target_chunk_set.activated_at = now

        db.flush()

        return {
            "processing_run_id": target.id,
            "document_id": target.document_id,
            "chunk_set_id": target_chunk_set.id,
            "chunks": len(chunks),
            "embeddings": embedding_count,
            "deactivated_runs": [
                run.id for run in old_active_runs
            ],
        }




def persist_registered_outputs(
    available_announcement_keys,
):
    available_keys = set(
        available_announcement_keys
    )

    with SessionLocal() as db:
        registered_keys = set(
            db.scalars(
                select(
                    Announcement.source_announcement_id
                )
            ).all()
        )

    targets = sorted(
        available_keys & registered_keys
    )

    if not targets:
        raise RuntimeError(
            "DB에 등록된 Persistence 대상 공고가 없습니다. "
            f"available={sorted(available_keys)}, "
            f"registered={sorted(registered_keys)}"
        )

    results = []

    for announcement_key in targets:
        persisted = persist_outputs(
            announcement_key
        )

        processing_run_id = persisted[
            "processing_run_id"
        ]

        activated = activate_processing_run(
            processing_run_id
        )

        results.append(
            {
                "announcement_key": announcement_key,
                "processing_run_id": (
                    processing_run_id
                ),
                "chunk_set_id": persisted[
                    "chunk_set_id"
                ],
                "chunks": persisted[
                    "written_chunks"
                ],
                "embeddings": persisted[
                    "written_embeddings"
                ],
                "deactivated_runs": activated[
                    "deactivated_runs"
                ],
            }
        )

    return {
        "registered_keys": sorted(
            registered_keys
        ),
        "targets": targets,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--announcement-key",
        required=True,
    )

    parser.add_argument(
        "--write",
        action="store_true",
    )

    args = parser.parse_args()

    if args.write:
        result = persist_outputs(
            args.announcement_key
        )

        print()
        print("PIPELINE PERSISTENCE WRITE")
        print("=" * 50)

        for key, value in result.items():
            print(f"{key}: {value}")

        print()
        print("DB WRITE: PASS")
        print("ACTIVE SWITCH: NO")
        return

    summary = validate_outputs(
        args.announcement_key
    )
    db_info = validate_registered_document(
        summary
    )

    print()
    print("PIPELINE PERSISTENCE DRY RUN")
    print("=" * 50)

    for key, value in summary.items():
        print(f"{key}: {value}")

    for key, value in db_info.items():
        print(f"{key}: {value}")

    print()
    print("DRY RUN: PASS")
    print("DB WRITE: NO")


if __name__ == "__main__":
    main()
