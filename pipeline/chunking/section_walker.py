from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class SectionContext:
    section: dict[str, Any]
    section_path: list[str]


def preferred_title(section: dict[str, Any]) -> str:
    return (
        section.get("normalized_title")
        or section.get("title")
        or section.get("search_title")
        or "제목 없음"
    ).strip()


def walk_sections(
    sections: list[dict[str, Any]],
    parent_path: list[str] | None = None,
) -> Iterator[SectionContext]:
    parent_path = list(parent_path or [])
    for section in sections:
        title = preferred_title(section)
        current_path = [*parent_path, title]
        yield SectionContext(section=section, section_path=current_path)
        children = section.get("children") or []
        yield from walk_sections(children, current_path)
