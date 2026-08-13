from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EmbeddingItem, LoadedChunkDocument


class ChunkLoadError(ValueError):
    """청크 JSON을 정상적으로 읽을 수 없을 때 발생하는 오류."""


def _read_json(path: Path) -> dict[str, Any]:
    """
    UTF-8 JSON 파일을 읽고 최상위 객체를 반환한다.
    """

    if not path.exists():
        raise ChunkLoadError(f"입력 파일을 찾을 수 없습니다: {path}")

    if not path.is_file():
        raise ChunkLoadError(f"입력 경로가 파일이 아닙니다: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ChunkLoadError(
            f"JSON 형식이 올바르지 않습니다: {path}\n"
            f"line={exc.lineno}, column={exc.colno}, message={exc.msg}"
        ) from exc
    except OSError as exc:
        raise ChunkLoadError(
            f"JSON 파일을 읽는 중 오류가 발생했습니다: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise ChunkLoadError(
            f"JSON 최상위 값은 객체여야 합니다: {path}"
        )

    return data


def _copy_metadata(
    chunk: dict[str, Any],
    *,
    document: dict[str, Any],
    source_path: Path,
    vector_index: int,
) -> dict[str, Any]:
    """
    원본 청크에서 벡터와 함께 저장할 메타데이터를 구성한다.

    원본 청크의 핵심 필드를 유지하며,
    없는 선택 필드는 None 또는 빈 값으로 보존한다.
    """

    document_id = (
        chunk.get("document_id")
        or document.get("document_id")
    )

    announcement_id = (
        chunk.get("announcement_id")
        or document.get("announcement_id")
    )

    return {
        # embeddings.npy에서 해당 벡터의 행 번호
        "vector_index": vector_index,

        # 청크 및 문서 식별자
        "chunk_id": chunk.get("chunk_id"),
        "document_id": document_id,
        "announcement_id": announcement_id,

        # 문서 내 청크 위치
        "chunk_order": chunk.get("chunk_order"),
        "chunk_type": chunk.get("chunk_type"),
        "section_id": chunk.get("section_id"),
        "section_level": chunk.get("section_level"),
        "section_path": chunk.get("section_path", []),

        # 제목 정보
        "title": chunk.get("title"),
        "normalized_title": chunk.get("normalized_title"),
        "search_title": chunk.get("search_title"),

        # 검색 및 답변용 텍스트
        "content": chunk.get("content"),
        "search_text": chunk.get("search_text"),

        # 분류 및 원본 추적 정보
        "domain": chunk.get("domain"),
        "source": chunk.get("source"),

        # 청크 통계
        "token_count": chunk.get("token_count"),
        "char_count": chunk.get("char_count"),

        # 원본 파일 정보
        "source_filename": chunk.get(
            "source_filename",
            document.get("filename"),
        ),
        "source_format": chunk.get(
            "source_format",
            document.get("source_format")
            or document.get("format"),
        ),

        # 디버깅 및 재현성
        "source_chunk_file": str(source_path),
    }


