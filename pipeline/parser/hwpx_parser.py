from __future__ import annotations

import argparse
import re
import zipfile
import unicodedata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import jpype

try:
    from .common import (
        ParseContext,
        build_document_header,
        ensure_jvm,
        java_class_name,
        resolve_jar_path,
        save_json,
        validate_document_path,
    )
except ImportError:
    from common import (  # type: ignore
        ParseContext,
        build_document_header,
        ensure_jvm,
        java_class_name,
        resolve_jar_path,
        save_json,
        validate_document_path,
    )


HWPX_READER_CLASS = "kr.dogfoot.hwpxlib.reader.HWPXReader"
HWPX_TEXT_CLASS_SUFFIX = ".paragraph.T"
HWPX_TABLE_CLASS_SUFFIX = ".Table"
HWPX_COMPOSE_CLASS_SUFFIX = ".paragraph.Compose"


# Parser에서는 PUA/Compose의 의미를 해석하지 않습니다.
# 원본 글리프와 codepoint만 보존하며 숫자 변환은 Normalizer에서 수행합니다.
HANGUL_PUA_NUMBER_MAP: dict[str, str] = {}
HANGUL_COMPOSE_NUMBER_MAP: dict[str, str] = {}



# 필요할 때만 켜는 진단 옵션입니다. 실제 복원 로직과는 독립적입니다.
DEBUG_SPECIAL_CHARACTERS = False


def _is_private_use_char(char: str) -> bool:
    if not char:
        return False

    codepoint = ord(char)
    return (
        0xE000 <= codepoint <= 0xF8FF
        or 0xF0000 <= codepoint <= 0xFFFFD
        or 0x100000 <= codepoint <= 0x10FFFD
    )


