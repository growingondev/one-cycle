from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_SPACE_RE = re.compile(r"[ \t]+")
_UNIT_DECLARATION_RE = re.compile(
    r"(?:^|[\[\(【〈《<]\s*)단위\s*[:：]\s*([^\s\]\)】〉》>,;；]+)",
    re.IGNORECASE,
)
_STANDALONE_UNIT_DECLARATION_RE = re.compile(
    r"^\s*[\[\(【〈《<]?\s*단위\s*[:：]\s*([^\s\]\)】〉》>,;；]+)\s*[\]\)】〉》>]?\s*$",
    re.IGNORECASE,
)
_KNOWN_PAREN_UNITS = {
    "원",
    "천원",
    "만원",
    "억원",
    "㎡",
    "m²",
    "m2",
    "%",
    "kg",
    "g",
    "km",
    "m",
    "cm",
    "mm",
    "세대",
    "호",
    "명",
    "개",
    "건",
    "년",
    "개월",
    "일",
    "시간",
    "분",
}
_PAREN_CONTENT_RE = re.compile(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]")
_NUMERIC_ONLY_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def flatten_search_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", clean_text(value).replace("\n", " ")).strip()


def unique_join(values: Iterable[Any], separator: str = " ") -> str:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = flatten_search_text(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return separator.join(output)


def section_heading(section_path: list[str]) -> str:
    return " > ".join(part for part in section_path if part)


def build_content(section_path: list[str], body: str, *, include_path: bool) -> str:
    body = clean_text(body)
    if include_path and section_path:
        return f"[{section_heading(section_path)}]\n\n{body}".strip()
    return body


def build_search_text(
    *,
    section_path: list[str],
    normalized_title: str,
    search_title: str,
    body_search_text: str,
    domain: dict[str, Any] | None,
    include_path: bool,
    include_domain: bool,
) -> str:
    parts: list[Any] = []
    if include_path:
        parts.extend(section_path)
    parts.extend([normalized_title, search_title, body_search_text])
    if include_domain and domain:
        parts.extend([domain.get("category"), domain.get("topic")])
    return unique_join(parts)


def build_embedding_text(section_path: list[str], body: str) -> str:
    heading = section_heading(section_path)
    body = clean_text(body)
    return f"{heading}\n{body}".strip() if heading else body


def normalized_entity_text(normalized: Any) -> list[str]:
    """Extract useful searchable normalized values without assuming one schema."""
    if not isinstance(normalized, dict):
        return []
    values: list[str] = []
    for entity in normalized.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        for key in ("normalized_value", "won_value", "numeric_value", "unit"):
            value = entity.get(key)
            if value is not None:
                values.append(str(value))
    return values


def collect_entities(normalized_values: Iterable[Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for normalized in normalized_values:
        if not isinstance(normalized, dict):
            continue
        for entity in normalized.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            fingerprint = repr(sorted(entity.items(), key=lambda item: item[0]))
            if fingerprint not in seen:
                seen.add(fingerprint)
                entities.append(entity)
    return entities


def extract_declared_unit(text: Any) -> str | None:
    """Return an explicitly declared unit such as '[단위: 천원]'.

    This function only trusts explicit unit declarations. It does not infer a unit
    from the numeric value itself.
    """
    value = clean_text(text)
    if not value:
        return None
    match = _UNIT_DECLARATION_RE.search(value)
    if not match:
        return None
    unit = clean_text(match.group(1)).strip(" .,:;：")
    return unit or None



def extract_standalone_declared_unit(text: Any) -> str | None:
    """Return a unit only when the whole paragraph is a unit declaration."""
    value = clean_text(text)
    if not value:
        return None
    match = _STANDALONE_UNIT_DECLARATION_RE.fullmatch(value)
    if not match:
        return None
    unit = clean_text(match.group(1)).strip(" .,:;：")
    return unit or None


def extract_header_unit(text: Any) -> str | None:
    """Extract a unit explicitly present in a header/title.

    Priority:
    1) '(단위: X)' / '[단위: X]' style declarations
    2) parenthesized tokens that are known measurement/currency units
    """
    value = clean_text(text)
    if not value:
        return None

    declared = extract_declared_unit(value)
    if declared:
        return declared

    for match in _PAREN_CONTENT_RE.finditer(value):
        candidate = clean_text(match.group(1))
        if candidate in _KNOWN_PAREN_UNITS:
            return candidate
    return None


def normalized_unit(normalized: Any) -> str | None:
    """Return one unambiguous unit from normalized entities, if available."""
    if not isinstance(normalized, dict):
        return None
    units: list[str] = []
    for entity in normalized.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        unit = clean_text(entity.get("unit"))
        if unit and unit not in units:
            units.append(unit)
    return units[0] if len(units) == 1 else None


def is_plain_numeric_value(value: Any) -> bool:
    """True only for a bare numeric value, not text that already contains a unit."""
    return bool(_NUMERIC_ONLY_RE.fullmatch(clean_text(value)))


def append_unit_if_applicable(value: Any, unit: str | None) -> str:
    """Attach a trusted unit only to a bare numeric value.

    This keeps raw structured values unchanged and only changes the display/search
    representation used by chunking.
    """
    text = clean_text(value)
    if not text or not unit or not is_plain_numeric_value(text):
        return text
    return f"{text}{unit}"
