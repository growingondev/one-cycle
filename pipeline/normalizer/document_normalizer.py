from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# 프로젝트 공통 경로 설정 불러오기
# ============================================================
#
# 사용자 PC의 절대 경로나 특정 공고 ID를 코드에 작성하지 않습니다.
# 이 파일의 위치를 기준으로 프로젝트 루트를 계산한 뒤,
# 프로젝트의 단일 경로 설정 파일인 config.paths를 사용합니다.
#
# run_pipeline.py처럼 이 파일을 직접 실행해도 config 패키지를
# 찾을 수 있도록 프로젝트 루트를 sys.path에 추가합니다.
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.paths import (
        get_document_output_paths,
    )
except ImportError as error:
    raise RuntimeError(
        "프로젝트의 config.paths를 불러오지 못했습니다. "
        "document_normalizer.py를 one-cycle/pipeline/normalizer 폴더에 두고 실행하세요."
    ) from error


# ============================================================
# Normalizer 기본 설정
# ============================================================
NORMALIZER_NAME = "document_normalizer"
NORMALIZER_VERSION = "1.6"
SUPPORTED_DOCUMENT_FORMATS = {"hwp", "hwpx"}

# config.paths에서 관리하는 단계 폴더명을 사용합니다.
# 문자열을 Normalizer 내부에 중복 하드코딩하지 않기 위한 값입니다.
_PATH_TEMPLATE = get_document_output_paths("_normalizer_path_template")
PARSED_STAGE_DIRECTORY_NAME = _PATH_TEMPLATE.parsed.name


# ============================================================
# 검증된 Private Use Area 문자 매핑
# ============================================================
# 실제 원본 문서에서 문자의 의미를 확인한 경우에만 추가합니다.
#
# 예:
# VERIFIED_PRIVATE_USE_MAP = {
#     "\U000F02D6": "▶",
#     "\U000F021D": "○",
# }
#
# 주의:
# - 검증되지 않은 PUA 문자를 임의로 변경하지 않습니다.
# - replacement character인 '�'도 임의로 치환하지 않습니다.
# ============================================================
VERIFIED_PRIVATE_USE_MAP: dict[str, str] = {}


# ============================================================
# 안전한 특수문자 치환 정책
# ============================================================
# 원문 의미 손실 가능성이 낮다고 확인된 문자만 등록합니다.
# ZWNJ(\u200C), ZWJ(\u200D), Word Joiner(\u2060)는
# 언어와 문맥에 따라 의미가 있을 수 있으므로 기본 제거 대상에서 제외합니다.
SAFE_CHARACTER_REPLACEMENTS: dict[str, str] = {
    "\u00A0": " ",  # Non-breaking space → 일반 공백
    "\u200B": "",   # Zero-width space 제거
    "\uFEFF": "",   # BOM 제거

    # HWP/HWPX 파서가 서로 다르게 반환하는 구두점 표현을 통일합니다.
    "\u2024": ".",  # ONE DOT LEADER(․) → 마침표
    "\u2027": "·",  # HYPHENATION POINT(‧) → 가운데점

    # 동그라미 숫자는 HWP에서 일반 숫자로 추출되는 경우가 있어 숫자로 통일합니다.
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",

    # HWP에서 초성 자모로 반환되는 문자를 호환 자모로 통일합니다.
    "ᄀ": "ㄱ",
    "ᄁ": "ㄲ",
    "ᄂ": "ㄴ",
    "ᄃ": "ㄷ",
    "ᄄ": "ㄸ",
    "ᄅ": "ㄹ",
    "ᄆ": "ㅁ",
    "ᄇ": "ㅂ",
    "ᄈ": "ㅃ",
    "ᄉ": "ㅅ",
    "ᄊ": "ㅆ",
    "ᄋ": "ㅇ",
    "ᄌ": "ㅈ",
    "ᄍ": "ㅉ",
    "ᄎ": "ㅊ",
    "ᄏ": "ㅋ",
    "ᄐ": "ㅌ",
    "ᄑ": "ㅍ",
    "ᄒ": "ㅎ",
}


# ============================================================
# Source Metadata 분류 기준
# ============================================================
# HWP와 HWPX에 공통으로 존재하며 후속 단계에서도 사용할 정보입니다.
COMMON_SOURCE_KEYS = {
    "section_index",
    "paragraph_index",
    "location",
    "parent_table_index",
    "parent_cell",
    "nested_depth",
    "object_path",
}

# 원본 포맷 내부의 객체 위치를 추적하기 위한 정보입니다.
FORMAT_SPECIFIC_SOURCE_KEYS = {
    "control_index",   # HWP
    "run_index",       # HWPX
    "item_index",      # HWPX
    "start_position",  # HWPX Paragraph segment
    "end_position",    # HWPX Paragraph segment
}


# ============================================================
# 공통 보조 함수
# ============================================================
def deep_copy(value: Any) -> Any:
    """입력 Parser JSON을 변경하지 않도록 값을 깊은 복사합니다."""
    return copy.deepcopy(value)


def as_dict(value: Any) -> dict[str, Any]:
    """dict가 아니면 안전한 빈 dict를 반환합니다."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """list가 아니면 안전한 빈 list를 반환합니다."""
    return value if isinstance(value, list) else []


def collect_extra_fields(
    source: dict[str, Any],
    known_keys: set[str],
) -> dict[str, Any]:
    """
    향후 Parser에 필드가 추가되어도 정규화 과정에서 유실되지 않도록
    현재 Normalizer가 직접 처리하지 않는 필드를 별도로 보존합니다.
    """
    return {
        key: deep_copy(value)
        for key, value in source.items()
        if key not in known_keys
    }


def normalize_optional_integer(
    value: Any,
    *,
    default: int | None = None,
    minimum: int | None = None,
) -> int | None:
    """
    정수 또는 정수 문자열을 공통 int로 변환합니다.

    변환할 수 없거나 minimum보다 작으면 default를 반환합니다.
    bool은 int의 하위 타입이지만 인덱스로 사용하는 값이 아니므로 제외합니다.
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError):
        return default

    if minimum is not None and normalized < minimum:
        return default

    return normalized


