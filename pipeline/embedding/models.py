from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EmbeddingItem:
    """
    임베딩 대상 청크 하나를 표현한다.

    embedding_text:
        BGE-M3 모델에 실제로 전달할 텍스트.

    metadata:
        벡터와 함께 보존할 청크 정보.
        이후 pgvector 저장, 검색 결과 표시, 출처 추적에 사용한다.
    """

    chunk_id: str
    embedding_text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LoadedChunkDocument:
    """
    chunks.json 한 파일을 읽은 결과를 표현한다.
    """

    source_path: Path
    document: dict[str, Any]
    chunking: dict[str, Any]
    items: list[EmbeddingItem]

    @property
    def chunk_count(self) -> int:
        return len(self.items)

    @property
    def document_id(self) -> str | None:
        value = self.document.get("document_id")
        return str(value) if value is not None else None

    @property
    def announcement_id(self) -> str | None:
        value = self.document.get("announcement_id")
        return str(value) if value is not None else None