from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            joined = "\n".join(f"- {item}" for item in self.errors)
            raise ValueError(f"Input schema validation failed:\n{joined}")


class StructuredJsonValidator:
    """Validate the stable input contract before chunk generation."""

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        result = ValidationResult()

        if not isinstance(data, dict):
            result.errors.append("root must be an object")
            return result

        document = data.get("document")
        if not isinstance(document, dict):
            result.errors.append("document must be an object")
        else:
            for key in ("filename", "format"):
                if not isinstance(document.get(key), str) or not document.get(key):
                    result.errors.append(f"document.{key} must be a non-empty string")

        intro = data.get("intro")
        if not isinstance(intro, list):
            result.errors.append("intro must be an array")
        else:
            self._validate_contents(intro, "intro", result)

        sections = data.get("sections")
        if not isinstance(sections, list):
            result.errors.append("sections must be an array")
        else:
            seen_ids: set[str] = set()
            for index, section in enumerate(sections):
                self._validate_section(section, f"sections[{index}]", result, seen_ids)

        schema_version = data.get("schema_version")
        if schema_version is None:
            result.warnings.append("schema_version is missing")

        return result

    def _validate_section(
        self,
        section: Any,
        path: str,
        result: ValidationResult,
        seen_ids: set[str],
    ) -> None:
        if not isinstance(section, dict):
            result.errors.append(f"{path} must be an object")
            return

        section_id = section.get("section_id")
        if not isinstance(section_id, str) or not section_id:
            result.errors.append(f"{path}.section_id must be a non-empty string")
        elif section_id in seen_ids:
            result.errors.append(f"duplicate section_id: {section_id}")
        else:
            seen_ids.add(section_id)

        if not isinstance(section.get("level"), int):
            result.errors.append(f"{path}.level must be an integer")
        if not isinstance(section.get("title"), str):
            result.errors.append(f"{path}.title must be a string")

        contents = section.get("contents")
        if not isinstance(contents, list):
            result.errors.append(f"{path}.contents must be an array")
        else:
            self._validate_contents(contents, f"{path}.contents", result)

        children = section.get("children")
        if not isinstance(children, list):
            result.errors.append(f"{path}.children must be an array")
        else:
            for index, child in enumerate(children):
                self._validate_section(
                    child,
                    f"{path}.children[{index}]",
                    result,
                    seen_ids,
                )

    def _validate_contents(
        self,
        contents: list[Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        for index, item in enumerate(contents):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                result.errors.append(f"{item_path} must be an object")
                continue
            item_type = item.get("type")
            if item_type == "paragraph":
                if not isinstance(item.get("text"), str):
                    result.errors.append(f"{item_path}.text must be a string")
            elif item_type == "table":
                if not isinstance(item.get("cells", []), list):
                    result.errors.append(f"{item_path}.cells must be an array")
                if "structured_table" not in item:
                    result.warnings.append(f"{item_path}.structured_table is missing")
            else:
                result.warnings.append(
                    f"{item_path} has unsupported type {item_type!r}; it will be skipped"
                )
