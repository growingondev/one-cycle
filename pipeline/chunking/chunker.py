from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import ChunkingConfig
from .models import Chunk, ChunkingInfo, ChunkSource
from .paragraph_chunker import ParagraphChunker
from .section_walker import walk_sections
from .table_chunker import TableChunker
from .text_builder import (
    build_content,
    build_embedding_text,
    build_search_text,
    clean_text,
)
from .tokenizer import TokenCounter, build_token_counter
from .validator import StructuredJsonValidator


_SAFE_ID = re.compile(r"[^0-9A-Za-z가-힣_-]+")
_UNIT_ONLY_RE = re.compile(
    r"^\s*[\[\(\{]?\s*단위\s*[:：]\s*(천원|만원|억원|원|㎡|m²|m2|%)\s*[\]\)\}]?\s*$",
    re.IGNORECASE,
)


class StructureAwareChunker:
    def __init__(self, config: ChunkingConfig | None = None, token_counter: TokenCounter | None = None) -> None:
        self.config = config or ChunkingConfig()
        self.config.validate()
        self.tokens = token_counter or build_token_counter(
            self.config.tokenizer_name_or_path,
            local_files_only=self.config.tokenizer_local_files_only,
        )
        self.validator = StructuredJsonValidator()
        self.paragraph_chunker = ParagraphChunker(self.config, self.tokens)
        self.table_chunker = TableChunker(self.config, self.tokens)
        self._chunks: list[Chunk] = []
        self._warnings: list[str] = []
        self._document: dict[str, Any] = {}
        self._document_id = ""
        self._announcement_id = ""

    def chunk_file(self, input_path: str | Path, *, announcement_id: str | None = None) -> dict[str, Any]:
        input_path = Path(input_path)
        with input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return self.chunk_document(data, announcement_id=announcement_id)

    def chunk_document(self, data: dict[str, Any], *, announcement_id: str | None = None) -> dict[str, Any]:
        validation = self.validator.validate(data)
        validation.raise_for_errors()
        self._chunks = []
        self._warnings = list(validation.warnings)
        self._document = data["document"]
        self._document_id = self._make_document_id(self._document)
        self._announcement_id = announcement_id or self._document_id
        self._process_intro(data.get("intro") or [])
        self._process_sections(data.get("sections") or [])
        return {
            "document": {
                "document_id": self._document_id,
                "announcement_id": self._announcement_id,
                "filename": self._document.get("filename"),
                "source_format": self._document.get("format"),
                "source_schema_version": data.get("schema_version"),
                "chunk_schema_version": self.config.schema_version,
            },
            "chunking": {
                "strategy": self.config.strategy,
                "version": self.config.schema_version,
                "implementation_version": "generalized-unit-semantic-v5",
                "tokenizer": self.tokens.name,
                "target_tokens": self.config.target_tokens,
                "max_tokens": self.config.max_tokens,
                "min_tokens": self.config.min_tokens,
                "overlap_tokens": self.config.overlap_tokens,
            },
            "chunks": [chunk.to_dict() for chunk in self._chunks],
            "report": self._build_report(data),
        }

    def _process_intro(self, intro: list[dict[str, Any]]) -> None:
        section = {
            "section_id": None, "level": 0, "title": "공고 개요",
            "normalized_title": "공고 개요", "search_title": "공고 개요", "domain": None,
        }
        self._process_ordered_contents(intro, section=section, section_path=["공고 개요"], intro_mode=True)

    def _process_sections(self, sections: list[dict[str, Any]]) -> None:
        for context in walk_sections(sections):
            self._process_ordered_contents(
                context.section.get("contents") or [],
                section=context.section,
                section_path=context.section_path,
                intro_mode=False,
            )

    def _process_ordered_contents(self, contents, *, section, section_path, intro_mode) -> None:
        paragraph_buffer: list[dict[str, Any]] = []

        def flush_paragraphs() -> None:
            nonlocal paragraph_buffer
            if paragraph_buffer:
                self._emit_paragraph_chunks(
                    paragraph_buffer, section=section, section_path=section_path, intro_mode=intro_mode
                )
                paragraph_buffer = []

        for item in contents:
            item_type = item.get("type")
            if item_type == "paragraph":
                paragraph_buffer.append(item)
            elif item_type == "table":
                inherited_unit = self._trailing_unit(paragraph_buffer)
                flush_paragraphs()
                self._emit_table_chunks(
                    item, section=section, section_path=section_path,
                    intro_mode=intro_mode, inherited_unit=inherited_unit
                )
            else:
                flush_paragraphs()
                self._warnings.append(
                    f"Skipped unsupported content type {item_type!r} in section {section.get('section_id')!r}"
                )
        flush_paragraphs()

    @staticmethod
    def _trailing_unit(paragraphs: list[dict[str, Any]]) -> str | None:
        if not paragraphs:
            return None
        match = _UNIT_ONLY_RE.fullmatch(clean_text(paragraphs[-1].get("text")))
        if not match:
            return None
        unit = match.group(1)
        return {"m2": "㎡", "m²": "㎡"}.get(unit.lower(), unit)

    def _body_limits(self, section_path: list[str]) -> tuple[int, int]:
        heading = " > ".join(x for x in section_path if x)
        reserve = self.tokens.count(heading) + (8 if heading else 4)
        max_body = max(16, self.config.max_tokens - reserve)
        return min(self.config.target_tokens, max_body), max_body

    def _emit_paragraph_chunks(self, paragraphs, *, section, section_path, intro_mode) -> None:
        target, maximum = self._body_limits(section_path)
        parts = self.paragraph_chunker.chunk(paragraphs, target_tokens=target, max_tokens=maximum)
        for part in parts:
            paragraph_indexes = [
                p["paragraph_index"] for p in part.paragraphs if isinstance(p.get("paragraph_index"), int)
            ]
            origin_paths = [
                list(p.get("origin_path") or []) for p in part.paragraphs if p.get("origin_path")
            ]
            chunk_type = (
                "intro" if intro_mode else
                "paragraph_split" if part.part_count > 1 and len(part.paragraphs) == 1 else
                "paragraph_group"
            )
            suffix = f"para_{paragraph_indexes[0]:04d}" if paragraph_indexes else "para_na"
            if part.part_count > 1:
                suffix += f"_p{part.part_index:02d}"
            self._append_chunk(
                chunk_type=chunk_type, section=section, section_path=section_path,
                body_text=part.body_text, body_search_text=part.body_search_text, entities=[],
                source=ChunkSource(
                    content_type="paragraph", paragraph_indexes=paragraph_indexes, origin_paths=origin_paths
                ),
                source_suffix=suffix,
                strategy="paragraph_group" if len(part.paragraphs) > 1 else "paragraph",
                part_index=part.part_index, part_count=part.part_count,
                overlap_applied=part.overlap_applied,
            )

    def _emit_table_chunks(self, table, *, section, section_path, intro_mode, inherited_unit) -> None:
        target, maximum = self._body_limits(section_path)
        parts = self.table_chunker.chunk(
            table, inherited_unit=inherited_unit, target_tokens=target, max_tokens=maximum
        )
        for part in parts:
            table_index = part.table_index
            suffix = f"tbl_{table_index:04d}" if isinstance(table_index, int) else "tbl_na"
            if part.record_index is not None:
                suffix += f"_rec_{int(part.record_index):04d}"
            if part.part_count > 1:
                suffix += f"_p{part.part_index:02d}"
            chunk_type = "intro" if intro_mode else (
                "table_fallback" if part.strategy.startswith("table_fallback") else "table_record"
            )
            self._append_chunk(
                chunk_type=chunk_type, section=section, section_path=section_path,
                body_text=part.body_text, body_search_text=part.body_search_text, entities=part.entities,
                source=ChunkSource(
                    content_type="table", table_index=part.table_index,
                    record_index=part.record_index, row_index=part.row_index, row_kind=part.row_kind,
                    origin_paths=[list(table.get("origin_path") or [])] if table.get("origin_path") else [],
                    object_path=part.object_path,
                ),
                source_suffix=suffix, strategy=part.strategy,
                part_index=part.part_index, part_count=part.part_count,
                overlap_applied=part.overlap_applied,
            )

    def _append_chunk(self, *, chunk_type, section, section_path, body_text, body_search_text,
                      entities, source, source_suffix, strategy, part_index, part_count, overlap_applied) -> None:
        body_text = clean_text(body_text)
        if not body_text:
            self._warnings.append(f"Skipped empty chunk candidate: {section.get('section_id')} {source_suffix}")
            return
        normalized_title = clean_text(section.get("normalized_title") or section.get("title"))
        search_title = clean_text(section.get("search_title") or normalized_title)
        title = clean_text(section.get("title") or normalized_title)
        domain = section.get("domain") if isinstance(section.get("domain"), dict) else None
        content = build_content(
            section_path, body_text, include_path=self.config.include_section_path_in_content
        )
        search_text = build_search_text(
            section_path=section_path, normalized_title=normalized_title, search_title=search_title,
            body_search_text=body_search_text, domain=domain,
            include_path=self.config.include_section_path_in_search_text,
            include_domain=self.config.include_domain_in_search_text,
        )
        embedding_text = build_embedding_text(section_path, body_text)
        token_count = self.tokens.count(embedding_text)
        if token_count > self.config.max_tokens:
            self._warnings.append(
                f"MAX_TOKEN_VIOLATION {source_suffix}: {token_count}>{self.config.max_tokens}"
            )
        section_id = section.get("section_id")
        logical_section = section_id or "intro"
        chunk_id = self._unique_chunk_id(f"{self._document_id}_{logical_section}_{source_suffix}")
        self._chunks.append(
            Chunk(
                chunk_id=chunk_id, chunk_order=len(self._chunks) + 1, chunk_type=chunk_type,
                document_id=self._document_id, announcement_id=self._announcement_id,
                source_filename=str(self._document.get("filename") or ""),
                source_format=str(self._document.get("format") or ""),
                section_id=section_id, section_level=section.get("level"),
                section_path=list(section_path), title=title,
                normalized_title=normalized_title, search_title=search_title,
                content=content, search_text=search_text, embedding_text=embedding_text,
                domain=domain, source=source, entities=entities,
                token_count=token_count, char_count=len(content),
                chunking=ChunkingInfo(
                    strategy=strategy, part_index=part_index, part_count=part_count,
                    overlap_applied=overlap_applied,
                ),
            )
        )

    def _build_report(self, source_data: dict[str, Any]) -> dict[str, Any]:
        type_counts = Counter(chunk.chunk_type for chunk in self._chunks)
        token_counts = [chunk.token_count for chunk in self._chunks]
        ids = [chunk.chunk_id for chunk in self._chunks]
        contents = [clean_text(chunk.content) for chunk in self._chunks if clean_text(chunk.content)]
        over_max = sum(1 for n in token_counts if n > self.config.max_tokens)
        empty_embedding = sum(1 for c in self._chunks if not clean_text(c.embedding_text))
        duplicate_ids = len(ids) - len(set(ids))
        duplicate_content = len(contents) - len(set(contents))
        missing_source = sum(
            1 for c in self._chunks
            if (c.source.content_type == "paragraph" and not c.source.paragraph_indexes and not c.source.origin_paths)
            or (c.source.content_type == "table" and c.source.table_index is None and not c.source.origin_paths)
        )
        percent_candidates = [
            c.chunk_id for c in self._chunks
            if re.search(r"(?m)^[^:\n]*\(\s*\d+(?:\.\d+)?\s*%\s*\)[^:\n]*:\s*\d[\d,.]*\s*%\s*$", c.content)
        ]
        quality_gate = {
            "pass": not any([over_max, empty_embedding, duplicate_ids, missing_source, len(percent_candidates)]),
            "max_token_violations": over_max,
            "empty_embedding_text": empty_embedding,
            "duplicate_chunk_ids": duplicate_ids,
            "duplicate_content_warnings": duplicate_content,
            "missing_source_reference": missing_source,
            "unit_contamination_candidates": percent_candidates,
        }
        return {
            "total_chunks": len(self._chunks),
            "chunk_types": dict(sorted(type_counts.items())),
            "token_stats": {
                "min": min(token_counts, default=0),
                "max": max(token_counts, default=0),
                "average": round(sum(token_counts) / len(token_counts), 2) if token_counts else 0,
                "over_max_count": over_max,
            },
            "quality_gate": quality_gate,
            "warnings": self._warnings,
            "source_value_normalization_warnings": source_data.get("value_normalization_warnings", []),
        }

    @staticmethod
    def _make_document_id(document: dict[str, Any]) -> str:
        filename = str(document.get("filename") or "document")
        safe = _SAFE_ID.sub("_", Path(filename).stem).strip("_")[:60] or "document"
        digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:10]
        return f"{safe}_{digest}"

    def _unique_chunk_id(self, raw: str) -> str:
        base = _SAFE_ID.sub("_", raw).strip("_")
        existing = {chunk.chunk_id for chunk in self._chunks}
        if base not in existing:
            return base
        suffix = 2
        while f"{base}_{suffix}" in existing:
            suffix += 1
        return f"{base}_{suffix}"
