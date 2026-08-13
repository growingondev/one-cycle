#!/usr/bin/env python3
"""Structure 결과의 값 타입 정규화 및 검증.

목적
----
- Structure가 만든 제목/문단/표 구조는 변경하지 않습니다.
- 원본 문자열을 덮어쓰지 않고 검색용 문자열과 타입 정보를 추가합니다.
- 금액, 날짜·시간, 면적, 전화번호, 백분율을 보수적으로 추출합니다.
- U+FFFD(�), 사설 영역 문자(PUA), 빈 값 등 후속 검토 대상을 보고서로 만듭니다.

기본 출력
---------
입력 파일과 같은 폴더에 아래 두 파일을 생성합니다.

- step4-1_value_normalized.json
- step4-2_value_validation.json

실행
----
    python -m structure.value_normalizer

또는
    python structure/value_normalizer.py

명령행 지정
-----------
    python -m structure.value_normalizer ^
      --input outputs/announcement_001/03_structured/hwp/step3-3_structured_tables.json
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    from tkinter import Tk, filedialog, messagebox
except ImportError:  # GUI가 없는 서버 환경
    Tk = None
    filedialog = None
    messagebox = None


OUTPUT_FILENAME = "step4-1_value_normalized.json"
REPORT_FILENAME = "step4-2_value_validation.json"

MIDDLE_DOTS_RE = re.compile(r"[․·ㆍ･]")
WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
LINE_SPACE_RE = re.compile(r"[ \t]*\n[ \t]*")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
REPLACEMENT_CHAR = "\ufffd"

PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+82[-\s]?)?"
    r"(?:0\d{1,2}|1[5-8]\d{2})"
    r"[-\s)]?\d{3,4}[-\s]?\d{4}"
    r"(?!\d)"
)

AREA_RE = re.compile(
    r"(?<![\d.])"
    r"(?P<value>\d+(?:\.\d+)?)"
    r"\s*(?P<unit>㎡|m²|m2|제곱미터)"
)

PERCENT_RE = re.compile(
    r"(?<![\d.])(?P<value>\d+(?:\.\d+)?)\s*(?:%|％|퍼센트)"
)

FULL_DATE_RE = re.compile(
    r"(?<!\d)"
    r"(?P<year>\d{4})\s*[./년-]\s*"
    r"(?P<month>\d{1,2})\s*[./월-]\s*"
    r"(?P<day>\d{1,2})\s*(?:일|[.]|/)?"
)

SHORT_DATE_RE = re.compile(
    r"(?<!\d)"
    r"[‘'`]?"
    r"(?P<year>\d{2})\s*[./-]\s*"
    r"(?P<month>\d{1,2})\s*[./-]\s*"
    r"(?P<day>\d{1,2})\s*[.]?"
)

MONTH_PRECISION_RE = re.compile(
    r"(?<!\d)"
    r"(?P<year>\d{4})\s*년\s*"
    r"(?P<month>\d{1,2})\s*월\s*"
    r"(?P<position>초|중|말)"
)

TIME_RE = re.compile(
    r"(?<!\d)"
    r"(?P<hour>[01]?\d|2[0-3])\s*:\s*"
    r"(?P<minute>[0-5]\d)"
    r"(?::\s*(?P<second>[0-5]\d))?"
)

# 숫자 + 한국어 금액 단위. 복합 표현도 연속 토큰으로 처리합니다.
MONEY_TOKEN_RE = re.compile(
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>억원|억|천만원|백만원|십만원|만원|천원|원)"
)

MONEY_MULTIPLIER = {
    "억원": 100_000_000,
    "억": 100_000_000,
    "천만원": 10_000_000,
    "백만원": 1_000_000,
    "십만원": 100_000,
    "만원": 10_000,
    "천원": 1_000,
    "원": 1,
}

DATE_CONTEXT_WORDS = (
    "일정", "기간", "접수", "신청", "계약", "납부", "발표",
    "입주", "동호지정", "선택 가능", "시기", "기한",
)
MONEY_CONTEXT_WORDS = (
    "금액", "가격", "계약금", "잔금", "융자금", "납부",
    "비용", "대금", "세액", "공급가",
)
AREA_CONTEXT_WORDS = (
    "면적", "전용", "공용", "주거", "대지", "주차장",
)


@dataclass
class NormalizationStats:
    text_field_count: int = 0
    search_text_added_count: int = 0
    normalized_value_count: int = 0
    entity_counts: Counter[str] = field(default_factory=Counter)
    replacement_character_count: int = 0
    pua_occurrence_count: int = 0
    pua_affected_field_count: int = 0
    pua_unique_texts: set[str] = field(default_factory=set)
    pua_unique_codepoints: set[str] = field(default_factory=set)
    warning_count: int = 0


@dataclass
class NormalizationContext:
    stats: NormalizationStats = field(default_factory=NormalizationStats)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    _reported_problem_signatures: set[tuple[str, str]] = field(
        default_factory=set,
        repr=False,
    )

    def warn(
        self,
        code: str,
        message: str,
        *,
        path: Iterable[Any],
        raw_value: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        warning: dict[str, Any] = {
            "stage": "value_normalizer",
            "code": code,
            "message": message,
            "path": [str(part) for part in path],
        }
        if raw_value is not None:
            warning["raw_value"] = raw_value
        if details:
            warning["details"] = details
        self.warnings.append(warning)
        self.stats.warning_count += 1


def load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()

    if not target.is_file():
        raise FileNotFoundError(f"입력 JSON을 찾을 수 없습니다: {target}")

    try:
        with target.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {target} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(data, dict):
        raise ValueError("JSON 최상위 값은 객체(dict)여야 합니다.")

    return data


def save_json(data: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    return target


def normalize_search_text(value: Any) -> str:
    """원문을 보존하면서 검색·임베딩 입력에 사용할 문자열을 만듭니다."""

    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(REPLACEMENT_CHAR, " ")
    text = "".join(
        " "
        if is_private_use_character(character)
        else character
        for character in text
    )
    text = MIDDLE_DOTS_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    text = LINE_SPACE_RE.sub("\n", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def is_private_use_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0xE000 <= codepoint <= 0xF8FF
        or 0xF0000 <= codepoint <= 0xFFFFD
        or 0x100000 <= codepoint <= 0x10FFFD
    )


def private_use_codepoints(text: str) -> list[str]:
    return [
        f"U+{ord(character):04X}"
        for character in text
        if is_private_use_character(character)
    ]


def safe_number(value: str) -> int | float:
    cleaned = value.replace(",", "")
    number = float(cleaned)
    return int(number) if number.is_integer() else number


def valid_date(year: int, month: int, day: int) -> bool:
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return False

    days_by_month = {
        1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
        7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
    }
    return day <= days_by_month[month]


def extract_money_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    for match in MONEY_TOKEN_RE.finditer(text):
        number = safe_number(match.group("number"))
        unit = match.group("unit")
        won_value = int(number * MONEY_MULTIPLIER[unit])

        entities.append({
            "type": "money",
            "raw": match.group(0),
            "numeric_value": number,
            "unit": unit,
            "won_value": won_value,
            "start": match.start(),
            "end": match.end(),
        })

    return entities


def extract_date_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    for match in FULL_DATE_RE.finditer(text):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))

        if not valid_date(year, month, day):
            continue

        entities.append({
            "type": "date",
            "raw": match.group(0),
            "normalized_value": f"{year:04d}-{month:02d}-{day:02d}",
            "precision": "day",
            "century_inferred": False,
            "start": match.start(),
            "end": match.end(),
        })
        occupied.append((match.start(), match.end()))

    for match in SHORT_DATE_RE.finditer(text):
        if any(
            match.start() < end and start < match.end()
            for start, end in occupied
        ):
            continue

        short_year = int(match.group("year"))
        year = 2000 + short_year
        month = int(match.group("month"))
        day = int(match.group("day"))

        if not valid_date(year, month, day):
            continue

        entities.append({
            "type": "date",
            "raw": match.group(0),
            "normalized_value": f"{year:04d}-{month:02d}-{day:02d}",
            "precision": "day",
            "century_inferred": True,
            "start": match.start(),
            "end": match.end(),
        })

    for match in MONTH_PRECISION_RE.finditer(text):
        year = int(match.group("year"))
        month = int(match.group("month"))
        position = match.group("position")

        if not 1 <= month <= 12:
            continue

        precision_map = {
            "초": "month_start",
            "중": "month_middle",
            "말": "month_end",
        }

        entities.append({
            "type": "date",
            "raw": match.group(0),
            "normalized_value": f"{year:04d}-{month:02d}",
            "precision": precision_map[position],
            "century_inferred": False,
            "start": match.start(),
            "end": match.end(),
        })

    entities.sort(key=lambda item: (item["start"], item["end"]))
    return entities


def extract_time_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    for match in TIME_RE.finditer(text):
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        second_text = match.group("second")

        normalized = f"{hour:02d}:{minute:02d}"
        precision = "minute"

        if second_text is not None:
            normalized += f":{int(second_text):02d}"
            precision = "second"

        entities.append({
            "type": "time",
            "raw": match.group(0),
            "normalized_value": normalized,
            "precision": precision,
            "start": match.start(),
            "end": match.end(),
        })

    return entities


def extract_area_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    for match in AREA_RE.finditer(text):
        entities.append({
            "type": "area",
            "raw": match.group(0),
            "numeric_value": safe_number(match.group("value")),
            "unit": "㎡",
            "start": match.start(),
            "end": match.end(),
        })

    return entities


def extract_phone_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    for match in PHONE_RE.finditer(text):
        raw = match.group(0).strip()
        digits = re.sub(r"\D", "", raw)

        if raw.startswith("+82") and digits.startswith("82"):
            digits = "0" + digits[2:]

        entities.append({
            "type": "phone",
            "raw": raw,
            "normalized_value": digits,
            "start": match.start(),
            "end": match.end(),
        })

    return entities


def extract_percentage_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []

    for match in PERCENT_RE.finditer(text):
        entities.append({
            "type": "percentage",
            "raw": match.group(0),
            "numeric_value": safe_number(match.group("value")),
            "unit": "%",
            "start": match.start(),
            "end": match.end(),
        })

    return entities


def header_context_text(header_path: Any) -> str:
    if isinstance(header_path, list):
        return " ".join(str(value) for value in header_path)
    return str(header_path or "")


def choose_primary_type(
    entities: list[dict[str, Any]],
    *,
    context_text: str,
    raw_text: str,
) -> str | None:
    entity_types = {entity["type"] for entity in entities}

    if not entity_types:
        return None
    if len(entity_types) == 1:
        return next(iter(entity_types))

    context = normalize_search_text(context_text)

    if any(word in context for word in MONEY_CONTEXT_WORDS) and "money" in entity_types:
        return "money"
    if any(word in context for word in DATE_CONTEXT_WORDS) and "date" in entity_types:
        return "date"
    if any(word in context for word in AREA_CONTEXT_WORDS) and "area" in entity_types:
        return "area"
    if "phone" in entity_types and len(raw_text) <= 30:
        return "phone"

    return "mixed"


def extract_context_inferred_entities(
    raw_text: str,
    *,
    context_text: str,
    existing_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """헤더에만 단위가 있고 셀 값은 숫자만인 경우를 보완합니다.

    예:
        header: "주거전용(㎡)", value: "59.8421"
        header: "합계 (단위:천원)", value: "4,269"

    단위가 명확하게 기록된 경우에만 추론합니다.
    """

    compact = normalize_search_text(raw_text)
    context = normalize_search_text(context_text)
    numeric_match = re.fullmatch(
        r"[+-]?\d[\d,]*(?:\.\d+)?",
        compact,
    )
    if not numeric_match:
        return []

    number = safe_number(compact)
    existing_types = {entity["type"] for entity in existing_entities}
    inferred: list[dict[str, Any]] = []

    if (
        "area" not in existing_types
        and (
            "㎡" in context_text
            or "m²" in context_text
            or "제곱미터" in context
        )
    ):
        inferred.append({
            "type": "area",
            "raw": raw_text,
            "numeric_value": number,
            "unit": "㎡",
            "start": 0,
            "end": len(raw_text),
            "inferred_from_context": True,
            "context": context_text,
        })

    money_unit: str | None = None
    if re.search(r"(?:단위\s*[:：]?\s*)?천원", context):
        money_unit = "천원"
    elif re.search(r"(?:단위\s*[:：]?\s*)?만원", context):
        money_unit = "만원"
    elif re.search(r"(?:단위\s*[:：]?\s*)?백만원", context):
        money_unit = "백만원"
    elif re.search(r"(?:단위\s*[:：]?\s*)?억원?", context):
        money_unit = "억원"
    elif re.search(r"(?:단위\s*[:：]?\s*)?원", context):
        money_unit = "원"

    if "money" not in existing_types and money_unit:
        inferred.append({
            "type": "money",
            "raw": raw_text,
            "numeric_value": number,
            "unit": money_unit,
            "won_value": int(number * MONEY_MULTIPLIER[money_unit]),
            "start": 0,
            "end": len(raw_text),
            "inferred_from_context": True,
            "context": context_text,
        })

    if (
        "percentage" not in existing_types
        and ("%" in context_text or "퍼센트" in context)
    ):
        inferred.append({
            "type": "percentage",
            "raw": raw_text,
            "numeric_value": number,
            "unit": "%",
            "start": 0,
            "end": len(raw_text),
            "inferred_from_context": True,
            "context": context_text,
        })

    return inferred


def normalize_typed_value(
    raw_value: Any,
    *,
    context_text: str = "",
) -> dict[str, Any]:
    """값 하나를 분석하되 원본 의미를 추측해서 바꾸지 않습니다."""

    raw_text = "" if raw_value is None else str(raw_value)
    search_text = normalize_search_text(raw_text)

    entities: list[dict[str, Any]] = []
    entities.extend(extract_money_entities(raw_text))
    entities.extend(extract_date_entities(raw_text))
    entities.extend(extract_time_entities(raw_text))
    entities.extend(extract_area_entities(raw_text))
    entities.extend(extract_phone_entities(raw_text))
    entities.extend(extract_percentage_entities(raw_text))
    entities.extend(
        extract_context_inferred_entities(
            raw_text,
            context_text=context_text,
            existing_entities=entities,
        )
    )
    entities.sort(key=lambda item: (item["start"], item["end"], item["type"]))

    primary_type = choose_primary_type(
        entities,
        context_text=context_text,
        raw_text=raw_text,
    )

    return {
        "raw_value": raw_text,
        "search_text": search_text,
        "primary_type": primary_type,
        "entities": entities,
    }


def inspect_problem_characters(
    text: str,
    *,
    path: Iterable[Any],
    context: NormalizationContext,
) -> None:
    replacement_count = text.count(REPLACEMENT_CHAR)
    if replacement_count:
        context.stats.replacement_character_count += replacement_count
        context.warn(
            "REPLACEMENT_CHARACTER_FOUND",
            "문자 복원에 실패한 대체 문자(�)가 포함되어 있습니다.",
            path=path,
            raw_value=text,
            details={"count": replacement_count},
        )

    codepoints = private_use_codepoints(text)
    if codepoints:
        unique_codepoints = sorted(set(codepoints))
        context.stats.pua_occurrence_count += len(codepoints)
        context.stats.pua_affected_field_count += 1
        context.stats.pua_unique_texts.add(text)
        context.stats.pua_unique_codepoints.update(unique_codepoints)

        # 구조화 과정에서 같은 원문이 text/value 등 여러 필드에 복제될 수
        # 있으므로 동일 문자열과 동일 코드포인트 조합의 경고는 한 번만 남깁니다.
        signature = (text, "|".join(unique_codepoints))
        if signature not in context._reported_problem_signatures:
            context._reported_problem_signatures.add(signature)
            context.warn(
                "PRIVATE_USE_CHARACTER_FOUND",
                "검증되지 않은 사설 영역 문자가 포함되어 있습니다.",
                path=path,
                raw_value=text,
                details={
                    "occurrence_count_in_text": len(codepoints),
                    "codepoints": unique_codepoints,
                },
            )


def add_search_text(
    container: dict[str, Any],
    *,
    source_key: str,
    target_key: str,
    path: Iterable[Any],
    context: NormalizationContext,
) -> None:
    value = container.get(source_key)
    if not isinstance(value, str):
        return

    context.stats.text_field_count += 1
    inspect_problem_characters(
        value,
        path=[*path, source_key],
        context=context,
    )

    search_text = normalize_search_text(value)
    container[target_key] = search_text
    context.stats.search_text_added_count += 1


def normalize_structured_table(
    table: dict[str, Any],
    *,
    path: list[Any],
    context: NormalizationContext,
) -> None:
    structured = table.get("structured_table")
    if not isinstance(structured, dict):
        return

    records = structured.get("records")
    if not isinstance(records, list):
        return

    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            continue

        record_path = [
            *path,
            "structured_table",
            "records",
            record_index,
        ]

        # key_value 형태
        if isinstance(record.get("key"), str):
            add_search_text(
                record,
                source_key="key",
                target_key="key_search_text",
                path=record_path,
                context=context,
            )

        if "value" in record:
            value_context = str(record.get("key") or "")
            normalized = normalize_typed_value(
                record.get("value"),
                context_text=value_context,
            )
            record["value_normalized"] = normalized
            context.stats.normalized_value_count += 1
            inspect_problem_characters(
                normalized["raw_value"],
                path=[*record_path, "value"],
                context=context,
            )
            for entity in normalized["entities"]:
                context.stats.entity_counts[entity["type"]] += 1

        # row_records 형태
        values = record.get("values")
        if isinstance(values, list):
            for value_index, value_item in enumerate(values):
                if not isinstance(value_item, dict) or "value" not in value_item:
                    continue

                value_path = [
                    *record_path,
                    "values",
                    value_index,
                ]
                header_text = header_context_text(
                    value_item.get("header_path")
                )
                normalized = normalize_typed_value(
                    value_item.get("value"),
                    context_text=header_text,
                )
                value_item["normalized"] = normalized
                context.stats.normalized_value_count += 1
                inspect_problem_characters(
                    normalized["raw_value"],
                    path=[*value_path, "value"],
                    context=context,
                )
                for entity in normalized["entities"]:
                    context.stats.entity_counts[entity["type"]] += 1

        # merged_values도 검색 대상에 포함
        merged_values = record.get("merged_values")
        if isinstance(merged_values, list):
            for merged_index, merged in enumerate(merged_values):
                if not isinstance(merged, dict) or "value" not in merged:
                    continue

                merged_path = [
                    *record_path,
                    "merged_values",
                    merged_index,
                ]
                normalized = normalize_typed_value(
                    merged.get("value"),
                    context_text=header_context_text(
                        merged.get("header_path")
                    ),
                )
                merged["normalized"] = normalized
                context.stats.normalized_value_count += 1
                inspect_problem_characters(
                    normalized["raw_value"],
                    path=[*merged_path, "value"],
                    context=context,
                )
                for entity in normalized["entities"]:
                    context.stats.entity_counts[entity["type"]] += 1


def normalize_document_node(
    value: Any,
    *,
    path: list[Any],
    context: NormalizationContext,
    seen: set[int],
) -> None:
    """문서 전체를 재귀 순회하면서 원본 필드 옆에 정규화 필드를 추가합니다."""

    if isinstance(value, dict):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)

        node_type = value.get("type")

        if isinstance(value.get("title"), str):
            add_search_text(
                value,
                source_key="title",
                target_key="search_title",
                path=path,
                context=context,
            )

        if node_type in {"paragraph", "text"} and isinstance(
            value.get("text"), str
        ):
            add_search_text(
                value,
                source_key="text",
                target_key="search_text",
                path=path,
                context=context,
            )

        if node_type == "table":
            # raw cell의 text도 검색용 표현을 추가하지만 원본은 유지합니다.
            cells = value.get("cells")
            if isinstance(cells, list):
                for cell_index, cell in enumerate(cells):
                    if not isinstance(cell, dict):
                        continue
                    if isinstance(cell.get("text"), str):
                        add_search_text(
                            cell,
                            source_key="text",
                            target_key="search_text",
                            path=[*path, "cells", cell_index],
                            context=context,
                        )

            normalize_structured_table(
                value,
                path=path,
                context=context,
            )

        for key, child in list(value.items()):
            # 방금 추가한 정규화 결과를 다시 순회하지 않습니다.
            if key in {
                "search_text",
                "search_title",
                "key_search_text",
                "normalized",
                "value_normalized",
                "value_normalization",
            }:
                continue
            if isinstance(child, (dict, list)):
                normalize_document_node(
                    child,
                    path=[*path, key],
                    context=context,
                    seen=seen,
                )

    elif isinstance(value, list):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)

        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                normalize_document_node(
                    child,
                    path=[*path, index],
                    context=context,
                    seen=seen,
                )


def count_sections(sections: Any) -> int:
    if not isinstance(sections, list):
        return 0

    total = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        total += 1
        total += count_sections(section.get("children"))
    return total


def iter_tables(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("type") == "table":
            yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from iter_tables(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                yield from iter_tables(child)


def validate_input_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    stage = document.get("stage")
    if stage not in {"structured", "value_normalized"}:
        errors.append(
            "입력 stage가 structured가 아닙니다. "
            f"현재 값: {stage!r}"
        )

    if not isinstance(document.get("sections"), list):
        errors.append("sections 배열이 없습니다.")

    if "document" not in document or not isinstance(
        document.get("document"), dict
    ):
        errors.append("document 메타데이터가 없습니다.")

    return errors




def portable_report_path(path: Path) -> str:
    """검증 JSON에 OS 종속 절대경로 대신 이식 가능한 경로를 기록합니다."""
    resolved = path.expanduser().resolve()
    parts = resolved.parts

    for marker in ("outputs", "output"):
        if marker in parts:
            index = parts.index(marker)
            return Path(*parts[index:]).as_posix()

    # 표준 outputs 경로가 아닌 단독 실행도 사용자 홈 경로를 노출하지 않습니다.
    return resolved.name


def build_validation_report(
    result: dict[str, Any],
    *,
    input_path: Path,
    output_path: Path,
    context: NormalizationContext,
) -> dict[str, Any]:
    tables = list(iter_tables(result))
    structured_count = 0
    skipped_count = 0
    unresolved_count = 0

    for table in tables:
        status = (
            (table.get("structured_table") or {}).get("status")
            if isinstance(table.get("structured_table"), dict)
            else None
        )
        if status == "structured":
            structured_count += 1
        elif status == "skipped":
            skipped_count += 1
        else:
            unresolved_count += 1

    status = "pass"
    if context.warnings:
        status = "warning"

    return {
        "schema_version": "1.0",
        "stage": "value_validation",
        "status": status,
        "input_file": portable_report_path(input_path),
        "output_file": portable_report_path(output_path),
        "summary": {
            "section_count": count_sections(result.get("sections")),
            "table_count": len(tables),
            "structured_table_count": structured_count,
            "skipped_table_count": skipped_count,
            "unresolved_table_count": unresolved_count,
            "text_field_count": context.stats.text_field_count,
            "search_text_added_count": (
                context.stats.search_text_added_count
            ),
            "normalized_value_count": (
                context.stats.normalized_value_count
            ),
            "entity_counts": dict(
                sorted(context.stats.entity_counts.items())
            ),
            "replacement_character_count": (
                context.stats.replacement_character_count
            ),
            # 기존 필드는 전체 출현 횟수 의미로 유지합니다.
            "private_use_character_count": (
                context.stats.pua_occurrence_count
            ),
            "private_use_occurrence_count": (
                context.stats.pua_occurrence_count
            ),
            "private_use_affected_field_count": (
                context.stats.pua_affected_field_count
            ),
            "private_use_unique_text_count": len(
                context.stats.pua_unique_texts
            ),
            "private_use_unique_character_count": len(
                context.stats.pua_unique_codepoints
            ),
            "private_use_unique_codepoints": sorted(
                context.stats.pua_unique_codepoints
            ),
            "warning_count": context.stats.warning_count,
        },
        "warnings": context.warnings,
        "notes": [
            "원본 title/text/value는 변경하지 않았습니다.",
            "search_text 계열 필드는 검색 및 임베딩 입력용입니다.",
            "금액은 원 단위 won_value를 함께 기록합니다.",
            "두 자리 연도는 2000년대로 보완하고 century_inferred=true로 표시합니다.",
            "� 및 PUA 문자는 임의 복원하지 않고 검색용 문자열에서만 제외합니다.",
        ],
    }


def normalize_values(
    source: dict[str, Any],
    *,
    input_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = validate_input_document(source)
    if errors:
        raise ValueError("\n".join(errors))

    result = copy.deepcopy(source)
    context = NormalizationContext()

    normalize_document_node(
        result,
        path=[],
        context=context,
        seen=set(),
    )

    result["schema_version"] = "1.2"
    result["stage"] = "value_normalized"
    result["value_normalization"] = {
        "version": "value-normalizer-v1",
        "policy": {
            "raw_value_preserved": True,
            "search_text_added": True,
            "typed_entities_added": True,
            "replacement_characters_reconstructed": False,
            "private_use_characters_reconstructed": False,
        },
        "summary": {
            "normalized_value_count": (
                context.stats.normalized_value_count
            ),
            "entity_counts": dict(
                sorted(context.stats.entity_counts.items())
            ),
            "warning_count": context.stats.warning_count,
        },
    }

    # 기존 경고를 덮어쓰지 않고 별도 배열로 추가합니다.
    result["value_normalization_warnings"] = copy.deepcopy(
        context.warnings
    )

    report = build_validation_report(
        result,
        input_path=input_path,
        output_path=output_path,
        context=context,
    )
    return result, report


def default_output_paths(input_path: Path) -> tuple[Path, Path]:
    return (
        input_path.parent / OUTPUT_FILENAME,
        input_path.parent / REPORT_FILENAME,
    )


def select_input_json() -> Path | None:
    if Tk is None or filedialog is None:
        return None

    root = Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    selected = filedialog.askopenfilename(
        title="Structure 최종 JSON 선택",
        filetypes=[
            (
                "Structure 최종 JSON",
                "*step3-3_structured_tables.json",
            ),
            ("JSON Files", "*.json"),
            ("All Files", "*.*"),
        ],
    )
    root.destroy()

    return Path(selected).resolve() if selected else None


def select_output_directory(initial_dir: Path) -> Path | None:
    if Tk is None or filedialog is None:
        return None

    root = Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    selected = filedialog.askdirectory(
        title="값 정규화 결과 저장 폴더 선택",
        initialdir=str(initial_dir),
    )
    root.destroy()

    return Path(selected).resolve() if selected else None


def show_message(title: str, message: str, *, error: bool = False) -> None:
    if Tk is None or messagebox is None:
        return

    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)
        root.destroy()
    except Exception:
        pass


def process(
    input_path: str | Path,
    output_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> tuple[Path, Path]:
    input_file = Path(input_path).expanduser().resolve()

    default_output, default_report = default_output_paths(input_file)
    output_file = (
        Path(output_path).expanduser().resolve()
        if output_path
        else default_output
    )
    report_file = (
        Path(report_path).expanduser().resolve()
        if report_path
        else default_report
    )

    source = load_json(input_file)
    result, report = normalize_values(
        source,
        input_path=input_file,
        output_path=output_file,
    )

    save_json(result, output_file)
    save_json(report, report_file)

    return output_file, report_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Structure 결과의 값 타입 정규화 및 검증"
    )
    parser.add_argument(
        "--input",
        help=(
            "step3-3_structured_tables.json 경로. "
            "생략하면 파일 선택 창이 열립니다."
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "값 정규화 JSON 저장 경로. 생략하면 입력 파일과 같은 "
            f"폴더에 {OUTPUT_FILENAME}으로 저장합니다."
        ),
    )
    parser.add_argument(
        "--report",
        help=(
            "검증 보고서 저장 경로. 생략하면 입력 파일과 같은 "
            f"폴더에 {REPORT_FILENAME}으로 저장합니다."
        ),
    )
    parser.add_argument(
        "--choose-output",
        action="store_true",
        help="출력 폴더도 마우스로 선택합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    input_path = (
        Path(args.input).expanduser().resolve()
        if args.input
        else select_input_json()
    )

    if input_path is None:
        print("[안내] 입력 파일이 선택되지 않았습니다.")
        return 0

    output_path: Path | None = (
        Path(args.output).expanduser().resolve()
        if args.output
        else None
    )
    report_path: Path | None = (
        Path(args.report).expanduser().resolve()
        if args.report
        else None
    )

    if args.choose_output:
        selected_dir = select_output_directory(input_path.parent)
        if selected_dir is None:
            print("[안내] 출력 폴더가 선택되지 않았습니다.")
            return 0
        output_path = selected_dir / OUTPUT_FILENAME
        report_path = selected_dir / REPORT_FILENAME

    try:
        output_file, report_file = process(
            input_path=input_path,
            output_path=output_path,
            report_path=report_path,
        )
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        print()
        print("=" * 72)
        print("[ERROR] 값 정규화 실패")
        print("=" * 72)
        print(message)
        show_message("값 정규화 실패", message, error=True)
        return 1

    print()
    print("=" * 72)
    print("값 타입 정규화 및 검증 완료")
    print("=" * 72)
    print(f"입력: {input_path}")
    print(f"결과: {output_file}")
    print(f"검증: {report_file}")

    show_message(
        "값 정규화 완료",
        "값 타입 정규화 및 검증이 완료되었습니다.\n\n"
        f"결과:\n{output_file}\n\n"
        f"검증 보고서:\n{report_file}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
