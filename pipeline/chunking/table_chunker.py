from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from .config import ChunkingConfig
from .text_builder import clean_text, flatten_search_text, normalized_entity_text, unique_join
from .tokenizer import TokenCounter

_NUMERIC_RE = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")
_NUMERIC_PREFIX_RE = re.compile(r"^\s*([+-]?\d[\d,]*(?:\.\d+)?)")
_EXPLICIT_UNIT_RE = re.compile(r"단위\s*[:：]\s*(천원|만원|억원|원|㎡|m²|m2|%)", re.I)
_GROUP_UNIT_RE = re.compile(r"\(\s*(천원|만원|억원|원|㎡|m²|m2)\s*\)", re.I)
_RATIO_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_VALUE_UNIT_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?\s*(천원|만원|억원|원|㎡|m²|m2|%)", re.I)

_MONEY_HINT_RE = re.compile(
    r"(가격|금액|계약금|잔금|보증금|임대료|비용|공사비|분양가|대금|납부금|부담금|융자금)",
    re.I,
)
_AREA_HINT_RE = re.compile(
    r"(면적|주거전용|주거공용|계약면적|대지면적|공유대지|기타공용|지하주차장)",
    re.I,
)
_COUNT_HINT_RE = re.compile(
    r"(세대수|모집수|모집\s*수|모집호수|건설호수|공급호수|호수|세대|동수|개수|인원)",
    re.I,
)
_DURATION_HINT_RE = re.compile(
    r"(거주기간|거주\s*기간|최대\s*거주|기간|개월|년)",
    re.I,
)
_IDENTIFIER_HINT_RE = re.compile(
    r"(주택형|타입|세부평형|품목번호|품목\s*번호|번호|형별|블록|동호|동·호)",
    re.I,
)

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
    part_index: int = 1
    part_count: int = 1
    overlap_applied: bool = False

