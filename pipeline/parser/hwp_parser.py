from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

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


HWP_READER_CLASS = "kr.dogfoot.hwplib.reader.HWPReader"
HWP_TABLE_CLASS_SUFFIX = ".ControlTable"


# 한컴 전용 글꼴(PUA)에서 확인된 네모 안 숫자 매핑입니다.
# 청주지북 테스트 문서에서 U+F02D6은 네모 안 숫자 12로 확인되었습니다.
HANGUL_PUA_NUMBER_MAP: dict[str, str] = {}

# HWP의 PUA 문자는 글꼴에 따라 화면에 표시되는 값이 달라질 수 있습니다.
# 따라서 HWP Parser에서는 PUA 코드나 이전 셀 번호를 실제 숫자로 추측하지 않습니다.
# 정확한 값은 동일 문서의 HWPX 결과 또는 별도의 글꼴 매핑 정보가 있을 때만 보완해야 합니다.


def _normalize_group_label(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _replace_pua_numbers(text: str) -> tuple[str, list[dict[str, str]]]:
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
        replacements.append({
            "character": char,
            "codepoint": f"U+{codepoint:05X}",
            "mapped_value": mapped or "",
        })
        if mapped:
            value = value.replace(char, mapped)

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


def recover_hwp_table_item_numbers(
    cells: list[dict[str, Any]],
    *,
    context: ParseContext,
    source: dict[str, Any],
) -> None:
    """HWP에서도 직접 확인된 번호만 가까운 하위 항목에 전달합니다.

    검증 anchor는 글자 겹치기 컨트롤에서 실제 숫자를 읽어
    ``overlapping_letter_control``로 기록된 셀뿐입니다. 일반 숫자나 PUA
    코드값은 항목 번호로 추측하지 않습니다.
    """
    if not cells:
        return

    rows: dict[int, list[dict[str, Any]]] = {}

    for cell in cells:
        raw_text = str(cell.get("text", ""))

        recovered_paragraphs = [
            paragraph
            for paragraph in cell.get("paragraphs", [])
            if isinstance(paragraph, dict)
            and isinstance(paragraph.get("number_recovery"), dict)
            and paragraph["number_recovery"].get("recovered") is True
            and paragraph["number_recovery"].get("method") == "overlapping_letter_control"
            and paragraph["number_recovery"].get("prefix")
        ]

        if recovered_paragraphs:
            original_cell_text = "\n".join(
                str(paragraph.get("raw_text", paragraph.get("text", "")))
                for paragraph in cell.get("paragraphs", [])
                if isinstance(paragraph, dict)
            ).strip()
            prefixes = {
                str(paragraph["number_recovery"]["prefix"])
                for paragraph in recovered_paragraphs
            }
            prefix = next(iter(prefixes)) if len(prefixes) == 1 else None
            cell["raw_text"] = original_cell_text
            cell["number_recovery"] = {
                "recovered": True,
                "method": "overlapping_letter_control",
                "prefix": prefix,
                "confidence": 1.0 if prefix else 0.0,
                "items": [paragraph["number_recovery"] for paragraph in recovered_paragraphs],
            }

        _, replacements = _replace_pua_numbers(raw_text)
        if replacements and not cell.get("number_recovery", {}).get("recovered"):
            cell.setdefault("raw_text", raw_text)
            cell["pua_characters"] = replacements
            cell["number_recovery"] = {
                "recovered": False,
                "method": "pua_detected_unresolved",
                "prefix": None,
                "confidence": 0.0,
            }
            context.warn(
                "HWP_PUA_NUMBER_UNRESOLVED",
                "PUA 글리프를 발견했지만 글꼴 기반 실제 숫자를 확정할 수 없어 원문을 유지했습니다.",
                source={
                    **source,
                    "row": cell.get("row"),
                    "col": cell.get("col"),
                    "raw_text": raw_text,
                    "pua_characters": replacements,
                },
            )

        rows.setdefault(int(cell.get("row", 0)), []).append(cell)

    verified_anchors: dict[int, tuple[str, int]] = {}
    max_row_distance = 3

    for row_index in sorted(rows):
        row_cells = sorted(rows[row_index], key=lambda item: int(item.get("col", 0)))

        for cell in row_cells:
            recovery = cell.get("number_recovery")
            if not isinstance(recovery, dict):
                continue
            if (
                recovery.get("recovered") is True
                and recovery.get("method") == "overlapping_letter_control"
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
                        method="verified_control_context",
                        prefix=prefix,
                        confidence=1.0,
                    )
                    context.warn(
                        "HWP_MISSING_ITEM_PREFIX_RECOVERED",
                        "같은 열의 가까운 글자 겹치기 검증 번호를 사용해 하위 항목 번호를 복원했습니다.",
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

            cell.setdefault("raw_text", raw_text)
            cell["number_recovery"] = {
                "recovered": False,
                "method": "missing_prefix_unresolved",
                "prefix": None,
                "confidence": 0.0,
            }
            context.warn(
                "HWP_MISSING_ITEM_PREFIX_UNRESOLVED",
                "상위 번호가 누락된 항목을 발견했지만 검증된 근거가 없어 원문을 유지했습니다.",
                source={
                    **source,
                    "row": row_index,
                    "col": col,
                    "raw_text": raw_text,
                },
            )

        verified_anchors = {
            col: value
            for col, value in verified_anchors.items()
            if row_index - value[1] <= max_row_distance
        }



def _iter_java_values(value: Any) -> list[Any]:
    """Java List/배열 또는 Python iterable을 안전하게 list로 변환합니다."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return [value[index] for index in range(len(value))]
    except Exception:
        pass
    try:
        size = int(value.size())
        return [value.get(index) for index in range(size)]
    except Exception:
        return [value]


def _collect_control_strings(value: Any, *, depth: int = 0) -> list[str]:
    """글자 겹치기 컨트롤에서 사람이 입력한 문자열만 보수적으로 수집합니다.

    getCode(), getId() 같은 내부 정숫값은 절대 읽지 않습니다. 이전 버전에서
    12가 55로 변한 원인이 내부 ID/코드값을 숫자로 오인한 것이기 때문입니다.
    """
    if value is None or depth > 3:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, bytes):
        try:
            return [value.decode('utf-8', errors='ignore')]
        except Exception:
            return []

    values = _iter_java_values(value)
    if len(values) > 1 or (values and values[0] is not value):
        result: list[str] = []
        for item in values:
            result.extend(_collect_control_strings(item, depth=depth + 1))
        return result

    method_names = (
        'getNormalString',
        'getString',
        'getText',
        'getTexts',
        'getLetter',
        'getLetters',
        'getLetterList',
        'getOverlappingLetter',
        'getOverlappingLetters',
        'getOverlappingLetterList',
        'getContent',
        'getContents',
        'getCharList',
    )
    result: list[str] = []
    for method_name in method_names:
        try:
            method = getattr(value, method_name, None)
            if not callable(method):
                continue
            child = method()
        except Exception:
            continue
        if child is value:
            continue
        result.extend(_collect_control_strings(child, depth=depth + 1))
    return result



def _java_byte_array_to_bytes(value: Any) -> bytes:
    """Java byte[]를 Python bytes로 안전하게 변환합니다.

    JPype의 Java byte는 -128~127의 signed 값으로 보일 수 있으므로
    ``& 0xFF``를 적용해 원래 0~255 바이트 값으로 복원합니다.
    """
    if value is None:
        return b""

    try:
        return bytes(
            int(value[index]) & 0xFF
            for index in range(len(value))
        )
    except Exception:
        pass

    try:
        size = int(value.length)
        return bytes(
            int(value[index]) & 0xFF
            for index in range(size)
        )
    except Exception:
        return b""


def _extract_overlapping_letter_strings(control: Any) -> list[str]:
    """ControlOverlappingLetter의 실제 겹침 문자열을 안전하게 읽습니다.

    HWP 5.0 명세의 글자 겹침 데이터는 WCHAR array[len]입니다.

    hwplib는 이 값을 여러 HWPString 객체로 나눠 보관할 수 있는데,
    보조 평면 PUA(U+Fxxxx 등)는 UTF-16 surrogate pair 두 WCHAR를
    사용합니다. 각 HWPString을 따로 ``toUTF16LEString()`` 하면
    surrogate 절반만 디코딩되어 U+FFFD(�)로 깨질 수 있습니다.

    따라서 모든 HWPString.getBytes()를 먼저 원래 순서대로 합친 뒤
    UTF-16LE로 한 번에 디코딩합니다.
    """
    class_name = java_class_name(control)
    lowered = class_name.lower()

    if not any(
        token in lowered
        for token in (
            "overlappingletter",
            "overlapping",
            "overlap",
        )
    ):
        return []

    try:
        header = control.getHeader()
    except Exception:
        header = None

    if header is None:
        return []

    try:
        letter_list = header.getOverlappingLetterList()
    except Exception:
        letter_list = None

    if letter_list is None:
        return []

    items = _iter_java_values(letter_list)
    if not items:
        return []

    # 1순위: 모든 WCHAR의 원시 바이트를 연결한 후 한 번에 UTF-16LE 디코딩.
    combined = bytearray()

    for item in items:
        try:
            raw = item.getBytes()
        except Exception:
            raw = None

        raw_bytes = _java_byte_array_to_bytes(raw)
        if raw_bytes:
            combined.extend(raw_bytes)

    if combined:
        try:
            value = bytes(combined).decode(
                "utf-16-le",
                errors="strict",
            )
        except UnicodeDecodeError:
            value = ""

        # replacement character가 있으면 정상 복원으로 인정하지 않습니다.
        if value and "\ufffd" not in value:
            return [value]

    # 2순위 fallback:
    # 개별 HWPString이 완전한 BMP 문자/일반 숫자인 경우만 사용합니다.
    result: list[str] = []

    for item in items:
        try:
            raw = item.getBytes()
        except Exception:
            raw = None

        raw_bytes = _java_byte_array_to_bytes(raw)
        if not raw_bytes:
            continue

        try:
            value = raw_bytes.decode(
                "utf-16-le",
                errors="strict",
            )
        except UnicodeDecodeError:
            continue

        if not value or "\ufffd" in value:
            continue

        if value not in result:
            result.append(value)

    return result


def _raw_hwp_paragraph_text(paragraph: Any) -> str:
    """HWP 문단의 일반 문자열을 읽고, 검증된 PUA 치환만 적용합니다."""
    if paragraph is None:
        return ""

    try:
        text = paragraph.getNormalString()
        value = "" if text is None else str(text)
    except Exception:
        return ""

    # Parser 단계에서는 PUA를 숫자로 바꾸지 않고 원문 그대로 보존합니다.
    return value


def _extract_overlapping_payload(
    paragraph: Any,
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """글자 겹치기 컨트롤의 실제 표시 문자열을 보존해서 추출합니다.

    반환값:
      raw_value:
        ControlOverlappingLetter에 저장된 원래 문자열입니다.
        숫자뿐 아니라 PUA/특수기호도 그대로 반환합니다.

      numeric_value:
        raw_value가 명확한 숫자인 경우에만 일반 숫자 문자열을 반환합니다.
        표의 -1/-2 하위 번호 문맥 복원용 anchor로만 사용합니다.

      diagnostics:
        복원 근거 기록입니다.

    중요한 원칙:
    - PUA를 임의의 숫자로 추측하지 않습니다.
    - HWP 원본에 실제 저장된 겹침 문자열은 손실시키지 않습니다.
    """
    try:
        controls = paragraph.getControlList()
    except Exception:
        controls = None

    diagnostics: list[dict[str, Any]] = []
    if controls is None:
        return None, None, diagnostics

    for control in _iter_java_values(controls):
        class_name = java_class_name(control)
        lowered = class_name.lower()

        if not any(
            token in lowered
            for token in ("overlappingletter", "overlapping", "overlap", "compose")
        ):
            continue

        header_strings = _extract_overlapping_letter_strings(control)
        fallback_strings = _collect_control_strings(control)

        # Header 값이 실제 겹침 글자이므로 최우선으로 사용합니다.
        cleaned_header: list[str] = []
        for item in header_strings:
            value = unicodedata.normalize("NFKC", str(item))
            if value and value not in cleaned_header:
                cleaned_header.append(value)

        cleaned_fallback: list[str] = []
        for item in fallback_strings:
            value = unicodedata.normalize("NFKC", str(item))
            if value and value not in cleaned_fallback:
                cleaned_fallback.append(value)

        diagnostics.append(
            {
                "class_name": class_name,
                "header_strings": cleaned_header,
                "fallback_strings": cleaned_fallback,
            }
        )

        # HWP의 겹침글자는 여러 HWPString으로 분할 저장될 수 있습니다.
        # 순서를 유지하여 그대로 이어 붙입니다.
        if cleaned_header:
            raw_value = "".join(cleaned_header)
        elif cleaned_fallback:
            # fallback은 중복/내부값 가능성이 있으므로 첫 번째 값만 보수적으로 사용
            raw_value = cleaned_fallback[0]
        else:
            continue

        raw_value = raw_value.strip()
        if not raw_value:
            continue

        numeric_value: str | None = None

        # 실제 저장값 자체가 숫자로 명확한 경우에만 number anchor로 사용합니다.
        if re.fullmatch(r"\d{1,3}", raw_value):
            numeric_value = str(int(raw_value))

        return raw_value, numeric_value, diagnostics

    return None, None, diagnostics


def _recover_paragraph_number(
    paragraph: Any,
    raw_text: str,
) -> tuple[str, dict[str, Any] | None]:
    """글자 겹치기 문자열을 일반 텍스트에 다시 삽입합니다.

    예:
      ControlOverlappingLetter = "󰋗󰋣"
      getNormalString()         = "-2 파우더장"

      결과                    = "󰋗󰋣-2 파우더장"

    숫자 여부와 상관없이 원문 겹침 문자열 자체를 보존합니다.
    """
    overlap_value, numeric_value, diagnostics = _extract_overlapping_payload(
        paragraph
    )

    if not overlap_value:
        return raw_text, None

    stripped = raw_text.lstrip()
    leading_space = raw_text[: len(raw_text) - len(stripped)]

    # getNormalString()에 이미 동일한 문자열이 들어간 경우 중복 삽입 방지
    if stripped.startswith(overlap_value):
        return raw_text, None

    if stripped:
        # -1, -2처럼 바로 이어지는 하위 번호에는 공백을 넣지 않습니다.
        if re.match(r"^-\d+", stripped):
            recovered = f"{leading_space}{overlap_value}{stripped}"
        else:
            # 일반 본문 앞의 겹침 문자도 손실되지 않도록 보존합니다.
            recovered = f"{leading_space}{overlap_value}{stripped}"
    else:
        recovered = f"{leading_space}{overlap_value}"

    contains_pua = any(
        (
            0xE000 <= ord(char) <= 0xF8FF
            or 0xF0000 <= ord(char) <= 0xFFFFD
            or 0x100000 <= ord(char) <= 0x10FFFD
        )
        for char in overlap_value
    )

    recovery: dict[str, Any] = {
        "recovered": recovered != raw_text,
        "method": (
            "overlapping_letter_control"
            if numeric_value is not None
            else "overlapping_letter_raw"
        ),
        # prefix는 숫자로 검증된 경우에만 설정합니다.
        "prefix": numeric_value,
        # 원문 문자열 존재 자체는 확정적이지만 숫자 의미는 추측하지 않습니다.
        "confidence": 1.0,
        "overlapping_text": overlap_value,
        "controls": diagnostics,
    }

    if contains_pua:
        recovery["pua_characters"] = [
            {
                "character": char,
                "codepoint": f"U+{ord(char):05X}",
                "mapped_value": "",
            }
            for char in overlap_value
            if (
                0xE000 <= ord(char) <= 0xF8FF
                or 0xF0000 <= ord(char) <= 0xFFFFD
                or 0x100000 <= ord(char) <= 0x10FFFD
            )
        ]

    return recovered, recovery


def extract_hwp_paragraph_text(
    paragraph: Any,
    *,
    context: ParseContext | None = None,
    source: dict[str, Any] | None = None,
) -> str:
    if paragraph is None:
        return ''

    raw_text = _raw_hwp_paragraph_text(paragraph)
    recovered_text, recovery = _recover_paragraph_number(paragraph, raw_text)

    if recovery is not None and context is not None:
        context.warn(
            'HWP_OVERLAPPING_NUMBER_RECOVERED',
            '글자 겹치기 컨트롤에 저장된 원문 문자열을 문단 텍스트에 복원했습니다.',
            source={
                **(source or {}),
                'raw_text': raw_text,
                'recovered_text': recovered_text,
                'number_recovery': recovery,
            },
        )

    return recovered_text

def extract_cell_paragraphs(
    cell: Any,
    *,
    context: ParseContext,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    paragraphs_data: list[dict[str, Any]] = []

    try:
        paragraph_list = cell.getParagraphList()
    except Exception as error:
        context.warn(
            "HWP_CELL_PARAGRAPH_LIST_READ_FAILED",
            "HWP 셀의 ParagraphList를 읽지 못했습니다.",
            source=source,
            error=error,
        )
        return paragraphs_data

    if paragraph_list is None:
        return paragraphs_data

    try:
        paragraphs = paragraph_list.getParagraphs()

        for paragraph_index in range(len(paragraphs)):
            paragraph = paragraphs[paragraph_index]
            paragraph_source = {
                **source,
                "cell_paragraph_index": paragraph_index,
            }
            raw_text = _raw_hwp_paragraph_text(paragraph)
            text, recovery = _recover_paragraph_number(paragraph, raw_text)

            if recovery is not None:
                context.warn(
                    "HWP_OVERLAPPING_NUMBER_RECOVERED",
                    "글자 겹치기 컨트롤에 저장된 원문 문자열을 셀 문단에 복원했습니다.",
                    source={
                        **paragraph_source,
                        "raw_text": raw_text,
                        "recovered_text": text,
                        "number_recovery": recovery,
                    },
                )

            if text.strip():
                paragraph_data: dict[str, Any] = {
                    "paragraph_index": paragraph_index,
                    "text": text,
                }
                if recovery is not None:
                    paragraph_data["raw_text"] = raw_text
                    paragraph_data["number_recovery"] = recovery
                paragraphs_data.append(paragraph_data)

        return paragraphs_data

    except Exception as error:
        context.warn(
            "HWP_CELL_PARAGRAPHS_READ_FAILED",
            "HWP 셀의 문단 목록을 순회하지 못해 전체 텍스트 방식으로 대체합니다.",
            source=source,
            error=error,
        )

    try:
        fallback_text = paragraph_list.getNormalString()
    except Exception as error:
        context.warn(
            "HWP_CELL_TEXT_FALLBACK_FAILED",
            "HWP 셀의 대체 텍스트 추출도 실패했습니다.",
            source=source,
            error=error,
        )
        return paragraphs_data

    if fallback_text is not None and str(fallback_text).strip():
        paragraphs_data.append(
            {
                "paragraph_index": 0,
                "text": str(fallback_text),
            }
        )

    return paragraphs_data


def _cell_text(
    cell: Any,
    paragraphs: list[dict[str, Any]],
) -> str:
    text = "\n".join(
        str(paragraph.get("text", ""))
        for paragraph in paragraphs
        if str(paragraph.get("text", "")).strip()
    ).strip()

    if text:
        return text

    try:
        paragraph_list = cell.getParagraphList()
        fallback = paragraph_list.getNormalString() if paragraph_list else None
        return "" if fallback is None else str(fallback)
    except Exception:
        return ""


def find_nested_tables_in_hwp_cell(
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
        paragraph_list = cell.getParagraphList()
        paragraphs = paragraph_list.getParagraphs() if paragraph_list else None
    except Exception as error:
        context.warn(
            "HWP_NESTED_TABLE_SCAN_FAILED",
            "HWP 셀의 중첩 표 탐색을 시작하지 못했습니다.",
            source={
                "section_index": section_index,
                "parent_table_index": parent_table_index,
                "parent_cell": parent_cell,
            },
            error=error,
        )
        return nested_tables

    if paragraphs is None:
        return nested_tables

    for paragraph_index in range(len(paragraphs)):
        paragraph = paragraphs[paragraph_index]

        try:
            controls = paragraph.getControlList()
        except Exception:
            controls = None

        if controls is None:
            continue

        for control_index in range(len(controls)):
            control = controls[control_index]

            if not java_class_name(control).endswith(HWP_TABLE_CLASS_SUFFIX):
                continue

            table_index = context.allocate_table_index("nested_table")
            nested_path = [
                *object_path,
                f"cell:{parent_cell['row']},{parent_cell['col']}",
                f"paragraph:{paragraph_index}",
                f"table:{table_index}",
            ]
            source = {
                "section_index": section_index,
                "paragraph_index": paragraph_index,
                "control_index": control_index,
                "location": "nested_table",
                "parent_table_index": parent_table_index,
                "parent_cell": parent_cell,
                "nested_depth": depth + 1,
                "object_path": nested_path,
            }

            nested_tables.append(
                parse_table(
                    table=control,
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
            row_list = table.getRowList()
        except Exception as error:
            context.warn(
                "HWP_TABLE_ROWS_READ_FAILED",
                "HWP 표의 행 목록을 읽지 못했습니다.",
                source=source,
                error=error,
                fatal_in_strict=True,
            )
            return result

        if row_list is None:
            return result

        cells: list[dict[str, Any]] = []

        for row_list_index in range(len(row_list)):
            row = row_list[row_list_index]

            try:
                cell_list = row.getCellList()
            except Exception as error:
                context.warn(
                    "HWP_TABLE_CELL_LIST_READ_FAILED",
                    "HWP 표 행의 셀 목록을 읽지 못했습니다.",
                    source={**source, "row_list_index": row_list_index},
                    error=error,
                )
                continue

            if cell_list is None:
                continue

            for cell_list_index in range(len(cell_list)):
                cell = cell_list[cell_list_index]
                cell_scan_source = {
                    **source,
                    "row_list_index": row_list_index,
                    "cell_list_index": cell_list_index,
                }

                try:
                    header = cell.getListHeader()
                    actual_row = int(header.getRowIndex())
                    actual_col = int(header.getColIndex())
                    row_span = max(1, int(header.getRowSpan()))
                    col_span = max(1, int(header.getColSpan()))
                except Exception as error:
                    context.warn(
                        "HWP_CELL_ADDRESS_READ_FAILED",
                        "HWP 셀의 좌표 또는 병합 정보를 읽지 못해 해당 셀을 제외했습니다.",
                        source=cell_scan_source,
                        error=error,
                        fatal_in_strict=True,
                    )
                    continue

                parent_cell = {
                    "row": actual_row,
                    "col": actual_col,
                }
                cell_source = {
                    **cell_scan_source,
                    **parent_cell,
                }
                paragraphs = extract_cell_paragraphs(
                    cell,
                    context=context,
                    source=cell_source,
                )
                nested_tables = find_nested_tables_in_hwp_cell(
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
                        "text": _cell_text(cell, paragraphs),
                        "paragraphs": paragraphs,
                        "nested_tables": nested_tables,
                    }
                )
                context.add_cell()

        row_count = max(
            (cell["row"] + cell["row_span"] for cell in cells),
            default=0,
        )
        col_count = max(
            (cell["col"] + cell["col_span"] for cell in cells),
            default=0,
        )

        recover_hwp_table_item_numbers(
            cells,
            context=context,
            source=source,
        )

        result.update(
            {
                "row_count": row_count,
                "col_count": col_count,
                "cells": cells,
            }
        )
        return result

    finally:
        context.exit_table(table)


def parse_hwp(
    hwp_jar_path: str | Path | None,
    hwp_file_path: str | Path,
    *,
    original_filename: str | None = None,
    max_nested_depth: int = 10,
    strict: bool = False,
) -> dict[str, Any]:
    jar_path = resolve_jar_path("hwp", hwp_jar_path)
    file_path = validate_document_path(hwp_file_path, ".hwp")

    ensure_jvm(
        [jar_path],
        required_classes=[HWP_READER_CLASS],
    )

    reader = jpype.JClass(HWP_READER_CLASS)
    hwp_file = reader.fromFile(str(file_path))

    if hwp_file is None:
        raise RuntimeError(f"HWP 파일 파싱에 실패했습니다: {file_path}")

    context = ParseContext(
        max_nested_depth=max_nested_depth,
        strict=strict,
    )
    document = build_document_header(
        file_path,
        document_format="hwp",
        engine="hwplib",
        jar_path=jar_path,
    )

    if original_filename:
        document["document"]["filename"] = original_filename

    try:
        body_text = hwp_file.getBodyText()
        sections = body_text.getSectionList()
    except Exception as error:
        raise RuntimeError(
            f"HWP 본문 Section 목록을 읽지 못했습니다: {file_path}"
        ) from error

    for section_index in range(len(sections)):
        section = sections[section_index]
        section_data: dict[str, Any] = {
            "section_index": section_index,
            "blocks": [],
        }

        try:
            paragraphs = section.getParagraphs()
        except Exception as error:
            context.warn(
                "HWP_SECTION_PARAGRAPHS_READ_FAILED",
                "HWP Section의 문단 목록을 읽지 못했습니다.",
                source={"section_index": section_index},
                error=error,
                fatal_in_strict=True,
            )
            document["sections"].append(section_data)
            continue

        for paragraph_index in range(len(paragraphs)):
            paragraph = paragraphs[paragraph_index]
            paragraph_source = {
                "section_index": section_index,
                "paragraph_index": paragraph_index,
                "location": "top_level",
            }
            text = extract_hwp_paragraph_text(
                paragraph,
                context=context,
                source=paragraph_source,
            )

            if text.strip():
                section_data["blocks"].append(
                    {
                        "type": "paragraph",
                        "paragraph_index": paragraph_index,
                        "text": text,
                        "source": paragraph_source,
                    }
                )
                context.add_paragraph()

            try:
                controls = paragraph.getControlList()
            except Exception:
                controls = None

            if controls is None:
                continue

            for control_index in range(len(controls)):
                control = controls[control_index]

                if not java_class_name(control).endswith(HWP_TABLE_CLASS_SUFFIX):
                    continue

                table_index = context.allocate_table_index("top_level")
                object_path = [
                    f"section:{section_index}",
                    f"paragraph:{paragraph_index}",
                    f"table:{table_index}",
                ]
                source = {
                    "section_index": section_index,
                    "paragraph_index": paragraph_index,
                    "control_index": control_index,
                    "location": "top_level",
                    "nested_depth": 0,
                    "object_path": object_path,
                }
                section_data["blocks"].append(
                    parse_table(
                        table=control,
                        table_index=table_index,
                        context=context,
                        source=source,
                        depth=0,
                        object_path=object_path,
                    )
                )

        document["sections"].append(section_data)

    document["statistics"] = context.statistics(len(document["sections"]))
    document["warnings"] = context.warnings
    return document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="hwplib를 이용해 HWP를 중첩 표 포함 Raw JSON으로 변환합니다."
    )
    parser.add_argument(
        "--hwp_jar_path",
        default=None,
        help="생략 시 환경변수 또는 libs/hwp의 단일 JAR를 자동 탐색합니다.",
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

    result = parse_hwp(
        hwp_jar_path=args.hwp_jar_path,
        hwp_file_path=args.file_path,
        original_filename=args.original_filename,
        max_nested_depth=args.max_nested_depth,
        strict=args.strict,
    )
    output_path = save_json(result, args.output_path)

    print("=" * 80)
    print("HWP 파싱 완료")
    print("=" * 80)
    print(f"파일: {result['document']['filename']}")
    statistics = result.get("statistics", {})
    print(f"Section 수: {statistics.get('section_count', len(result.get('sections', [])))}")
    print(f"일반 문단 수: {statistics.get('paragraph_count', statistics.get('top_level_paragraph_count', 0))}")
    print(f"최상위 표 수: {statistics.get('top_level_table_count', 0)}")
    print(f"중첩 표 수: {statistics.get('nested_table_count', 0)}")
    print(f"경고 수: {statistics.get('warning_count', len(result.get('warnings', [])))}")
    print(f"출력: {output_path}")


if __name__ == "__main__":
    main()
