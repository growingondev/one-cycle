#!/usr/bin/env python3
"""Structure + Value Normalizer 최종 결과 검증.

실행 오류와 데이터 품질 경고를 분리해 JSON 보고서로 저장한다.
원본 문서를 수정하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

OUTPUT_FILENAME = "step4-3_pipeline_verification.json"


def load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"검증 입력 파일을 찾을 수 없습니다: {target}")
    try:
        with target.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {target} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error
    if not isinstance(data, dict):
        raise ValueError("검증 입력 JSON 최상위 값은 객체여야 합니다.")
    return data


def save_json(data: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return target


def iter_sections(sections: Any, parent_path: list[str] | None = None):
    parent_path = parent_path or []
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "")
        path = [*parent_path, *([title] if title else [])]
        yield section, path
        yield from iter_sections(section.get("children") or [], path)


def iter_tables(value: Any, path: list[Any] | None = None):
    path = path or []
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_tables(child, [*path, index])
        return
    if not isinstance(value, dict):
        return
    if value.get("type") == "table":
        yield value, path
    for key, child in value.items():
        if key in {"structured_table", "source", "domain", "classification_sources"}:
            continue
        if isinstance(child, (dict, list)):
            yield from iter_tables(child, [*path, key])


def issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    *,
    path: Iterable[Any] = (),
    details: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "path": [str(part) for part in path],
    }
    if details:
        item["details"] = details
    issues.append(item)


def verify_document(document: dict[str, Any], *, input_path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    stage = str(document.get("stage") or "")
    if stage != "value_normalized":
        issue(
            issues, "error", "INVALID_STAGE",
            "최종 검증 입력 stage는 value_normalized여야 합니다.",
            details={"actual": stage},
        )

    sections_raw = document.get("sections")
    if not isinstance(sections_raw, list):
        issue(issues, "error", "SECTIONS_MISSING", "sections 배열이 없습니다.")
        sections_raw = []

    sections = list(iter_sections(sections_raw))
    if not sections:
        issue(issues, "error", "NO_SECTIONS", "구조화된 Section이 없습니다.")

    section_ids: list[str] = []
    domain_count = 0
    semantic_count = 0
    classification_text_missing = 0
    for section, section_path in sections:
        section_id = str(section.get("section_id") or "")
        if not section_id:
            issue(
                issues, "warning", "SECTION_ID_MISSING",
                "Section ID가 없습니다.", path=section_path,
            )
        else:
            section_ids.append(section_id)

        if isinstance(section.get("domain"), dict):
            domain_count += 1
            domain = section["domain"]
            for field in ("category", "topic", "method", "confidence"):
                if field not in domain:
                    issue(
                        issues, "warning", "DOMAIN_FIELD_MISSING",
                        f"domain.{field} 필드가 없습니다.",
                        path=[*section_path, "domain"],
                    )
        if section.get("needs_semantic_classification") is True:
            semantic_count += 1
        if not str(section.get("classification_text") or "").strip():
            classification_text_missing += 1
            issue(
                issues, "warning", "CLASSIFICATION_TEXT_MISSING",
                "임베딩 보완용 classification_text가 비어 있습니다.",
                path=section_path,
            )

    duplicate_ids = sorted(
        section_id for section_id, count in Counter(section_ids).items() if count > 1
    )
    if duplicate_ids:
        issue(
            issues, "error", "DUPLICATE_SECTION_ID",
            "중복 Section ID가 있습니다.", details={"section_ids": duplicate_ids},
        )

    tables = list(iter_tables(document))
    structured_count = 0
    skipped_count = 0
    unresolved_count = 0
    for table, table_path in tables:
        rows = int(table.get("row_count", 0) or 0)
        cols = int(table.get("col_count", 0) or 0)
        if rows <= 0 or cols <= 0:
            issue(
                issues, "warning", "INVALID_TABLE_SIZE",
                "표의 행 또는 열 수가 유효하지 않습니다.",
                path=table_path, details={"rows": rows, "cols": cols},
            )

        for index, cell in enumerate(table.get("cells") or []):
            if not isinstance(cell, dict):
                continue
            row = int(cell.get("row", 0) or 0)
            col = int(cell.get("col", 0) or 0)
            row_span = max(1, int(cell.get("row_span", 1) or 1))
            col_span = max(1, int(cell.get("col_span", 1) or 1))
            if row < 0 or col < 0 or row + row_span > rows or col + col_span > cols:
                issue(
                    issues, "error", "CELL_RANGE_OUT_OF_BOUNDS",
                    "셀 병합 범위가 표 크기를 벗어납니다.",
                    path=[*table_path, "cells", index],
                    details={
                        "row": row, "col": col,
                        "row_span": row_span, "col_span": col_span,
                        "rows": rows, "cols": cols,
                    },
                )

        structured = table.get("structured_table")
        status = structured.get("status") if isinstance(structured, dict) else None
        if status in {"structured", "partially_structured"}:
            structured_count += 1
            layout = structured.get("layout")
            if layout not in {"row_records", "key_value"}:
                issue(
                    issues, "warning", "UNKNOWN_TABLE_LAYOUT",
                    "지원 목록에 없는 구조화 표 layout입니다.",
                    path=[*table_path, "structured_table"],
                    details={"layout": layout},
                )
        elif status == "skipped":
            skipped_count += 1
        else:
            unresolved_count += 1
            issue(
                issues, "warning", "TABLE_UNRESOLVED",
                "표가 structured 또는 skipped 상태가 아닙니다.",
                path=table_path, details={"status": status},
            )

    error_count = sum(item["severity"] == "error" for item in issues)
    warning_count = sum(item["severity"] == "warning" for item in issues)
    status = "fail" if error_count else ("warning" if warning_count else "pass")

    return {
        "schema_version": "1.0",
        "stage": "pipeline_verification",
        "status": status,
        "input_file": str(input_path),
        "summary": {
            "section_count": len(sections),
            "domain_matched_count": domain_count,
            "semantic_fallback_count": semantic_count,
            "classification_text_missing_count": classification_text_missing,
            "table_count": len(tables),
            "structured_table_count": structured_count,
            "skipped_table_count": skipped_count,
            "unresolved_table_count": unresolved_count,
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "issues": issues,
    }


def process(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    source_path = Path(input_path).expanduser().resolve()
    output = (
        Path(output_path).expanduser().resolve()
        if output_path
        else source_path.parent / OUTPUT_FILENAME
    )
    report = verify_document(load_json(source_path), input_path=source_path)
    return save_json(report, output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Structure 최종 결과 검증")
    parser.add_argument("--input", required=True, help="step4-1_value_normalized.json 경로")
    parser.add_argument("--output", help="검증 보고서 저장 경로")
    args = parser.parse_args()
    result = process(args.input, args.output)
    print(f"검증 보고서: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
