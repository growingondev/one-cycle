from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_SPACE_RE = re.compile(r"[ \t]+")


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