def _normalize_group_label(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _replace_pua_numbers(text: str) -> tuple[str, list[dict[str, str]]]:
    """PUA를 변환하지 않고 원문 및 codepoint 기록만 반환합니다."""
    value = str(text or "")
    replacements: list[dict[str, str]] = []

    for char in value:
        codepoint = ord(char)
        if not (
            0xE000 <= codepoint <= 0xF8FF
            or 0xF0000 <= codepoint <= 0xFFFFD
            or 0x100000 <= codepoint <= 0x10FFFD
        ):
            continue

        mapped = HANGUL_PUA_NUMBER_MAP.get(char)
        replacements.append(
            {
                "character": char,
                "codepoint": f"U+{codepoint:05X}",
                "mapped_value": mapped or "",
            }
        )
        if mapped:
            value = value.replace(char, mapped)

    # 원형/괄호 숫자처럼 NFKC로 안전하게 풀리는 문자도 일반 숫자로 통일합니다.
    value = unicodedata.normalize("NFKC", value)
    return value, replacements


def _set_recovered_cell_text(
    cell: dict[str, Any],
    recovered_text: str,
    *,
    raw_text: str,
    method: str,
    prefix: str | None,
    confidence: float,
    pua_replacements: list[dict[str, str]] | None = None,
) -> None:
    cell["raw_text"] = raw_text
    cell["text"] = recovered_text
    cell["number_recovery"] = {
        "recovered": recovered_text != raw_text,
        "method": method,
        "prefix": prefix,
        "confidence": confidence,
    }
    if pua_replacements:
        cell["pua_characters"] = pua_replacements

    paragraphs = cell.get("paragraphs")
    if isinstance(paragraphs, list) and len(paragraphs) == 1:
        paragraph = paragraphs[0]
        if isinstance(paragraph, dict):
            paragraph_raw = str(paragraph.get("text", ""))
            paragraph["raw_text"] = paragraph_raw
            paragraph["text"] = recovered_text
            paragraph["number_recovery"] = dict(cell["number_recovery"])
            if pua_replacements:
                paragraph["pua_characters"] = pua_replacements


def recover_table_item_numbers(
    cells: list[dict[str, Any]],
    *,
    context: ParseContext,
    source: dict[str, Any],
) -> None:
    """확실한 근거가 있는 번호만 복원합니다.

    안전 규칙:
    1. 등록된 PUA 문자를 직접 숫자로 치환한 셀만 ``verified anchor``로 인정합니다.
    2. anchor와 같은 열에서 가까운 후속 ``-1``/``-2`` 항목만 복원합니다.
    3. 55A, 59A, 면적, 가격 등 일반 숫자는 prefix 근거로 절대 사용하지 않습니다.
    4. 근거가 없으면 원문을 유지하고 unresolved 메타데이터만 기록합니다.
    """
    if not cells:
        return

    # 0단계: 셀 문단에서 검증된 Compose 복원값을 anchor 메타데이터로 승격합니다.
    for cell in cells:
        paragraphs = cell.get("paragraphs", [])
        if not isinstance(paragraphs, list):
            continue

        verified_compose = []
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                continue
            recoveries = paragraph.get("compose_recoveries", [])
            if not isinstance(recoveries, list):
                continue
            verified_compose.extend(
                recovery
                for recovery in recoveries
                if isinstance(recovery, dict)
                and recovery.get("recovered") is True
                and recovery.get("method") == "compose_map"
                and recovery.get("mapped_value")
                and float(recovery.get("confidence", 0.0)) >= 1.0
            )

        if not verified_compose:
            continue

        current_text = str(cell.get("text", ""))
        prefix_match = re.match(r"^\s*(\d+)(?:\s|[-]|$)", current_text)
        if not prefix_match:
            continue

        cell.setdefault("raw_text", current_text)
        cell["number_recovery"] = {
            "recovered": True,
            "method": "compose_map",
            "prefix": prefix_match.group(1),
            "confidence": 1.0,
            "items": verified_compose,
        }

    # 1단계: 알려진 PUA 문자만 직접 치환합니다.
    for cell in cells:
        raw_text = str(cell.get("text", ""))
        replaced, replacements = _replace_pua_numbers(raw_text)
        if not replacements:
            continue

        mapped_items = [item for item in replacements if item.get("mapped_value")]
        mapped = bool(mapped_items)
        prefix_match = re.match(r"^\s*(\d+)(?:\s|$)", replaced) if mapped else None

        _set_recovered_cell_text(
            cell,
            replaced,
            raw_text=raw_text,
            method="pua_map" if mapped else "pua_detected_unresolved",
            prefix=prefix_match.group(1) if prefix_match else None,
            confidence=1.0 if prefix_match else 0.0,
            pua_replacements=replacements,
        )

        if prefix_match:
            context.warn(
                "HWPX_PUA_NUMBER_RECOVERED",
                "등록된 PUA 글리프를 확인된 일반 숫자로 복원했습니다.",
                source={
                    **source,
                    "row": cell.get("row"),
                    "col": cell.get("col"),
                    "raw_text": raw_text,
                    "recovered_text": replaced,
                    "pua_characters": replacements,
                },
            )
        else:
            context.warn(
                "HWPX_PUA_NUMBER_UNRESOLVED",
                "PUA 글리프를 발견했지만 확인된 숫자 매핑이 없어 원문을 유지했습니다.",
                source={
                    **source,
                    "row": cell.get("row"),
                    "col": cell.get("col"),
                    "raw_text": raw_text,
                    "pua_characters": replacements,
                },
            )

    # 2단계: PUA로 직접 확인된 anchor만 가까운 하위 항목에 전달합니다.
    rows: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        rows.setdefault(int(cell.get("row", 0)), []).append(cell)

    # 열별 최근 검증 anchor: col -> (prefix, row)
    verified_anchors: dict[int, tuple[str, int]] = {}
    max_row_distance = 3

    for row_index in sorted(rows):
        row_cells = sorted(rows[row_index], key=lambda item: int(item.get("col", 0)))

        # 먼저 이 행의 검증 anchor를 등록합니다.
        for cell in row_cells:
            recovery = cell.get("number_recovery")
            if not isinstance(recovery, dict):
                continue
            if (
                recovery.get("recovered") is True
                and recovery.get("method") in {"pua_map", "compose_map"}
                and recovery.get("prefix")
                and float(recovery.get("confidence", 0.0)) >= 1.0
            ):
                verified_anchors[int(cell.get("col", 0))] = (
                    str(recovery["prefix"]),
                    row_index,
                )

        for cell in row_cells:
            raw_text = str(cell.get("raw_text", cell.get("text", "")))
            missing = re.match(r"^\s*-(\d+)\s*(.+)$", raw_text, flags=re.DOTALL)
            if not missing:
                continue

            col = int(cell.get("col", 0))
            anchor = verified_anchors.get(col)
            if anchor is not None:
                prefix, anchor_row = anchor
                distance = row_index - anchor_row
                if 0 < distance <= max_row_distance:
                    recovered = f"{prefix}-{missing.group(1)} {missing.group(2).strip()}"
                    _set_recovered_cell_text(
                        cell,
                        recovered,
                        raw_text=raw_text,
                        method="verified_pua_context",
                        prefix=prefix,
                        confidence=1.0,
                    )
                    context.warn(
                        "HWPX_MISSING_ITEM_PREFIX_RECOVERED",
                        "같은 열의 가까운 PUA 검증 번호를 사용해 하위 항목 번호를 복원했습니다.",
                        source={
                            **source,
                            "row": row_index,
                            "col": col,
                            "anchor_row": anchor_row,
                            "raw_text": raw_text,
                            "recovered_text": recovered,
                        },
                    )
                    continue

            # 근거가 없거나 너무 멀면 절대 추측하지 않습니다.
            cell.setdefault("raw_text", raw_text)
            cell["number_recovery"] = {
                "recovered": False,
                "method": "missing_prefix_unresolved",
                "prefix": None,
                "confidence": 0.0,
            }
            context.warn(
                "HWPX_MISSING_ITEM_PREFIX_UNRESOLVED",
                "상위 번호가 누락된 항목을 발견했지만 검증된 근거가 없어 원문을 유지했습니다.",
                source={
                    **source,
                    "row": row_index,
                    "col": col,
                    "raw_text": raw_text,
                },
            )

        # 너무 오래된 anchor는 폐기합니다.
        verified_anchors = {
            col: value
            for col, value in verified_anchors.items()
            if row_index - value[1] <= max_row_distance
        }



def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _natural_section_key(name: str) -> tuple[int, str]:
    match = re.search(r"section(\d+)\.xml$", name, flags=re.IGNORECASE)
    return (int(match.group(1)) if match else 10**9, name.lower())


def _extract_xml_text(element: ET.Element, *, skip_tables: bool = False) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        local = _local_name(node.tag).lower()
        if skip_tables and local in {"tbl", "table"}:
            return

        if local in {"t", "text", "char", "compose", "composetext"}:
            value = "".join(node.itertext())
            if value:
                parts.append(value)
            return

        for child in list(node):
            visit(child)

    visit(element)
    return "".join(parts)


def load_hwpx_xml_top_level_paragraphs(
    hwpx_path: str | Path,
) -> dict[int, list[str]]:
    """HWPX 내부 XML에서 최상위 문단 텍스트를 보조 추출합니다.

    hwpxlib가 글자 겹치기·특수 문자 객체를 일반 문자열에서 누락하는 경우,
    같은 문단의 XML 텍스트를 이용해 원문을 보완합니다. 표 내부 문단은
    최상위 문단과 섞이지 않도록 제외합니다.
    """
    result: dict[int, list[str]] = {}
    path = Path(hwpx_path)

    try:
        with zipfile.ZipFile(path, "r") as archive:
            section_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.search(
                        r"(^|/)Contents/section\d+\.xml$",
                        name,
                        flags=re.IGNORECASE,
                    )
                    or re.search(
                        r"(^|/)section\d+\.xml$",
                        name,
                        flags=re.IGNORECASE,
                    )
                ),
                key=_natural_section_key,
            )

            for section_index, section_name in enumerate(section_names):
                root = ET.fromstring(archive.read(section_name))
                paragraphs: list[str] = []

                def walk(node: ET.Element, *, inside_table: bool = False) -> None:
                    local = _local_name(node.tag).lower()
                    now_inside_table = inside_table or local in {"tbl", "table"}

                    if local in {"p", "para", "paragraph"} and not now_inside_table:
                        paragraphs.append(
                            _extract_xml_text(node, skip_tables=True)
                        )
                        return

                    for child in list(node):
                        walk(child, inside_table=now_inside_table)

                walk(root)
                result[section_index] = paragraphs
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return {}

    return result


