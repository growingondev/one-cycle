from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import ChunkingConfig
from .text_builder import (
    clean_text,
    collect_entities,
    flatten_search_text,
    normalized_entity_text,
    unique_join,
)
from .tokenizer import TokenCounter


@dataclass(slots=True)
class TablePart:
    body_text: str
    body_search_text: str
    table_index: int | None
    record_index: int | None
    row_index: int | None
    row_kind: str | None
    entities: list[dict[str, Any]] = field(default_factory=list)
    object_path: list[str] = field(default_factory=list)
    strategy: str = "table_record"


class TableChunker:
    def __init__(self, config: ChunkingConfig, token_counter: TokenCounter) -> None:
        self.config = config
        self.tokens = token_counter

    def chunk(self, table: dict[str, Any]) -> list[TablePart]:
        structured = table.get("structured_table") or {}
        status = structured.get("status")
        layout = structured.get("layout")

        if status == "structured" and layout == "key_value":
            return self._chunk_key_value(table, structured)
        if status == "structured" and layout == "row_records":
            return self._chunk_row_records(table, structured)
        return self._chunk_fallback(table)

    def _chunk_key_value(
        self,
        table: dict[str, Any],
        structured: dict[str, Any],
    ) -> list[TablePart]:
        records = structured.get("records") or []
        record_lines: list[tuple[str, str, dict[str, Any]]] = []
        for record in records:
            key = clean_text(record.get("key"))
            value = clean_text(record.get("value"))
            if not key and not value:
                continue
            body = f"{key}: {value}" if key else value
            search = unique_join(
                [
                    record.get("key_search_text") or key,
                    value,
                    *normalized_entity_text(record.get("value_normalized")),
                ]
            )
            record_lines.append((body, search, record))

        whole_body = "\n".join(item[0] for item in record_lines)
        if (
            record_lines
            and self.tokens.count(whole_body) <= self.config.small_key_value_table_tokens
        ):
            normalized_values = [r.get("value_normalized") for _, _, r in record_lines]
            return [
                TablePart(
                    body_text=whole_body,
                    body_search_text=unique_join(item[1] for item in record_lines),
                    table_index=table.get("table_index"),
                    record_index=None,
                    row_index=None,
                    row_kind="key_value_group",
                    entities=collect_entities(normalized_values),
                    object_path=list(structured.get("object_path") or []),
                    strategy="key_value_group",
                )
            ]

        result: list[TablePart] = []
        for fallback_index, (body, search, record) in enumerate(record_lines):
            result.append(
                TablePart(
                    body_text=body,
                    body_search_text=search,
                    table_index=table.get("table_index"),
                    record_index=record.get("record_index", fallback_index),
                    row_index=record.get("row_index"),
                    row_kind="key_value",
                    entities=collect_entities([record.get("value_normalized")]),
                    object_path=list(structured.get("object_path") or []),
                    strategy="key_value_record",
                )
            )
        return result

    def _chunk_row_records(
        self,
        table: dict[str, Any],
        structured: dict[str, Any],
    ) -> list[TablePart]:
        result: list[TablePart] = []
        records = structured.get("records") or []
        table_title = clean_text(structured.get("table_title"))

        for fallback_index, record in enumerate(records):
            lines: list[str] = []
            search_parts: list[str] = [table_title]
            normalized_values: list[Any] = []

            for value_item in record.get("values") or []:
                header_path = [clean_text(x) for x in value_item.get("header_path") or []]
                header_path = [x for x in header_path if x]
                label = " > ".join(header_path) or f"열 {value_item.get('column', '')}".strip()
                value = clean_text(value_item.get("value"))
                if not value and value_item.get("status") in {"empty", "missing"}:
                    continue
                lines.append(f"{label}: {value}")
                search_parts.extend([*header_path, value])
                normalized = value_item.get("normalized")
                normalized_values.append(normalized)
                search_parts.extend(normalized_entity_text(normalized))

            for merged in record.get("merged_values") or []:
                if not isinstance(merged, dict):
                    continue
                label = clean_text(
                    merged.get("header")
                    or merged.get("label")
                    or "병합값"
                )
                value = clean_text(merged.get("value"))
                if value:
                    lines.append(f"{label}: {value}")
                    search_parts.extend([label, value])

            if not lines:
                continue
            if table_title:
                lines.insert(0, f"표 제목: {table_title}")

            result.append(
                TablePart(
                    body_text="\n".join(lines),
                    body_search_text=unique_join(search_parts),
                    table_index=table.get("table_index"),
                    record_index=record.get("record_index", fallback_index),
                    row_index=record.get("row_index"),
                    row_kind=record.get("row_kind") or "data",
                    entities=collect_entities(normalized_values),
                    object_path=list(structured.get("object_path") or []),
                    strategy="row_record",
                )
            )
        return result

    def _chunk_fallback(self, table: dict[str, Any]) -> list[TablePart]:
        cells = table.get("cells") or []
        if not cells:
            return []

        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            rows.setdefault(int(cell.get("row", 0)), []).append(cell)

        # Tiny/one-cell layout table becomes one text block.
        if len(rows) <= 1 or table.get("row_count") == 1 or table.get("col_count") == 1:
            texts = [clean_text(c.get("text")) for c in cells]
            texts = [t for t in texts if t]
            if not texts:
                return []
            return [
                TablePart(
                    body_text="\n".join(texts),
                    body_search_text=unique_join(
                        c.get("search_text") or c.get("text") for c in cells
                    ),
                    table_index=table.get("table_index"),
                    record_index=None,
                    row_index=None,
                    row_kind="layout_text",
                    object_path=list((table.get("structured_table") or {}).get("object_path") or []),
                    strategy="table_fallback_whole",
                )
            ]

        result: list[TablePart] = []
        for record_index, row_index in enumerate(sorted(rows)):
            row_cells = sorted(rows[row_index], key=lambda c: int(c.get("col", 0)))
            values = [clean_text(c.get("text")) for c in row_cells]
            values = [v for v in values if v]
            if not values:
                continue
            result.append(
                TablePart(
                    body_text=" | ".join(values),
                    body_search_text=unique_join(
                        c.get("search_text") or c.get("text") for c in row_cells
                    ),
                    table_index=table.get("table_index"),
                    record_index=record_index,
                    row_index=row_index,
                    row_kind="fallback_row",
                    strategy="table_fallback_row",
                )
            )
        return result