def normalize_boolean(value: Any, *, default: bool = False) -> bool:
    """문자열을 포함한 bool 표현을 안전하게 공통 bool로 변환합니다."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False

    return default


# ============================================================
# 정규화 실행 상태 및 통계
# ============================================================
@dataclass
class NormalizationContext:
    """한 문서의 정규화 통계와 경고를 관리합니다."""

    strict: bool = False
    section_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    cell_count: int = 0
    image_count: int = 0
    empty_cell_count: int = 0
    image_only_cell_count: int = 0
    unknown_block_count: int = 0
    unverified_pua_count: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    _reported_unverified_pua: set[str] = field(
        default_factory=set,
        repr=False,
    )

    def warn(
        self,
        code: str,
        message: str,
        *,
        source: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        fatal_in_strict: bool = False,
    ) -> None:
        warning: dict[str, Any] = {
            "stage": "normalizer",
            "code": code,
            "message": message,
        }

        if source:
            warning["source"] = deep_copy(source)

        if details:
            warning["details"] = deep_copy(details)

        self.warnings.append(warning)

        if self.strict and fatal_in_strict:
            raise ValueError(f"[{code}] {message}")

    def statistics(self) -> dict[str, int]:
        return {
            "section_count": self.section_count,
            "paragraph_count": self.paragraph_count,
            "table_count": self.table_count,
            "cell_count": self.cell_count,
            "image_count": self.image_count,
            "empty_cell_count": self.empty_cell_count,
            "image_only_cell_count": self.image_only_cell_count,
            "unknown_block_count": self.unknown_block_count,
            "unverified_pua_count": self.unverified_pua_count,
            "warning_count": len(self.warnings),
        }


# ============================================================
# JSON 로드
# ============================================================
def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(
            f"JSON 파일을 찾을 수 없습니다: {file_path}"
        )

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON 파일입니다: {file_path} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            f"JSON 최상위 값은 객체여야 합니다: {file_path}"
        )

    return data


# ============================================================
# JSON 저장
# ============================================================
def save_json(
    data: dict[str, Any],
    path: str | Path,
) -> Path:
    file_path = Path(path).expanduser().resolve()

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return file_path


# ============================================================
# 제어문자 정규화
# ============================================================
def normalize_control_characters(text: str) -> str:
    """
    텍스트 해석에 방해되는 C0 제어문자를 제거합니다.

    줄바꿈(\\n), 탭(\\t), 캐리지 리턴(\\r)은 뒤 단계에서 처리하므로
    여기서는 보존합니다.
    """
    if not text:
        return ""

    return re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        "",
        text,
    )


# ============================================================
# 기본 특수문자 정규화
# ============================================================
def normalize_measurement_units(text: str) -> str:
    """HWP/HWPX에서 다르게 추출되는 면적·부피 단위를 통일합니다.

    변환 예:
        55m2, 55 m2, 55m^2, 55m² -> 55㎡
        10m3, 10 m3, 10m^3, 10m³ -> 10㎥

    영문 단어의 일부를 잘못 바꾸지 않도록 숫자 뒤 단위 표현만 처리합니다.
    """
    if not text:
        return ""

    # 숫자와 단위가 붙어 있거나 공백이 있는 경우를 모두 처리합니다.
    # 뒤에 한글 조사/조건(이하, 이상, 초과 등)이 바로 붙어도 변환합니다.
    # 예: 60m2이하 -> 60㎡이하, 84.95 m² 이상 -> 84.95㎡ 이상
    text = re.sub(
        r"(?i)(?P<value>\d+(?:[.,]\d+)?)\s*m(?:\^?2|²)(?![A-Za-z0-9])",
        lambda match: f"{match.group('value')}㎡",
        text,
    )
    text = re.sub(
        r"(?i)(?P<value>\d+(?:[.,]\d+)?)\s*m(?:\^?3|³)(?![A-Za-z0-9])",
        lambda match: f"{match.group('value')}㎥",
        text,
    )

    # 표 머리글처럼 숫자 없이 단위만 쓰인 표현도 처리합니다.
    # 예: 주택면적(m2) -> 주택면적(㎡)
    text = re.sub(
        r"(?i)(?<![A-Za-z0-9])m(?:\^?2|²)(?![A-Za-z0-9])",
        "㎡",
        text,
    )
    text = re.sub(
        r"(?i)(?<![A-Za-z0-9])m(?:\^?3|³)(?![A-Za-z0-9])",
        "㎥",
        text,
    )
    return text


def normalize_special_characters(text: str) -> str:
    """
    의미 손실 위험이 낮은 문자만 정규화합니다.

    처리:
    - Non-breaking space → 일반 공백
    - Zero-width space 제거
    - BOM 제거

    처리하지 않는 항목:
    - HWP에서 깨진 문자 '�'
    - 검증되지 않은 PUA 문자
    - ZWNJ, ZWJ, Word Joiner
    - 따옴표, 대시처럼 문맥에 따라 의미가 달라질 수 있는 문자
    """
    if not text:
        return ""

    for source, target in SAFE_CHARACTER_REPLACEMENTS.items():
        text = text.replace(source, target)

    return text


# ============================================================
# 검증된 Private Use Area 문자 정규화
# ============================================================
def is_private_use_character(character: str) -> bool:
    """문자가 Unicode Private Use Area에 속하는지 확인합니다."""
    code_point = ord(character)
    return (
        0xE000 <= code_point <= 0xF8FF
        or 0xF0000 <= code_point <= 0xFFFFD
        or 0x100000 <= code_point <= 0x10FFFD
    )


def find_private_use_characters(text: str) -> list[str]:
    """텍스트에 포함된 PUA 문자를 코드 포인트 순으로 반환합니다."""
    return sorted(
        {
            character
            for character in text
            if is_private_use_character(character)
        },
        key=ord,
    )


def normalize_verified_private_use_characters(
    text: str,
    *,
    context: NormalizationContext | None = None,
    source: dict[str, Any] | None = None,
) -> str:
    """
    검증된 PUA 문자만 치환합니다.

    매핑되지 않은 PUA 문자는 삭제하거나 추측해 바꾸지 않고 원문 그대로
    보존합니다. 같은 문자에 대한 경고는 문서당 한 번만 기록합니다.
    """
    if not text:
        return ""

    for character in find_private_use_characters(text):
        if character in VERIFIED_PRIVATE_USE_MAP:
            continue

        if (
            context is not None
            and character not in context._reported_unverified_pua
        ):
            context._reported_unverified_pua.add(character)
            context.unverified_pua_count += 1
            context.warn(
                "UNVERIFIED_PRIVATE_USE_CHARACTER",
                "검증되지 않은 PUA 문자가 발견되어 원문 그대로 보존했습니다.",
                source=source,
                details={
                    "character": character,
                    "code_point": f"U+{ord(character):04X}",
                    "python_escape": f"\\U{ord(character):08X}",
                },
                fatal_in_strict=False,
            )

    for original, replacement in VERIFIED_PRIVATE_USE_MAP.items():
        text = text.replace(original, replacement)

    return text


# ============================================================
# 글머리표 공백 정규화
# ============================================================
def normalize_bullet_spacing(text: str) -> str:
    """
    각 줄 시작 글머리표 뒤 공백을 정확히 한 칸으로 통일합니다.

    예:
        ■전화상담
        ■  전화상담
        ■   전화상담

    결과:
        ■ 전화상담

    글머리표 하나만 있는 줄은 뒤에 공백을 추가하지 않으며,
    문장 중간에 있는 기호는 변경하지 않습니다.
    """
    if not text:
        return ""

    # 실제 공공문서에서 반복적으로 사용되는 기호만 제한적으로 처리합니다.
    bullet_pattern = re.compile(
        r"^(\s*)(■|□|●|○|◆|◇|▶|▷|❚)\s*"
    )

    normalized_lines: list[str] = []

    for line in text.split("\n"):
        match = bullet_pattern.match(line)

        if match:
            indent, bullet = match.groups()
            remainder = line[match.end():]

            if remainder.strip():
                line = f"{indent}{bullet} {remainder}"
            else:
                line = f"{indent}{bullet}"

        normalized_lines.append(line)

    return "\n".join(normalized_lines)


# ============================================================
# 일반 텍스트 정규화
# ============================================================
def normalize_text(text: Any) -> str:
    """
    서비스에서 공통으로 사용할 텍스트 표현을 정규화합니다.

    처리:
    - None → 빈 문자열
    - CRLF / CR → LF
    - 탭 → 일반 공백
    - 줄 내부의 연속된 일반 공백 축소
    - 각 줄 앞뒤 공백 제거
    - 내용이 없는 빈 줄 제거

    주의:
    - 내용이 있는 문단 사이의 줄바꿈은 유지합니다.
    - 제목 판단, 문장 결합, 의미 분석은 수행하지 않습니다.
    """
    if text is None:
        return ""

    text = str(text)

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\t", " ")

    normalized_lines: list[str] = []

    for line in text.split("\n"):
        line = re.sub(r"[ ]+", " ", line)
        line = line.strip()

        if not line:
            continue

        normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()


# ============================================================
# 로마 숫자 표기 통일
# ============================================================
ASCII_ROMAN_TO_UNICODE: dict[str, str] = {
    "VIII": "Ⅷ",
    "VII": "Ⅶ",
    "VI": "Ⅵ",
    "IV": "Ⅳ",
    "III": "Ⅲ",
    "II": "Ⅱ",
    "IX": "Ⅸ",
    "X": "Ⅹ",
    "V": "Ⅴ",
    "I": "Ⅰ",
}


def normalize_roman_numerals(text: str) -> str:
    """장·절 번호로 사용된 ASCII 로마 숫자를 Unicode 로마 숫자로 통일합니다.

    영문 단어 내부의 I, V, X 등은 변경하지 않습니다. 다음 경우만 변환합니다.
    - 문자열 전체가 I~X인 경우
    - 각 줄의 시작에서 로마 숫자 뒤에 공백이나 구분 기호가 오는 경우
    """
    if not text:
        return ""

    normalized_lines: list[str] = []
    pattern = re.compile(
        r"^(?P<indent>\s*)(?P<roman>VIII|VII|VI|IV|III|II|IX|X|V|I)"
        r"(?P<boundary>$|[\s.．、:：)）-])"
    )

    for line in text.split("\n"):
        match = pattern.match(line)
        if match:
            roman = match.group("roman")
            replacement = ASCII_ROMAN_TO_UNICODE.get(roman, roman)
            start, end = match.span("roman")
            line = line[:start] + replacement + line[end:]
        normalized_lines.append(line)

    return "\n".join(normalized_lines)


# ============================================================
# 최종 콘텐츠 텍스트 정규화
# ============================================================
def normalize_content_text(
    text: Any,
    *,
    context: NormalizationContext | None = None,
    source: dict[str, Any] | None = None,
) -> str:
    """
    문단과 셀 콘텐츠에 적용되는 전체 정규화 흐름입니다.

    순서:
    1. C0 제어문자 제거
    2. 안전한 특수문자 처리
    3. 면적·부피 단위 통일
    4. 장·절 로마 숫자를 Ⅰ·Ⅱ·Ⅲ 형식으로 통일
    5. 검증된 PUA 문자 처리 및 미검증 문자 기록
    6. 글머리표 공백 처리
    7. 일반 공백과 개행 처리
    """
    value = "" if text is None else str(text)
    value = normalize_control_characters(value)
    value = normalize_special_characters(value)
    value = normalize_measurement_units(value)
    value = normalize_roman_numerals(value)
    value = normalize_verified_private_use_characters(
        value,
        context=context,
        source=source,
    )
    value = normalize_bullet_spacing(value)
    value = normalize_text(value)

    return value


# ============================================================
# 검색용 문자열 생성
# ============================================================
UNICODE_ROMAN_TO_ASCII: dict[str, str] = {
    "Ⅰ": "I",
    "Ⅱ": "II",
    "Ⅲ": "III",
    "Ⅳ": "IV",
    "Ⅴ": "V",
    "Ⅵ": "VI",
    "Ⅶ": "VII",
    "Ⅷ": "VIII",
    "Ⅸ": "IX",
    "Ⅹ": "X",
}


def build_search_text(text: Any) -> str:
    """정규화된 표시 문자열에서 검색용 별칭 문자열을 생성합니다.

    표시용 ``text``는 Unicode 로마 숫자와 표준 단위를 유지합니다.
    ``search_text``에는 다음 ASCII 별칭을 추가합니다.

    - Ⅰ·Ⅱ·Ⅲ ... → I·II·III ...
    - ㎡·㎥ → m2·m3

    중요: 이 함수의 반환값은 다시 ``normalize_content_text``에 넣지 않습니다.
    다시 정규화하면 ASCII 로마 숫자 별칭이 Unicode 표기로 되돌아갑니다.
    """
    normalized = "" if text is None else str(text).strip()
    if not normalized:
        return ""

    aliases: list[str] = [normalized]

    ascii_alias = normalized
    for unicode_roman, ascii_roman in UNICODE_ROMAN_TO_ASCII.items():
        ascii_alias = ascii_alias.replace(unicode_roman, ascii_roman)

    ascii_alias = ascii_alias.replace("㎡", "m2").replace("㎥", "m3")

    if ascii_alias != normalized:
        aliases.append(ascii_alias)

    return " ".join(dict.fromkeys(aliases))


# ============================================================
# 셀 좌표와 병합 범위 검증
# ============================================================
def normalize_cell_position(
    value: Any,
    *,
    field_name: str,
    context: NormalizationContext,
    source: dict[str, Any] | None = None,
) -> int | None:
    """row/col을 0 이상의 정수로 검증합니다."""
    normalized = normalize_optional_integer(
        value,
        default=None,
        minimum=0,
    )

    if normalized is None:
        context.warn(
            "INVALID_CELL_POSITION",
            f"{field_name} 값을 0 이상의 정수로 정규화하지 못했습니다.",
            source=source,
            details={
                "field": field_name,
                "original_value": deep_copy(value),
            },
            fatal_in_strict=True,
        )

    return normalized


def normalize_cell_span(
    value: Any,
    *,
    field_name: str,
    context: NormalizationContext,
    source: dict[str, Any] | None = None,
) -> int:
    """
    row_span/col_span을 1 이상의 정수로 검증합니다.

    일반 모드에서는 비정상 값을 경고와 함께 1로 보정하고,
    strict 모드에서는 오류를 발생시킵니다.
    """
    normalized = normalize_optional_integer(
        value,
        default=None,
        minimum=1,
    )

    if normalized is not None:
        return normalized

    context.warn(
        "INVALID_CELL_SPAN",
        f"{field_name} 값은 1 이상의 정수여야 하므로 1로 보정했습니다.",
        source=source,
        details={
            "field": field_name,
            "original_value": deep_copy(value),
            "normalized_value": 1,
        },
        fatal_in_strict=True,
    )
    return 1


# ============================================================
# Source Metadata 정규화
# ============================================================
def normalize_source(
    source: dict[str, Any] | None,
    document_format: str,
    section_index: int | None,
) -> dict[str, Any]:
    """
    HWP/HWPX 공통 위치 정보와 포맷별 위치 정보를 분리합니다.

    중요:
    중첩 표의 source.section_index가 없거나 None인 경우에는
    현재 부모 Section의 section_index를 상속합니다.
    """
    raw = source if isinstance(source, dict) else {}

    source_section_index = raw.get("section_index")
    if source_section_index is None:
        source_section_index = section_index

    normalized: dict[str, Any] = {
        "section_index": normalize_optional_integer(
            source_section_index,
            default=section_index,
            minimum=0,
        ),
        "paragraph_index": normalize_optional_integer(
            raw.get("paragraph_index"),
            default=None,
            minimum=0,
        ),
        "location": raw.get("location"),
        "format": document_format,
        "format_specific": {},
    }

    # --------------------------------------------------------
    # HWP/HWPX 공통 구조 위치 정보
    # --------------------------------------------------------
    if "parent_table_index" in raw:
        normalized["parent_table_index"] = normalize_optional_integer(
            raw.get("parent_table_index"),
            default=None,
            minimum=0,
        )

    if "parent_cell" in raw:
        parent_cell = as_dict(raw.get("parent_cell"))
        normalized["parent_cell"] = {
            "row": normalize_optional_integer(
                parent_cell.get("row"),
                default=None,
                minimum=0,
            ),
            "col": normalize_optional_integer(
                parent_cell.get("col"),
                default=None,
                minimum=0,
            ),
        }

    if "nested_depth" in raw:
        normalized["nested_depth"] = normalize_optional_integer(
            raw.get("nested_depth"),
            default=0,
            minimum=0,
        )

    if "object_path" in raw:
        object_path = raw.get("object_path")
        normalized["object_path"] = (
            [str(item) for item in object_path]
            if isinstance(object_path, list)
            else []
        )

    # --------------------------------------------------------
    # 파일 형식별 원본 위치 정보
    # --------------------------------------------------------
    format_specific: dict[str, Any] = {}

    for key in FORMAT_SPECIFIC_SOURCE_KEYS:
        if key in raw:
            format_specific[key] = deep_copy(raw[key])

    # Parser가 향후 source 필드를 추가해도 데이터가 사라지지 않게 보존합니다.
    known_keys = COMMON_SOURCE_KEYS | FORMAT_SPECIFIC_SOURCE_KEYS
    extra = collect_extra_fields(raw, known_keys)

    if extra:
        format_specific["extra"] = extra

    normalized["format_specific"] = format_specific

    return normalized


# ============================================================
# Image Metadata 정규화
# ============================================================
def normalize_image(
    image: Any,
    fallback_index: int,
    context: NormalizationContext,
) -> dict[str, Any]:
    """
    Parser에서 탐지한 이미지 존재 정보를 공통 구조로 보존합니다.

    현재 Parser는 이미지 파일 자체를 추출하지 않으므로 extracted와
    ocr_applied는 보통 False입니다. 이후 image_path, media_type,
    ocr_text 등이 추가되어도 extra가 아니라 원래 필드명으로 보존합니다.
    """
    if not isinstance(image, dict):
        context.warn(
            "INVALID_IMAGE_METADATA",
            "이미지 메타데이터가 객체가 아니어서 기본값으로 정규화했습니다.",
            details={"fallback_index": fallback_index},
        )
        raw: dict[str, Any] = {}
    else:
        raw = image

    normalized: dict[str, Any] = {
        "image_index": normalize_optional_integer(
            raw.get("image_index"),
            default=fallback_index,
            minimum=0,
        ),
        "type": str(raw.get("type") or "embedded_image"),
        "extracted": normalize_boolean(
            raw.get("extracted"),
            default=False,
        ),
        "ocr_applied": normalize_boolean(
            raw.get("ocr_applied"),
            default=False,
        ),
    }

    # 향후 이미지 추출/OCR 필드가 추가되어도 같은 이름으로 보존합니다.
    for key, value in raw.items():
        if key not in normalized:
            normalized[key] = deep_copy(value)

    return normalized


# ============================================================
# Paragraph 정규화
# ============================================================
def normalize_paragraph(
    paragraph: dict[str, Any],
    document_format: str,
    section_index: int | None,
    context: NormalizationContext,
) -> dict[str, Any]:
    """Paragraph를 Common JSON 구조로 정규화합니다."""
    context.paragraph_count += 1

    paragraph_source = as_dict(paragraph.get("source"))

    normalized_text = normalize_content_text(
        paragraph.get("text", ""),
        context=context,
        source=paragraph_source,
    )

    normalized: dict[str, Any] = {
        "type": "paragraph",
        "paragraph_index": normalize_optional_integer(
            paragraph.get("paragraph_index"),
            default=None,
            minimum=0,
        ),
        "text": normalized_text,
        "search_text": build_search_text(normalized_text),
    }

    # 최상위 Paragraph에는 Parser source가 있으므로 보존합니다.
    if "source" in paragraph:
        normalized["source"] = normalize_source(
            paragraph_source,
            document_format,
            section_index,
        )

    extra = collect_extra_fields(
        paragraph,
        {
            "type",
            "paragraph_index",
            "text",
            "search_text",
            "source",
        },
    )

    if extra:
        normalized["extra"] = extra

    return normalized


# ============================================================
# Cell 내부 Blocks 생성
# ============================================================
def build_cell_blocks(
    paragraphs: list[Any],
    nested_tables: list[Any],
    document_format: str,
    section_index: int | None,
    context: NormalizationContext,
) -> list[dict[str, Any]]:
    """
    Parser Cell 내부의 paragraphs[]와 nested_tables[]를
    하나의 blocks[] 배열로 병합합니다.

    paragraph_index 수준의 순서를 복원합니다.
    같은 paragraph_index에서는 Paragraph를 Nested Table보다 먼저 둡니다.

    제한:
    Parser가 동일 Paragraph 내부의 정확한 Run/Control 순서를 별도 필드로
    제공하지 않는 경우 text → table → text와 같은 inline 순서는
    Normalizer에서 완전히 복원할 수 없습니다.
    """
    indexed_blocks: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # Paragraph Blocks
    # --------------------------------------------------------
    for order, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            context.warn(
                "INVALID_CELL_PARAGRAPH",
                "셀 내부 Paragraph가 객체가 아니어서 제외했습니다.",
                details={"original_order": order},
            )
            continue

        paragraph_index = normalize_optional_integer(
            paragraph.get("paragraph_index"),
            default=None,
            minimum=0,
        )

        indexed_blocks.append(
            {
                "paragraph_index": paragraph_index,
                "type_priority": 0,
                "original_order": order,
                "block": normalize_paragraph(
                    paragraph,
                    document_format,
                    section_index,
                    context,
                ),
            }
        )

    # --------------------------------------------------------
    # Nested Table Blocks
    # --------------------------------------------------------
    for order, table in enumerate(nested_tables):
        if not isinstance(table, dict):
            context.warn(
                "INVALID_NESTED_TABLE",
                "중첩 표가 객체가 아니어서 제외했습니다.",
                details={"original_order": order},
            )
            continue

        table_source = as_dict(table.get("source"))
        paragraph_index = normalize_optional_integer(
            table_source.get("paragraph_index"),
            default=None,
            minimum=0,
        )

        indexed_blocks.append(
            {
                "paragraph_index": paragraph_index,
                "type_priority": 1,
                "original_order": order,
                "block": normalize_table(
                    table,
                    document_format,
                    section_index,
                    context,
                ),
            }
        )

    # --------------------------------------------------------
    # Block 정렬
    # --------------------------------------------------------
    def sort_key(item: dict[str, Any]) -> tuple[float, int, int]:
        paragraph_index = item["paragraph_index"]

        if paragraph_index is None:
            sortable_index = float("inf")
        else:
            sortable_index = float(paragraph_index)

        return (
            sortable_index,
            int(item["type_priority"]),
            int(item["original_order"]),
        )

    indexed_blocks.sort(key=sort_key)

    return [
        item["block"]
        for item in indexed_blocks
    ]


# ============================================================
# Cell 정규화
# ============================================================
def normalize_cell(
    cell: dict[str, Any],
    document_format: str,
    section_index: int | None,
    context: NormalizationContext,
) -> dict[str, Any]:
    """
    Table Cell을 Common JSON 구조로 정규화합니다.

    Parser:
        paragraphs[]
        nested_tables[]
        images[]

    Normalizer:
        blocks[]
        images[]

    images[]를 blocks[]에 억지로 합치지 않는 이유는 현재 Parser 결과만으로는
    이미지의 정확한 inline 순서를 확인할 수 없기 때문입니다.
    """
    context.cell_count += 1

    paragraphs = as_list(cell.get("paragraphs"))
    nested_tables = as_list(cell.get("nested_tables"))
    raw_images = as_list(cell.get("images"))

    blocks = build_cell_blocks(
        paragraphs,
        nested_tables,
        document_format,
        section_index,
        context,
    )

    images = [
        normalize_image(
            image,
            fallback_index=image_index,
            context=context,
        )
        for image_index, image in enumerate(raw_images)
    ]

    context.image_count += len(images)

    cell_source = as_dict(cell.get("source"))

    text = normalize_content_text(
        cell.get("text", ""),
        context=context,
        source=cell_source,
    )

    row = normalize_cell_position(
        cell.get("row"),
        field_name="row",
        context=context,
        source=cell_source,
    )
    col = normalize_cell_position(
        cell.get("col"),
        field_name="col",
        context=context,
        source=cell_source,
    )
    row_span = normalize_cell_span(
        cell.get("row_span", 1),
        field_name="row_span",
        context=context,
        source=cell_source,
    )
    col_span = normalize_cell_span(
        cell.get("col_span", 1),
        field_name="col_span",
        context=context,
        source=cell_source,
    )

    # --------------------------------------------------------
    # 실제 빈 셀과 이미지 전용 셀 통계
    # --------------------------------------------------------
    if not text and not blocks and not images:
        context.empty_cell_count += 1
    elif not text and not blocks and images:
        context.image_only_cell_count += 1

    normalized: dict[str, Any] = {
        "row": row,
        "col": col,
        "row_span": row_span,
        "col_span": col_span,
        "text": text,
        "blocks": blocks,
        "images": images,
        "search_text": build_search_text(text),
    }

    if "source" in cell:
        normalized["source"] = normalize_source(
            cell_source,
            document_format,
            section_index,
        )

    extra = collect_extra_fields(
        cell,
        {
            "row",
            "col",
            "row_span",
            "col_span",
            "text",
            "search_text",
            "paragraphs",
            "nested_tables",
            "images",
            "source",
        },
    )

    if extra:
        normalized["extra"] = extra

    return normalized


# ============================================================
# Table 정규화
# ============================================================
def normalize_table(
    table: dict[str, Any],
    document_format: str,
    section_index: int | None,
    context: NormalizationContext,
) -> dict[str, Any]:
    """
    Table을 Common JSON 구조로 정규화합니다.

    Nested Table도 같은 함수를 재귀적으로 사용합니다.
    """
    context.table_count += 1

    raw_cells = as_list(table.get("cells"))
    normalized_cells: list[dict[str, Any]] = []

    for cell_order, cell in enumerate(raw_cells):
        if not isinstance(cell, dict):
            context.warn(
                "INVALID_TABLE_CELL",
                "표 셀이 객체가 아니어서 제외했습니다.",
                source=as_dict(table.get("source")),
                details={"cell_order": cell_order},
                fatal_in_strict=True,
            )
            continue

        normalized_cells.append(
            normalize_cell(
                cell,
                document_format,
                section_index,
                context,
            )
        )

    # --------------------------------------------------------
    # 셀 좌표와 병합 범위로 논리적 표 크기 계산
    # --------------------------------------------------------
    computed_row_count = max(
        (
            int(cell["row"]) + int(cell["row_span"])
            for cell in normalized_cells
            if cell.get("row") is not None
        ),
        default=0,
    )

    computed_col_count = max(
        (
            int(cell["col"]) + int(cell["col_span"])
            for cell in normalized_cells
            if cell.get("col") is not None
        ),
        default=0,
    )

    declared_row_count = normalize_optional_integer(
        table.get("row_count"),
        default=None,
        minimum=0,
    )
    declared_col_count = normalize_optional_integer(
        table.get("col_count"),
        default=None,
        minimum=0,
    )

    # Parser의 값이 없거나 셀 범위와 다르면 실제 셀 기준 값을 사용합니다.
    row_count = computed_row_count
    col_count = computed_col_count

    if declared_row_count is not None and declared_row_count != computed_row_count:
        context.warn(
            "TABLE_ROW_COUNT_MISMATCH",
            "Parser의 row_count와 셀 좌표로 계산한 행 수가 달라 계산값을 사용했습니다.",
            source=as_dict(table.get("source")),
            details={
                "declared": declared_row_count,
                "computed": computed_row_count,
            },
        )

    if declared_col_count is not None and declared_col_count != computed_col_count:
        context.warn(
            "TABLE_COL_COUNT_MISMATCH",
            "Parser의 col_count와 셀 좌표로 계산한 열 수가 달라 계산값을 사용했습니다.",
            source=as_dict(table.get("source")),
            details={
                "declared": declared_col_count,
                "computed": computed_col_count,
            },
        )

    normalized: dict[str, Any] = {
        "type": "table",
        "table_index": normalize_optional_integer(
            table.get("table_index"),
            default=None,
            minimum=0,
        ),
        "row_count": row_count,
        "col_count": col_count,
        "cells": normalized_cells,
        "source": normalize_source(
            as_dict(table.get("source")),
            document_format,
            section_index,
        ),
    }

    extra = collect_extra_fields(
        table,
        {
            "type",
            "table_index",
            "row_count",
            "col_count",
            "cells",
            "source",
        },
    )

    if extra:
        normalized["extra"] = extra

    return normalized


# ============================================================
# Section Block 정규화
# ============================================================
def normalize_block(
    block: dict[str, Any],
    document_format: str,
    section_index: int | None,
    context: NormalizationContext,
) -> dict[str, Any]:
    """Section 내부 Block을 유형별로 정규화합니다."""
    block_type = block.get("type")

    if block_type == "table":
        return normalize_table(
            block,
            document_format,
            section_index,
            context,
        )

    if block_type == "paragraph":
        return normalize_paragraph(
            block,
            document_format,
            section_index,
            context,
        )

    # 아직 정의하지 않은 Block은 데이터 손실을 막기 위해 그대로 보존합니다.
    context.unknown_block_count += 1
    context.warn(
        "UNKNOWN_BLOCK_TYPE",
        "정의되지 않은 Block 유형을 원본 그대로 보존했습니다.",
        source={
            "section_index": section_index,
            "block_type": block_type,
        },
    )

    return deep_copy(block)


# ============================================================
# Parser JSON 입력 구조 검증
# ============================================================
def validate_parser_document(document: dict[str, Any]) -> str:
    """필수 최상위 구조와 문서 형식을 확인하고 format을 반환합니다."""
    document_info = document.get("document")

    if not isinstance(document_info, dict):
        raise ValueError(
            "Parser JSON에 document 객체가 없습니다."
        )

    document_format = str(
        document_info.get("format", "")
    ).lower().strip()

    if document_format not in SUPPORTED_DOCUMENT_FORMATS:
        raise ValueError(
            "지원하지 않는 문서 형식입니다: "
            f"{document_format or '(비어 있음)'}"
        )

    sections = document.get("sections")
    if not isinstance(sections, list):
        raise ValueError(
            "Parser JSON의 sections는 배열이어야 합니다."
        )

    return document_format


# ============================================================
# search_text 최종 보장
# ============================================================
def ensure_search_text_fields(value: Any) -> None:
    """
    최종 정규화 JSON을 재귀적으로 순회하여 콘텐츠 ``text``가 있는 객체에
    ``search_text``가 반드시 존재하도록 보장합니다.

    적용 대상:
    - paragraph
    - table cell
    - 향후 추가되는 콘텐츠 block

    제외 대상:
    - raw_text 등 원본 추적 문자열
    - document/parser/source/통계/경고 메타데이터

    이 함수는 객체를 제자리에서 수정합니다.
    """
    if isinstance(value, list):
        for item in value:
            ensure_search_text_fields(item)
        return

    if not isinstance(value, dict):
        return

    text = value.get("text")
    if isinstance(text, str):
        # 빈 문자열도 빈 search_text로 명시해 스키마를 일정하게 유지합니다.
        value["search_text"] = build_search_text(text)

    # 원본/메타데이터 영역에는 search_text를 새로 만들지 않습니다.
    excluded_children = {
        "document",
        "parser",
        "normalizer",
        "source",
        "parser_statistics",
        "normalization_statistics",
        "parser_warnings",
        "normalizer_warnings",
        "warnings",
        "number_recovery",
        "pua_characters",
    }

    for key, child in value.items():
        if key in excluded_children:
            continue
        ensure_search_text_fields(child)


# ============================================================
# Document 전체 정규화
# ============================================================
def normalize_document(
    document: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """
    HWP/HWPX Parser가 생성한 JSON을 Common Normalized JSON으로 변환합니다.

    Normalizer의 범위:
    - 텍스트 표현 통일
    - Source Metadata 공통화
    - Cell paragraphs/nested_tables를 blocks로 통합
    - 이미지 존재 정보 보존
    - 구조 검증 및 통계 생성

    Normalizer에서 하지 않는 작업:
    - 제목 계층 판별
    - 표 헤더 및 행 의미 판별
    - 핵심 정보 추출
    - OCR
    - 청킹 및 임베딩
    """
    document_format = validate_parser_document(document)
    context = NormalizationContext(strict=strict)

    raw_document_info = as_dict(document.get("document"))
    normalized_document_info = deep_copy(raw_document_info)
    normalized_document_info["filename"] = raw_document_info.get("filename")
    normalized_document_info["format"] = document_format
    normalized_document_info["file_size"] = normalize_optional_integer(
        raw_document_info.get("file_size"),
        default=None,
        minimum=0,
    )

    normalized: dict[str, Any] = {
        "schema_version": document.get("schema_version", "1.1"),
        "stage": "normalized",
        "document": normalized_document_info,
        "parser": deep_copy(as_dict(document.get("parser"))),
        "normalizer": {
            "engine": NORMALIZER_NAME,
            "version": NORMALIZER_VERSION,
        },
        "sections": [],
    }

    # --------------------------------------------------------
    # Section 순회
    # --------------------------------------------------------
    raw_sections = as_list(document.get("sections"))

    for section_order, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            context.warn(
                "INVALID_SECTION",
                "Section이 객체가 아니어서 제외했습니다.",
                details={"section_order": section_order},
                fatal_in_strict=True,
            )
            continue

        context.section_count += 1

        section_index = normalize_optional_integer(
            section.get("section_index"),
            default=section_order,
            minimum=0,
        )

        normalized_section: dict[str, Any] = {
            "section_index": section_index,
            "blocks": [],
        }

        raw_blocks = as_list(section.get("blocks"))

        for block_order, block in enumerate(raw_blocks):
            if not isinstance(block, dict):
                context.warn(
                    "INVALID_SECTION_BLOCK",
                    "Section Block이 객체가 아니어서 제외했습니다.",
                    source={"section_index": section_index},
                    details={"block_order": block_order},
                    fatal_in_strict=True,
                )
                continue

            normalized_section["blocks"].append(
                normalize_block(
                    block,
                    document_format,
                    section_index,
                    context,
                )
            )

        section_extra = collect_extra_fields(
            section,
            {"section_index", "blocks"},
        )

        if section_extra:
            normalized_section["extra"] = section_extra

        normalized["sections"].append(normalized_section)

    # --------------------------------------------------------
    # Parser와 Normalizer 통계·경고를 분리하여 보존
    # --------------------------------------------------------
    parser_statistics = deep_copy(as_dict(document.get("statistics")))
    parser_warnings = deep_copy(as_list(document.get("warnings")))
    normalizer_warnings = deep_copy(context.warnings)

    normalized["parser_statistics"] = parser_statistics
    normalized["normalization_statistics"] = context.statistics()
    normalized["parser_warnings"] = parser_warnings
    normalized["normalizer_warnings"] = normalizer_warnings
    normalized["warnings"] = parser_warnings + normalizer_warnings

    # --------------------------------------------------------
    # 향후 Parser 최상위 필드가 추가되어도 유실되지 않도록 보존
    # --------------------------------------------------------
    top_level_extra = collect_extra_fields(
        document,
        {
            "schema_version",
            "document",
            "parser",
            "sections",
            "statistics",
            "warnings",
        },
    )

    if top_level_extra:
        normalized["input_extra"] = top_level_extra

    # 개별 정규화 함수나 향후 Block 유형에서 search_text가 누락되더라도
    # 최종 출력 직전에 모든 콘텐츠 text 노드에 검색 문자열을 보장합니다.
    ensure_search_text_fields(normalized.get("sections", []))

    return normalized


# ============================================================
# 출력 경로 결정
# ============================================================
def infer_document_id(input_path: Path) -> str | None:
    """
    표준 Parser 출력 경로에서 document_id를 추출합니다.

    표준 구조:
        outputs/<document_id>/<parsed-stage>/<format>.json

    단계 폴더명은 config.paths에서 가져오므로 Normalizer 안에 중복 작성하지 않습니다.
    """
    if input_path.parent.name != PARSED_STAGE_DIRECTORY_NAME:
        return None

    document_id = input_path.parent.parent.name.strip()
    return document_id or None


def resolve_output_path(
    input_path: str | Path,
    document_format: str,
    *,
    output_path: str | Path | None = None,
    document_id: str | None = None,
) -> Path:
    """
    출력 경로 우선순위:
    1. --output으로 직접 전달된 경로
    2. --document-id로 전달된 문서 ID
    3. 표준 01_parsed 입력 경로에서 자동 추출한 문서 ID

    비표준 입력 경로에서 문서 ID를 임의 추측하지 않습니다.
    """
    if output_path is not None:
        return Path(output_path).expanduser().resolve()

    source_path = Path(input_path).expanduser().resolve()

    resolved_document_id = (
        document_id.strip()
        if isinstance(document_id, str) and document_id.strip()
        else infer_document_id(source_path)
    )

    if not resolved_document_id:
        raise ValueError(
            "표준 Parser 출력 경로가 아니므로 출력 위치를 자동 결정할 수 없습니다. "
            "--output 또는 --document-id를 지정하세요."
        )

    paths = get_document_output_paths(resolved_document_id)
    return paths.normalized / f"{document_format}.json"


# ============================================================
# 실행 결과 요약
# ============================================================
def print_summary(
    input_path: Path,
    output_path: Path,
    normalized_document: dict[str, Any],
) -> None:
    statistics = as_dict(
        normalized_document.get("normalization_statistics")
    )

    print()
    print("=" * 70)
    print("정규화 완료")
    print("=" * 70)
    print(f"입력: {input_path}")
    print(f"출력: {output_path}")
    print(f"Section 수: {statistics.get('section_count', 0)}")
    print(f"문단 수: {statistics.get('paragraph_count', 0)}")
    print(f"표 수: {statistics.get('table_count', 0)}")
    print(f"셀 수: {statistics.get('cell_count', 0)}")
    print(f"이미지 수: {statistics.get('image_count', 0)}")
    print(f"실제 빈 셀 수: {statistics.get('empty_cell_count', 0)}")
    print(f"이미지 전용 셀 수: {statistics.get('image_only_cell_count', 0)}")
    print(f"미정의 Block 수: {statistics.get('unknown_block_count', 0)}")
    print(f"미검증 PUA 문자 수: {statistics.get('unverified_pua_count', 0)}")
    print(f"Normalizer 경고 수: {statistics.get('warning_count', 0)}")


# ============================================================
# CLI
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "HWP/HWPX Parser JSON을 Common Normalized JSON 구조로 변환합니다."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="입력 Parser JSON 경로",
    )

    parser.add_argument(
        "--output",
        required=False,
        help=(
            "출력 Normalized JSON 경로. 생략하면 표준 Parser 입력 경로 또는 "
            "--document-id를 기준으로 config.paths의 normalized 경로를 사용합니다."
        ),
    )

    parser.add_argument(
        "--document-id",
        required=False,
        help=(
            "비표준 위치의 Parser JSON을 자동 출력 경로로 저장할 때 사용할 문서 ID"
        ),
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="핵심 구조 오류가 발생하면 경고만 남기지 않고 실행을 중단합니다.",
    )

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    raw_document = load_json(input_path)

    normalized_document = normalize_document(
        raw_document,
        strict=args.strict,
    )

    document_format = str(
        normalized_document["document"]["format"]
    )

    output_path = resolve_output_path(
        input_path,
        document_format,
        output_path=args.output,
        document_id=args.document_id,
    )

    saved_path = save_json(
        normalized_document,
        output_path,
    )

    print_summary(
        input_path,
        saved_path,
        normalized_document,
    )


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    main()