def _looks_like_java_object_repr(value: str) -> bool:
    return bool(
        re.fullmatch(r"[\w.$]+@[0-9a-fA-F]+", value)
        or value.startswith("<java object '")
    )


def _extract_unknown_java_text(item: Any, *, depth: int = 0) -> str:
    """hwpxlib의 미지원 텍스트 객체에서 표시 문자열을 최대한 보존합니다."""
    if item is None or depth > 3:
        return ""

    if isinstance(item, str):
        return item

    method_names = (
        "text",
        "getText",
        "onlyText",
        "value",
        "getValue",
        "content",
        "getContent",
        "charValue",
        "getChar",
        "character",
        "composeText",
        "getComposeText",
    )

    for method_name in method_names:
        try:
            method = getattr(item, method_name, None)
            if not callable(method):
                continue
            value = method()
            if value is None or value is item:
                continue
            if isinstance(value, str):
                if value and not _looks_like_java_object_repr(value):
                    return value
            else:
                nested = _extract_unknown_java_text(value, depth=depth + 1)
                if nested:
                    return nested
        except Exception:
            continue

    collection_patterns = (
        ("countOfItems", "getItem"),
        ("countOfRunItem", "getRunItem"),
        ("count", "get"),
        ("size", "get"),
    )
    for count_name, getter_name in collection_patterns:
        try:
            count_method = getattr(item, count_name, None)
            getter = getattr(item, getter_name, None)
            if not callable(count_method) or not callable(getter):
                continue
            count = int(count_method())
            values: list[str] = []
            for index in range(count):
                nested = _extract_unknown_java_text(
                    getter(index),
                    depth=depth + 1,
                )
                if nested:
                    values.append(nested)
            if values:
                return "".join(values)
        except Exception:
            continue

    try:
        value = str(item)
    except Exception:
        return ""

    return "" if _looks_like_java_object_repr(value) else value


def _compose_codepoints(value: str) -> list[str]:
    return [
        f"U+{ord(char):05X}"
        for char in str(value or "")
        if _is_private_use_char(char)
    ]


