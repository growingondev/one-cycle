from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ChunkSource:
    content_type: str
    paragraph_indexes: list[int] = field(default_factory=list)
    table_index: int | None = None
    record_index: int | None = None
    row_index: int | None = None
    row_kind: str | None = None
    origin_paths: list[list[str]] = field(default_factory=list)
    object_path: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ChunkingInfo:
    strategy: str
    part_index: int = 1
    part_count: int = 1
    overlap_applied: bool = False


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    chunk_order: int
    chunk_type: str

    document_id: str
    announcement_id: str
    source_filename: str
    source_format: str

    section_id: str | None
    section_level: int | None
    section_path: list[str]
    title: str
    normalized_title: str
    search_title: str

    content: str
    search_text: str
    embedding_text: str

    domain: dict[str, Any] | None
    source: ChunkSource
    entities: list[dict[str, Any]]

    token_count: int
    char_count: int
    chunking: ChunkingInfo

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