def load_chunk_document(
    input_path: str | Path,
    *,
    text_field: str = "embedding_text",
    limit: int | None = None,
) -> LoadedChunkDocument:
    """
    chunks.json 한 파일을 읽어 임베딩 대상 목록으로 변환한다.

    Args:
        input_path:
            chunks.json 경로.

        text_field:
            임베딩 모델에 전달할 청크 필드명.
            기본값은 embedding_text.

        limit:
            앞에서부터 읽을 최대 청크 수.
            모델 소량 테스트 시 5 등을 전달할 수 있다.
            None이면 전체 청크를 읽는다.

    Returns:
        LoadedChunkDocument

    Raises:
        ChunkLoadError:
            파일 또는 JSON 구조에 문제가 있는 경우.
    """

    path = Path(input_path).expanduser().resolve()
    data = _read_json(path)

    document = data.get("document", {})
    chunking = data.get("chunking", {})
    chunks = data.get("chunks")

    if not isinstance(document, dict):
        raise ChunkLoadError(
            f"'document'는 객체여야 합니다: {path}"
        )

    if not isinstance(chunking, dict):
        raise ChunkLoadError(
            f"'chunking'은 객체여야 합니다: {path}"
        )

    if not isinstance(chunks, list):
        raise ChunkLoadError(
            f"'chunks'는 배열이어야 합니다: {path}"
        )

    if limit is not None:
        if limit <= 0:
            raise ChunkLoadError(
                f"limit은 1 이상의 정수여야 합니다: {limit}"
            )

        chunks = chunks[:limit]

    items: list[EmbeddingItem] = []

    for vector_index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ChunkLoadError(
                f"chunks[{vector_index}]는 객체여야 합니다: {path}"
            )

        chunk_id = chunk.get("chunk_id")
        embedding_text = chunk.get(text_field)

        # 세부 검증은 validator.py에서 다시 수행하지만,
        # 데이터 모델 생성에 필요한 최소 조건은 여기서 확인한다.
        if not isinstance(chunk_id, str):
            raise ChunkLoadError(
                f"chunks[{vector_index}].chunk_id는 문자열이어야 합니다."
            )

        if not isinstance(embedding_text, str):
            raise ChunkLoadError(
                f"chunks[{vector_index}].{text_field}는 "
                "문자열이어야 합니다."
            )

        metadata = _copy_metadata(
            chunk,
            document=document,
            source_path=path,
            vector_index=vector_index,
        )

        items.append(
            EmbeddingItem(
                chunk_id=chunk_id,
                embedding_text=embedding_text,
                metadata=metadata,
            )
        )

    return LoadedChunkDocument(
        source_path=path,
        document=document,
        chunking=chunking,
        items=items,
    )


def load_multiple_chunk_documents(
    input_paths: list[str | Path],
    *,
    text_field: str = "embedding_text",
    limit_per_file: int | None = None,
) -> list[LoadedChunkDocument]:
    """
    여러 chunks.json 파일을 순서대로 읽는다.

    한 파일에서 오류가 발생하면 전체 실행을 중단한다.
    임베딩 결과가 일부만 생성되는 상태를 방지하기 위함이다.
    """

    if not input_paths:
        raise ChunkLoadError(
            "입력 chunks.json 경로가 하나 이상 필요합니다."
        )

    documents: list[LoadedChunkDocument] = []

    for input_path in input_paths:
        documents.append(
            load_chunk_document(
                input_path,
                text_field=text_field,
                limit=limit_per_file,
            )
        )

    return documents

def discover_chunk_files(
    outputs_root: str | Path,
    *,
    formats: tuple[str, ...] = ("hwp", "hwpx"),
) -> list[Path]:
    """
    outputs 아래의 모든 청크 JSON을 자동으로 탐색한다.

    탐색 경로:
        outputs/announcement_*/04_chunks/<format>/chunks.json

    Args:
        outputs_root:
            outputs 폴더 경로.

        formats:
            처리할 원본 형식. 기본값은 hwp와 hwpx.

    Returns:
        정렬된 chunks.json 경로 목록.
    """

    root = Path(outputs_root).expanduser().resolve()

    if not root.exists():
        raise ChunkLoadError(
            f"outputs 폴더를 찾을 수 없습니다: {root}"
        )

    if not root.is_dir():
        raise ChunkLoadError(
            f"outputs 경로가 폴더가 아닙니다: {root}"
        )

    discovered: list[Path] = []

    announcement_dirs = sorted(
        path
        for path in root.glob("announcement_*")
        if path.is_dir()
    )

    for announcement_dir in announcement_dirs:
        for source_format in formats:
            chunk_path = (
                announcement_dir
                / "04_chunks"
                / source_format
                / "chunks.json"
            )

            if chunk_path.is_file():
                discovered.append(chunk_path.resolve())

    if not discovered:
        expected = (
            root
            / "announcement_*"
            / "04_chunks"
            / "{hwp,hwpx}"
            / "chunks.json"
        )

        raise ChunkLoadError(
            "임베딩할 chunks.json을 찾지 못했습니다.\n"
            f"outputs 루트: {root}\n"
            f"예상 구조: {expected}"
        )

    return discovered