def extract_text_from_compose(
    compose_item: Any,
    *,
    context: ParseContext | None = None,
    source: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Compose RunItem의 원문 문자열을 손실 없이 보존합니다.

    Parser의 역할은 HWPX 내부 표현을 읽는 데까지로 제한합니다.
    PUA/Compose 글리프가 어떤 숫자를 의미하는지는 여기서 해석하지 않고,
    codepoint와 원문 문자열만 metadata에 기록합니다.
    실제 숫자 변환은 Normalizer 단계에서 수행합니다.
    """
    if compose_item is None:
        return "", None

    raw_value = _extract_unknown_java_text(compose_item)
    if not raw_value:
        return "", None

    codepoints = _compose_codepoints(raw_value)

    recovery: dict[str, Any] = {
        "raw_value": raw_value,
        "codepoints": codepoints,
        "mapped_value": "",
        "recovered": False,
        "method": "compose_preserved",
        "confidence": 1.0,
    }

    if codepoints and context is not None:
        context.warn(
            "HWPX_COMPOSE_PRESERVED",
            "Compose 글리프를 원문 그대로 보존했습니다. 의미 변환은 Normalizer에서 수행합니다.",
            source={
                **(source or {}),
                "raw_value": raw_value,
                "codepoints": codepoints,
            },
        )

    return raw_value, recovery


def _debug_hwpx_text_item(
    text_item: Any,
    *,
    source: dict[str, Any] | None = None,
) -> None:
    """HWPX T 객체 내부의 PUA 및 비표준 텍스트 객체를 진단합니다."""
    if not DEBUG_SPECIAL_CHARACTERS or text_item is None:
        return

    diagnostics: list[dict[str, Any]] = []

    try:
        item_count = int(text_item.countOfItems())
    except Exception:
        return

    for item_index in range(item_count):
        try:
            item = text_item.getItem(item_index)
        except Exception:
            continue

        class_name = java_class_name(item)
        value = ""

        if class_name.endswith(".NormalText"):
            try:
                raw = item.text()
                value = "" if raw is None else str(raw)
            except Exception:
                value = ""
        else:
            value = _extract_unknown_java_text(item)

        pua_values = [
            {
                "position": index,
                "character": repr(char),
                "codepoint": f"U+{ord(char):05X}",
            }
            for index, char in enumerate(value)
            if _is_private_use_char(char)
        ]

        is_special_object = not any(
            class_name.endswith(suffix)
            for suffix in (".NormalText", ".FWSpace", ".LineBreak", ".Tab")
        )

        if pua_values or is_special_object:
            diagnostics.append(
                {
                    "item_index": item_index,
                    "class_name": class_name,
                    "value": value,
                    "pua": pua_values,
                }
            )

    if not diagnostics:
        return

    print()
    print("=" * 80)
    print("[HWPX T 객체 진단]")
    print("source:", source or {})

    for item in diagnostics:
        print(
            f"item_index={item['item_index']}",
            f"class={item['class_name']}",
        )
        print("value:", repr(item["value"]))
        for pua in item["pua"]:
            print(
                "  PUA:",
                f"position={pua['position']}",
                f"character={pua['character']}",
                f"codepoint={pua['codepoint']}",
            )

    print("=" * 80)


def _debug_hwpx_run_item(
    item: Any,
    *,
    source: dict[str, Any],
) -> None:
    """T/표가 아닌 HWPX RunItem의 저장 형태를 콘솔에 출력합니다."""
    if not DEBUG_SPECIAL_CHARACTERS or item is None:
        return

    class_name = java_class_name(item)

    if (
        class_name.endswith(HWPX_TEXT_CLASS_SUFFIX)
        or class_name.endswith(HWPX_TABLE_CLASS_SUFFIX)
    ):
        return

    lowered = class_name.lower()
    extracted = _extract_unknown_java_text(item)

    interesting_class = any(
        token in lowered
        for token in (
            "overlap",
            "overlapping",
            "compose",
            "character",
            "char",
            "text",
        )
    )

    if not interesting_class and not extracted:
        return

    print()
    print("=" * 80)
    print("[HWPX RunItem 진단]")
    print("source:", source)
    print("class:", class_name)
    print("extracted:", repr(extracted))
    print("=" * 80)


def _repair_text_with_xml(library_text: str, xml_text: str) -> tuple[str, bool]:
    """라이브러리 결과에서 빠진 문자만 XML 원문으로 보완합니다."""
    library_text = library_text or ""
    xml_text = xml_text or ""

    if not xml_text.strip() or library_text == xml_text:
        return library_text, False

    # 라이브러리 문자열이 XML 문자열의 뒷부분이면 앞에서 누락된 접두부를 복원합니다.
    if library_text and xml_text.endswith(library_text):
        return xml_text, True

    # 공백 차이만 무시했을 때 동일하면 원문의 표기를 보존합니다.
    compact_library = re.sub(r"\s+", "", library_text)
    compact_xml = re.sub(r"\s+", "", xml_text)
    if compact_library and compact_library == compact_xml:
        return xml_text, True

    # 파서 텍스트가 비어 있으면 XML 텍스트를 사용합니다.
    if not library_text.strip():
        return xml_text, True

    return library_text, False


def extract_text_from_t(
    text_item: Any,
    *,
    context: ParseContext | None = None,
    source: dict[str, Any] | None = None,
) -> str:
    if text_item is None:
        return ""

    _debug_hwpx_text_item(
        text_item,
        source=source,
    )

    try:
        if text_item.isOnlyText():
            text = text_item.onlyText()
            return "" if text is None else str(text)
    except Exception:
        pass

    parts: list[str] = []

    try:
        item_count = int(text_item.countOfItems())
    except Exception as error:
        if context is not None:
            context.warn(
                "HWPX_TEXT_ITEM_COUNT_FAILED",
                "HWPX T 객체의 내부 항목 수를 읽지 못했습니다.",
                source=source,
                error=error,
            )
        return ""

    for item_index in range(item_count):
        try:
            item = text_item.getItem(item_index)
        except Exception:
            continue

        class_name = java_class_name(item)

        if class_name.endswith(".NormalText"):
            try:
                value = item.text()
            except Exception:
                value = None
            if value is not None:
                parts.append(str(value))
        elif class_name.endswith(".FWSpace"):
            parts.append(" ")
        elif class_name.endswith(".LineBreak"):
            parts.append("\n")
        elif class_name.endswith(".Tab"):
            parts.append("\t")
        else:
            # 글자 겹치기, 특수 문자 등 hwpxlib가 NormalText로 분류하지
            # 않는 객체도 가능한 범위에서 표시 문자열을 보존합니다.
            value = _extract_unknown_java_text(item)
            if value:
                parts.append(value)

    return "".join(parts)


def extract_cell_paragraphs(
    cell: Any,
    *,
    context: ParseContext,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    paragraphs_data: list[dict[str, Any]] = []

    try:
        sublist = cell.subList()
        paragraph_count = int(sublist.countOfPara()) if sublist else 0
    except Exception as error:
        context.warn(
            "HWPX_CELL_PARAGRAPH_LIST_READ_FAILED",
            "HWPX 셀의 문단 목록을 읽지 못했습니다.",
            source=source,
            error=error,
        )
        return paragraphs_data

    for paragraph_index in range(paragraph_count):
        try:
            paragraph = sublist.getPara(paragraph_index)
            run_count = int(paragraph.countOfRun()) if paragraph else 0
        except Exception as error:
            context.warn(
                "HWPX_CELL_PARAGRAPH_READ_FAILED",
                "HWPX 셀 문단을 읽지 못했습니다.",
                source={**source, "cell_paragraph_index": paragraph_index},
                error=error,
            )
            continue

        paragraph_parts: list[str] = []
        compose_recoveries: list[dict[str, Any]] = []

        for run_index in range(run_count):
            try:
                run = paragraph.getRun(run_index)
                item_count = int(run.countOfRunItem()) if run else 0
            except Exception:
                continue

            for item_index in range(item_count):
                try:
                    item = run.getRunItem(item_index)
                except Exception:
                    continue

                item_source = {
                    **source,
                    "cell_paragraph_index": paragraph_index,
                    "run_index": run_index,
                    "item_index": item_index,
                    "location": "table_cell",
                }
                class_name = java_class_name(item)

                _debug_hwpx_run_item(
                    item,
                    source=item_source,
                )

                if class_name.endswith(HWPX_TEXT_CLASS_SUFFIX):
                    text_value = extract_text_from_t(
                        item,
                        context=context,
                        source=item_source,
                    )
                    if text_value:
                        paragraph_parts.append(text_value)
                    continue

                if class_name.endswith(HWPX_COMPOSE_CLASS_SUFFIX):
                    compose_text, recovery = extract_text_from_compose(
                        item,
                        context=context,
                        source=item_source,
                    )
                    if compose_text:
                        paragraph_parts.append(compose_text)
                    if recovery is not None:
                        compose_recoveries.append({
                            **recovery,
                            "run_index": run_index,
                            "item_index": item_index,
                        })
                    continue

                # 표는 별도의 nested table 탐색 단계에서 처리합니다.

        paragraph_text = "".join(paragraph_parts)
        if paragraph_text.strip():
            paragraph_data: dict[str, Any] = {
                "paragraph_index": paragraph_index,
                "text": paragraph_text,
            }
            if compose_recoveries:
                paragraph_data["compose_recoveries"] = compose_recoveries
            paragraphs_data.append(paragraph_data)

    return paragraphs_data

def find_nested_tables_in_hwpx_cell(
    cell: Any,
    *,
    context: ParseContext,
    section_index: int | None,
    parent_table_index: int,
    parent_cell: dict[str, int],
    depth: int,
    object_path: list[str],
) -> list[dict[str, Any]]:
    nested_tables: list[dict[str, Any]] = []

    if depth >= context.max_nested_depth:
        context.warn(
            "MAX_NESTED_DEPTH_EXCEEDED",
            "설정된 중첩 표 최대 깊이에 도달하여 하위 표 탐색을 중단했습니다.",
            source={
                "section_index": section_index,
                "parent_table_index": parent_table_index,
                "parent_cell": parent_cell,
                "nested_depth": depth,
                "object_path": object_path,
            },
            fatal_in_strict=True,
        )
        return nested_tables

    try:
        sublist = cell.subList()
        paragraph_count = int(sublist.countOfPara()) if sublist else 0
    except Exception as error:
        context.warn(
            "HWPX_NESTED_TABLE_SCAN_FAILED",
            "HWPX 셀의 중첩 표 탐색을 시작하지 못했습니다.",
            source={
                "section_index": section_index,
                "parent_table_index": parent_table_index,
                "parent_cell": parent_cell,
            },
            error=error,
        )
        return nested_tables

    for paragraph_index in range(paragraph_count):
        try:
            paragraph = sublist.getPara(paragraph_index)
            run_count = int(paragraph.countOfRun()) if paragraph else 0
        except Exception:
            continue

        for run_index in range(run_count):
            try:
                run = paragraph.getRun(run_index)
                item_count = int(run.countOfRunItem()) if run else 0
            except Exception:
                continue

            for item_index in range(item_count):
                try:
                    item = run.getRunItem(item_index)
                except Exception:
                    continue

                if not java_class_name(item).endswith(HWPX_TABLE_CLASS_SUFFIX):
                    continue

                table_index = context.allocate_table_index("nested_table")
                nested_path = [
                    *object_path,
                    f"cell:{parent_cell['row']},{parent_cell['col']}",
                    f"paragraph:{paragraph_index}",
                    f"run:{run_index}",
                    f"item:{item_index}",
                    f"table:{table_index}",
                ]
                source = {
                    "section_index": section_index,
                    "paragraph_index": paragraph_index,
                    "run_index": run_index,
                    "item_index": item_index,
                    "location": "nested_table",
                    "parent_table_index": parent_table_index,
                    "parent_cell": parent_cell,
                    "nested_depth": depth + 1,
                    "object_path": nested_path,
                }
                nested_tables.append(
                    parse_table(
                        table=item,
                        table_index=table_index,
                        context=context,
                        source=source,
                        depth=depth + 1,
                        object_path=nested_path,
                    )
                )

    return nested_tables


def parse_table(
    table: Any,
    table_index: int,
    *,
    context: ParseContext,
    source: dict[str, Any],
    depth: int,
    object_path: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "table",
        "table_index": table_index,
        "row_count": 0,
        "col_count": 0,
        "cells": [],
        "source": source,
    }

    if not context.enter_table(table, source):
        return result

    try:
        try:
            row_count_from_api = int(table.countOfTr())
        except Exception as error:
            context.warn(
                "HWPX_TABLE_ROWS_READ_FAILED",
                "HWPX 표의 행 수를 읽지 못했습니다.",
                source=source,
                error=error,
                fatal_in_strict=True,
            )
            return result

        cells: list[dict[str, Any]] = []

        for row_list_index in range(row_count_from_api):
            try:
                row = table.getTr(row_list_index)
                cell_count = int(row.countOfTc()) if row else 0
            except Exception as error:
                context.warn(
                    "HWPX_TABLE_ROW_READ_FAILED",
                    "HWPX 표 행을 읽지 못했습니다.",
                    source={**source, "row_list_index": row_list_index},
                    error=error,
                )
                continue

            for cell_list_index in range(cell_count):
                try:
                    cell = row.getTc(cell_list_index)
                    address = cell.cellAddr()
                    span = cell.cellSpan()
                    actual_row = int(address.rowAddr())
                    actual_col = int(address.colAddr())
                    row_span = max(1, int(span.rowSpan()))
                    col_span = max(1, int(span.colSpan()))
                except Exception as error:
                    context.warn(
                        "HWPX_CELL_ADDRESS_READ_FAILED",
                        "HWPX 셀의 좌표 또는 병합 정보를 읽지 못해 해당 셀을 제외했습니다.",
                        source={
                            **source,
                            "row_list_index": row_list_index,
                            "cell_list_index": cell_list_index,
                        },
                        error=error,
                        fatal_in_strict=True,
                    )
                    continue

                parent_cell = {
                    "row": actual_row,
                    "col": actual_col,
                }
                cell_source = {
                    **source,
                    "row_list_index": row_list_index,
                    "cell_list_index": cell_list_index,
                    **parent_cell,
                }
                paragraphs = extract_cell_paragraphs(
                    cell,
                    context=context,
                    source=cell_source,
                )
                nested_tables = find_nested_tables_in_hwpx_cell(
                    cell,
                    context=context,
                    section_index=source.get("section_index"),
                    parent_table_index=table_index,
                    parent_cell=parent_cell,
                    depth=depth,
                    object_path=object_path,
                )

                cells.append(
                    {
                        "row": actual_row,
                        "col": actual_col,
                        "row_span": row_span,
                        "col_span": col_span,
                        "text": "\n".join(
                            str(paragraph.get("text", ""))
                            for paragraph in paragraphs
                            if str(paragraph.get("text", "")).strip()
                        ).strip(),
                        "paragraphs": paragraphs,
                        "nested_tables": nested_tables,
                    }
                )
                context.add_cell()

        recover_table_item_numbers(
            cells,
            context=context,
            source=source,
        )

        logical_row_count = max(
            (cell["row"] + cell["row_span"] for cell in cells),
            default=0,
        )
        logical_col_count = max(
            (cell["col"] + cell["col_span"] for cell in cells),
            default=0,
        )

        result.update(
            {
                "row_count": logical_row_count,
                "col_count": logical_col_count,
                "cells": cells,
            }
        )
        return result

    finally:
        context.exit_table(table)


def _append_paragraph_segment(
    section_blocks: list[dict[str, Any]],
    *,
    context: ParseContext,
    text_parts: list[str],
    section_index: int,
    paragraph_index: int,
    start_position: dict[str, int] | None,
    end_position: dict[str, int] | None,
) -> None:
    text = "".join(text_parts)

    if not text.strip():
        text_parts.clear()
        return

    source: dict[str, Any] = {
        "section_index": section_index,
        "paragraph_index": paragraph_index,
        "location": "top_level",
    }

    if start_position is not None:
        source["start_position"] = start_position
    if end_position is not None:
        source["end_position"] = end_position

    section_blocks.append(
        {
            "type": "paragraph",
            "paragraph_index": paragraph_index,
            "text": text,
            "source": source,
        }
    )
    context.add_paragraph()
    text_parts.clear()


def parse_hwpx(
    hwpx_jar_path: str | Path | None,
    hwpx_file_path: str | Path,
    *,
    original_filename: str | None = None,
    max_nested_depth: int = 10,
    strict: bool = False,
) -> dict[str, Any]:
    jar_path = resolve_jar_path("hwpx", hwpx_jar_path)
    file_path = validate_document_path(hwpx_file_path, ".hwpx")

    ensure_jvm(
        [jar_path],
        required_classes=[HWPX_READER_CLASS],
    )

    reader = jpype.JClass(HWPX_READER_CLASS)
    hwpx_file = reader.fromFilepath(str(file_path))

    if hwpx_file is None:
        raise RuntimeError(f"HWPX 파일 파싱에 실패했습니다: {file_path}")

    context = ParseContext(
        max_nested_depth=max_nested_depth,
        strict=strict,
    )
    xml_paragraphs = load_hwpx_xml_top_level_paragraphs(file_path)
    document = build_document_header(
        file_path,
        document_format="hwpx",
        engine="hwpxlib",
        jar_path=jar_path,
    )

    if original_filename:
        document["document"]["filename"] = original_filename

    try:
        sections = hwpx_file.sectionXMLFileList()
        section_count = int(sections.count())
    except Exception as error:
        raise RuntimeError(
            f"HWPX Section 목록을 읽지 못했습니다: {file_path}"
        ) from error

    for section_index in range(section_count):
        section = sections.get(section_index)
        section_data: dict[str, Any] = {
            "section_index": section_index,
            "blocks": [],
        }

        try:
            paragraph_count = int(section.countOfPara())
        except Exception as error:
            context.warn(
                "HWPX_SECTION_PARAGRAPHS_READ_FAILED",
                "HWPX Section의 문단 수를 읽지 못했습니다.",
                source={"section_index": section_index},
                error=error,
                fatal_in_strict=True,
            )
            document["sections"].append(section_data)
            continue

        for paragraph_index in range(paragraph_count):
            paragraph_block_start = len(section_data["blocks"])
            try:
                paragraph = section.getPara(paragraph_index)
                run_count = int(paragraph.countOfRun()) if paragraph else 0
            except Exception as error:
                context.warn(
                    "HWPX_PARAGRAPH_READ_FAILED",
                    "HWPX 최상위 문단을 읽지 못했습니다.",
                    source={
                        "section_index": section_index,
                        "paragraph_index": paragraph_index,
                    },
                    error=error,
                )
                continue

            text_parts: list[str] = []
            segment_start: dict[str, int] | None = None
            segment_end: dict[str, int] | None = None

            for run_index in range(run_count):
                try:
                    run = paragraph.getRun(run_index)
                    item_count = int(run.countOfRunItem()) if run else 0
                except Exception:
                    continue

                for item_index in range(item_count):
                    try:
                        item = run.getRunItem(item_index)
                    except Exception:
                        continue

                    class_name = java_class_name(item)
                    position = {
                        "run_index": run_index,
                        "item_index": item_index,
                    }

                    _debug_hwpx_run_item(
                        item,
                        source={
                            "section_index": section_index,
                            "paragraph_index": paragraph_index,
                            **position,
                            "location": "top_level",
                        },
                    )

                    item_source = {
                        "section_index": section_index,
                        "paragraph_index": paragraph_index,
                        **position,
                        "location": "top_level",
                    }

                    if class_name.endswith(HWPX_TEXT_CLASS_SUFFIX):
                        text = extract_text_from_t(
                            item,
                            context=context,
                            source=item_source,
                        )
                        if text:
                            if segment_start is None:
                                segment_start = position
                            segment_end = position
                            text_parts.append(text)
                        continue

                    if class_name.endswith(HWPX_COMPOSE_CLASS_SUFFIX):
                        compose_text, _ = extract_text_from_compose(
                            item,
                            context=context,
                            source=item_source,
                        )
                        if compose_text:
                            if segment_start is None:
                                segment_start = position
                            segment_end = position
                            text_parts.append(compose_text)
                        continue

                    if not class_name.endswith(HWPX_TABLE_CLASS_SUFFIX):
                        continue

                    _append_paragraph_segment(
                        section_data["blocks"],
                        context=context,
                        text_parts=text_parts,
                        section_index=section_index,
                        paragraph_index=paragraph_index,
                        start_position=segment_start,
                        end_position=segment_end,
                    )
                    segment_start = None
                    segment_end = None

                    table_index = context.allocate_table_index("top_level")
                    object_path = [
                        f"section:{section_index}",
                        f"paragraph:{paragraph_index}",
                        f"run:{run_index}",
                        f"item:{item_index}",
                        f"table:{table_index}",
                    ]
                    source = {
                        "section_index": section_index,
                        "paragraph_index": paragraph_index,
                        "run_index": run_index,
                        "item_index": item_index,
                        "location": "top_level",
                        "nested_depth": 0,
                        "object_path": object_path,
                    }
                    section_data["blocks"].append(
                        parse_table(
                            table=item,
                            table_index=table_index,
                            context=context,
                            source=source,
                            depth=0,
                            object_path=object_path,
                        )
                    )

            _append_paragraph_segment(
                section_data["blocks"],
                context=context,
                text_parts=text_parts,
                section_index=section_index,
                paragraph_index=paragraph_index,
                start_position=segment_start,
                end_position=segment_end,
            )

            # 같은 최상위 문단의 XML 텍스트와 비교해 글자 겹치기·특수문자
            # 누락을 보완합니다. 표가 섞인 문단은 잘못 합치지 않도록
            # 일반 문단 블록이 정확히 하나일 때만 교체합니다.
            xml_section = xml_paragraphs.get(section_index, [])
            xml_text = (
                xml_section[paragraph_index]
                if paragraph_index < len(xml_section)
                else ""
            )
            new_blocks = section_data["blocks"][paragraph_block_start:]
            paragraph_blocks = [
                block for block in new_blocks
                if block.get("type") == "paragraph"
            ]
            table_blocks = [
                block for block in new_blocks
                if block.get("type") == "table"
            ]
            if xml_text and len(paragraph_blocks) == 1 and not table_blocks:
                block = paragraph_blocks[0]
                original_text = str(block.get("text", ""))
                repaired_text, repaired = _repair_text_with_xml(
                    original_text,
                    xml_text,
                )
                if repaired:
                    block["text"] = repaired_text
                    block["source"]["text_recovered_from_xml"] = True
                    context.warn(
                        "HWPX_TEXT_RECOVERED_FROM_XML",
                        "hwpxlib에서 누락된 문자를 HWPX 내부 XML 텍스트로 복원했습니다.",
                        source={
                            "section_index": section_index,
                            "paragraph_index": paragraph_index,
                            "library_text": original_text,
                            "xml_text": xml_text,
                        },
                    )

        document["sections"].append(section_data)

    document["statistics"] = context.statistics(len(document["sections"]))
    document["warnings"] = context.warnings
    return document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="hwpxlib를 이용해 HWPX를 중첩 표 포함 Raw JSON으로 변환합니다."
    )
    parser.add_argument(
        "--hwpx_jar_path",
        default=None,
        help="생략 시 환경변수 또는 libs/hwpx의 단일 JAR를 자동 탐색합니다.",
    )
    parser.add_argument("--file_path", required=True)
    parser.add_argument(
        "--original-filename",
        default=None,
        help="JSON에 기록할 실제 원본 파일명",
    )
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--max_nested_depth", type=int, default=10)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    result = parse_hwpx(
        hwpx_jar_path=args.hwpx_jar_path,
        hwpx_file_path=args.file_path,
        original_filename=args.original_filename,
        max_nested_depth=args.max_nested_depth,
        strict=args.strict,
    )
    output_path = save_json(result, args.output_path)

    print("=" * 80)
    print("HWPX 파싱 완료")
    print("=" * 80)
    statistics = result.get("statistics", {})

    paragraph_count = statistics.get(
        "paragraph_count",
        statistics.get(
            "top_level_paragraph_count",
            statistics.get("normal_paragraph_count", 0),
        ),
    )
    top_level_table_count = statistics.get(
        "top_level_table_count",
        statistics.get("table_count", 0),
    )
    nested_table_count = statistics.get("nested_table_count", 0)
    warning_count = statistics.get(
        "warning_count",
        len(result.get("warnings", [])),
    )

    print(f"파일: {result['document']['filename']}")
    print(f"Section 수: {statistics.get('section_count', len(result.get('sections', [])))}")
    print(f"일반 문단 수: {paragraph_count}")
    print(f"최상위 표 수: {top_level_table_count}")
    print(f"중첩 표 수: {nested_table_count}")
    print(f"경고 수: {warning_count}")
    print(f"출력: {output_path}")


if __name__ == "__main__":
    main()