class TableChunker:
    def __init__(self, config: ChunkingConfig, token_counter: TokenCounter) -> None:
        self.config = config
        self.tokens = token_counter

    def chunk(self, table, *, inherited_unit=None, target_tokens=None, max_tokens=None) -> list[TablePart]:
        structured = table.get("structured_table") or {}
        status, layout = structured.get("status"), structured.get("layout")
        if status == "structured" and layout == "key_value":
            parts = self._chunk_key_value(table, structured, inherited_unit)
        elif status == "structured" and layout == "row_records":
            parts = self._chunk_row_records(table, structured, inherited_unit)
        else:
            parts = self._chunk_fallback(table)
        return self._enforce_limits(
            parts,
            target_tokens=min(target_tokens or self.config.target_tokens, max_tokens or self.config.max_tokens),
            max_tokens=max_tokens or self.config.max_tokens,
        )

    def _chunk_key_value(self, table, structured, inherited_unit) -> list[TablePart]:
        records = structured.get("records") or []
        common = self._common_unit(structured, inherited_unit)
        rows = []
        for record in records:
            key, raw = clean_text(record.get("key")), clean_text(record.get("value"))
            if not key and not raw:
                continue
            unit = self._resolve_unit(raw, [key], record.get("value_normalized"), common, inherited_unit)
            value = self._format_value(raw, unit)
            entities = self._entities(record.get("value_normalized"), raw, unit)
            rows.append((
                f"{key}: {value}" if key else value,
                unique_join([record.get("key_search_text") or key, value, *self._entity_terms(entities)]),
                record, entities
            ))
        whole = "\n".join(x[0] for x in rows)
        if rows and self.tokens.count(whole) <= self.config.small_key_value_table_tokens:
            entities = self._dedupe([e for _, _, _, es in rows for e in es])
            return [TablePart(
                whole, unique_join(x[1] for x in rows), table.get("table_index"),
                None, None, "key_value_group", entities,
                list(structured.get("object_path") or []), "key_value_group"
            )]
        return [
            TablePart(
                body, search, table.get("table_index"), rec.get("record_index", i),
                rec.get("row_index"), "key_value", entities,
                list(structured.get("object_path") or []), "key_value_record"
            )
            for i, (body, search, rec, entities) in enumerate(rows)
        ]

    def _chunk_row_records(self, table, structured, inherited_unit) -> list[TablePart]:
        result = []
        title = clean_text(structured.get("table_title"))
        common = self._common_unit(structured, inherited_unit)
        for i, record in enumerate(structured.get("records") or []):
            lines, search, entities = [], [title], []
            for item in record.get("values") or []:
                headers = [clean_text(x) for x in item.get("header_path") or [] if clean_text(x)]
                label = " > ".join(headers) or f"열 {item.get('column', '')}".strip()
                raw = clean_text(item.get("value"))
                if not raw and item.get("status") in {"empty", "missing"}:
                    continue
                unit = self._resolve_unit(raw, headers, item.get("normalized"), common, inherited_unit)
                value = self._format_value(raw, unit)
                lines.append(f"{label}: {value}")
                resolved = self._entities(item.get("normalized"), raw, unit)
                entities.extend(resolved)
                search.extend([*headers, value, *self._entity_terms(resolved)])
            for merged in record.get("merged_values") or []:
                if isinstance(merged, dict):
                    label = clean_text(merged.get("header") or merged.get("label") or "병합값")
                    value = clean_text(merged.get("value"))
                    if value:
                        lines.append(f"{label}: {value}")
                        search.extend([label, value])
            if not lines:
                continue
            if title:
                lines.insert(0, f"표 제목: {title}")
            result.append(TablePart(
                "\n".join(lines), unique_join(search), table.get("table_index"),
                record.get("record_index", i), record.get("row_index"),
                record.get("row_kind") or "data", self._dedupe(entities),
                list(structured.get("object_path") or []), "row_record"
            ))
        return result

    def _chunk_fallback(self, table) -> list[TablePart]:
        cells = [c for c in table.get("cells") or [] if isinstance(c, dict)]
        if not cells:
            return []
        rows = {}
        for cell in cells:
            rows.setdefault(int(cell.get("row", 0)), []).append(cell)
        if len(rows) <= 1 or table.get("row_count") == 1 or table.get("col_count") == 1:
            texts = [clean_text(c.get("text")) for c in cells if clean_text(c.get("text"))]
            if not texts:
                return []
            return [TablePart(
                "\n".join(texts),
                unique_join(c.get("search_text") or c.get("text") for c in cells),
                table.get("table_index"), None, None, "layout_text", [],
                list((table.get("structured_table") or {}).get("object_path") or []),
                "table_fallback_whole"
            )]
        result = []
        for i, row_index in enumerate(sorted(rows)):
            row_cells = sorted(rows[row_index], key=lambda c: int(c.get("col", 0)))
            values = [clean_text(c.get("text")) for c in row_cells if clean_text(c.get("text"))]
            if values:
                result.append(TablePart(
                    " | ".join(values),
                    unique_join(c.get("search_text") or c.get("text") for c in row_cells),
                    table.get("table_index"), i, row_index, "fallback_row",
                    strategy="table_fallback_row"
                ))
        return result

    def _common_unit(self, structured, inherited):
        texts = [clean_text(structured.get("table_title"))]
        for record in structured.get("records") or []:
            for item in record.get("values") or []:
                texts.extend(clean_text(x) for x in item.get("header_path") or [])
        explicit, groups = [], []
        for text in texts:
            if not text:
                continue
            m = _EXPLICIT_UNIT_RE.search(text)
            if m:
                explicit.append(self._norm_unit(m.group(1)))
            if not _RATIO_RE.search(text):
                m = _GROUP_UNIT_RE.search(text)
                if m:
                    groups.append(self._norm_unit(m.group(1)))
        if explicit:
            return self._mode(explicit)
        if groups:
            return self._mode(groups)
        return inherited

    def _resolve_unit(self, value, headers, normalized, common, inherited):
        if not value:
            return None

        # 1. Unit physically present in the value is always preserved.
        m = _VALUE_UNIT_RE.search(value)
        if m:
            return self._norm_unit(m.group(1))

        semantic = self._header_semantic_kind(headers)

        # 2. Unit supplied by normalization is accepted only when it is
        # compatible with the field meaning. This prevents an inferred "㎡"
        # from leaking into 모집호수/건설호수/거주기간.
        unit = self._normalized_unit(normalized, value, semantic)
        if unit:
            return unit

        # 3. Exact header declaration is strong evidence.
        #    Example: "월 임대료(원)", "면적(㎡)".
        for header in reversed(headers):
            m = _EXPLICIT_UNIT_RE.search(header)
            if m:
                return self._norm_unit(m.group(1))

        for header in headers:
            if _RATIO_RE.search(header):
                continue
            m = _GROUP_UNIT_RE.search(header)
            if m:
                return self._norm_unit(m.group(1))

        # 4. Table-wide / previous-paragraph unit is weak evidence.
        #    Only apply it when the field semantics match the unit family.
        if not self._numeric_prefix(value):
            return None

        candidate = common or inherited
        if not candidate or candidate == "%":
            return None

        candidate = self._norm_unit(candidate)
        if self._unit_allowed_for_semantic(candidate, semantic):
            return candidate

        return None

    def _normalized_unit(self, normalized, value, semantic):
        if not isinstance(normalized, dict):
            return None

        direct = normalized.get("source_unit") or normalized.get("unit")
        if direct:
            unit = self._norm_unit(str(direct))
            if unit == "%" and "%" not in value:
                return None
            if self._unit_allowed_for_semantic(unit, semantic):
                return unit
            return None

        for entity in normalized.get("entities") or []:
            if not isinstance(entity, dict) or not entity.get("unit"):
                continue

            unit = self._norm_unit(str(entity["unit"]))

            if unit == "%" and "%" not in value and entity.get("inferred_from_context"):
                continue

            # Context-inferred units are never allowed to override a
            # count/duration/identifier field.
            if entity.get("inferred_from_context"):
                if not self._unit_allowed_for_semantic(unit, semantic):
                    continue
                return unit

            # Even non-inferred normalized units must be semantically sane
            # when the raw value itself did not contain the unit.
            if self._unit_allowed_for_semantic(unit, semantic):
                return unit

        return None

    @staticmethod
    def _header_semantic_kind(headers):
        text = " > ".join(clean_text(h) for h in headers if clean_text(h))

        # Exclusion classes first so "모집호수" is count even if a parent
        # header elsewhere mentions an area.
        if _IDENTIFIER_HINT_RE.search(text):
            return "identifier"
        if _COUNT_HINT_RE.search(text):
            return "count"
        if _DURATION_HINT_RE.search(text):
            return "duration"
        if _MONEY_HINT_RE.search(text):
            return "money"
        if _AREA_HINT_RE.search(text):
            return "area"
        return "unknown"

    @staticmethod
    def _unit_allowed_for_semantic(unit, semantic):
        unit = TableChunker._norm_unit(str(unit))
        if semantic in {"identifier", "count", "duration"}:
            return False
        if unit in {"원", "천원", "만원", "억원"}:
            return semantic == "money"
        if unit == "㎡":
            return semantic == "area"
        if unit == "%":
            return False
        return False

    def _format_value(self, value, unit):
        if not value or not unit or _VALUE_UNIT_RE.search(value):
            return value
        # 숫자로 시작하는 값이면 첫 숫자 뒤에 단위를 붙인다.
        # 예: "500\n(정액)" -> "500천원\n(정액)"
        match = _NUMERIC_PREFIX_RE.match(value)
        if not match:
            return value
        start, end = match.span(1)
        return value[:start] + value[start:end] + unit + value[end:]

    def _entities(self, normalized, raw, unit):
        entities = []
        if isinstance(normalized, dict):
            for entity in normalized.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                e = copy.deepcopy(entity)
                if (e.get("unit") == "%" and "%" not in raw
                        and e.get("inferred_from_context") and unit and unit != "%"):
                    continue
                entities.append(e)
        number = self._number_prefix(raw)
        if unit and number is not None and not any(self._norm_unit(str(e.get("unit") or "")) == unit for e in entities):
            kind = "money" if unit in {"원","천원","만원","억원"} else "area" if unit == "㎡" else "percentage" if unit == "%" else "number"
            e = {
                "type": kind, "raw": raw, "numeric_value": number, "unit": unit,
                "inferred_from_context": True, "inferred_at_chunking": True,
            }
            if unit in {"원","천원","만원","억원"}:
                e["won_value"] = number * {"원":1,"천원":1000,"만원":10000,"억원":100000000}[unit]
            entities.append(e)
        return self._dedupe(entities)

    @staticmethod
    def _numeric_prefix(value):
        return _NUMERIC_PREFIX_RE.match(clean_text(value) or "") is not None

    @staticmethod
    def _number_prefix(value):
        match = _NUMERIC_PREFIX_RE.match(clean_text(value) or "")
        if not match:
            return None
        n = float(match.group(1).replace(",", ""))
        return int(n) if n.is_integer() else n

    @staticmethod
    def _norm_unit(unit):
        unit = unit.strip()
        return {"m2":"㎡","m²":"㎡"}.get(unit.lower(), unit)

    @staticmethod
    def _mode(values):
        return max(dict.fromkeys(values), key=values.count) if values else None

    @staticmethod
    def _dedupe(entities):
        out, seen = [], set()
        for e in entities:
            key = repr(sorted(e.items(), key=lambda x: x[0]))
            if key not in seen:
                seen.add(key); out.append(e)
        return out

    @staticmethod
    def _entity_terms(entities):
        out = []
        for e in entities:
            for key in ("normalized_value","won_value","numeric_value","unit"):
                if e.get(key) is not None:
                    out.append(str(e[key]))
        return out

    def _enforce_limits(self, parts, *, target_tokens, max_tokens):
        output = []
        for part in parts:
            if self.tokens.count(part.body_text) <= max_tokens:
                output.append(part); continue
            bodies = self._split_text(part.body_text, target_tokens, max_tokens)
            total = len(bodies)
            for i, body in enumerate(bodies, 1):
                clone = copy.deepcopy(part)
                clone.body_text = body
                clone.body_search_text = flatten_search_text(body)
                clone.part_index, clone.part_count, clone.overlap_applied = i, total, False
                clone.strategy = (
                    "table_fallback_split" if clone.strategy == "table_fallback_whole"
                    else clone.strategy + "_split"
                )
                output.append(clone)
        return output

    def _split_text(self, text, target, maximum):
        atomic = []
        for line in [clean_text(x) for x in text.splitlines() if clean_text(x)]:
            atomic.extend([line] if self.tokens.count(line) <= maximum else self._split_words(line, maximum))
        chunks, buffer = [], []
        for item in atomic:
            candidate = "\n".join([*buffer, item]).strip()
            if buffer and self.tokens.count(candidate) > maximum:
                chunks.append("\n".join(buffer).strip()); buffer = [item]
            else:
                buffer.append(item)
                if self.tokens.count(candidate) >= target:
                    chunks.append(candidate); buffer = []
        if buffer:
            tail = "\n".join(buffer).strip()
            if chunks and self.tokens.count(tail) < self.config.min_tokens and self.tokens.count(chunks[-1]+"\n"+tail) <= maximum:
                chunks[-1] += "\n" + tail
            else:
                chunks.append(tail)

        # 마지막 안전장치: 어떤 경로로 들어온 텍스트도 maximum 초과를 허용하지 않는다.
        final_chunks = []
        for chunk in chunks:
            if self.tokens.count(chunk) <= maximum:
                final_chunks.append(chunk)
            else:
                final_chunks.extend(self._split_words(chunk, maximum))
        return [x for x in final_chunks if x]

    def _split_words(self, text, maximum):
        chunks, buffer = [], []
        for word in text.split():
            if self.tokens.count(word) > maximum:
                if buffer:
                    chunks.append(" ".join(buffer)); buffer=[]
                chunks.extend(self._split_chars(word, maximum)); continue
            candidate = " ".join([*buffer, word])
            if buffer and self.tokens.count(candidate) > maximum:
                chunks.append(" ".join(buffer)); buffer=[word]
            else:
                buffer.append(word)
        if buffer:
            chunks.append(" ".join(buffer))
        return chunks or [text]

    def _split_chars(self, token, maximum):
        parts, current = [], ""
        for ch in token:
            if current and self.tokens.count(current + ch) > maximum:
                parts.append(current); current=ch
            else:
                current += ch
        if current:
            parts.append(current)
        return parts
