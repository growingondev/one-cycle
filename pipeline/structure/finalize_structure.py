from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value))


def _cell_range(cell: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(cell.get("row", 0) or 0),
        int(cell.get("col", 0) or 0),
        max(1, int(cell.get("row_span", 1) or 1)),
        max(1, int(cell.get("col_span", 1) or 1)),
    )


def build_grid(
    table: dict[str, Any],
) -> tuple[list[list[dict[str, Any] | None]], list[str]]:
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)

    grid: list[list[dict[str, Any] | None]] = [
        [None for _ in range(cols)]
        for _ in range(rows)
    ]
    errors: list[str] = []

    for cell in table.get("cells") or []:
        if not isinstance(cell, dict):
            continue

        row, col, row_span, col_span = _cell_range(cell)
        if (
            row < 0
            or col < 0
            or row + row_span > rows
            or col + col_span > cols
        ):
            errors.append(
                "병합 범위 초과: "
                f"row={row}, col={col}, "
                f"row_span={row_span}, col_span={col_span}"
            )
            continue

        ref = {
            "origin_row": row,
            "origin_col": col,
            "row_span": row_span,
            "col_span": col_span,
            "text": clean_text(cell.get("text")),
        }

        for target_row in range(row, row + row_span):
            for target_col in range(col, col + col_span):
                if grid[target_row][target_col] is not None:
                    existing = grid[target_row][target_col]
                    if (
                        existing.get("origin_row") != row
                        or existing.get("origin_col") != col
                    ):
                        errors.append(
                            "셀 범위 겹침: "
                            f"row={target_row}, col={target_col}"
                        )
                grid[target_row][target_col] = ref

    return grid, errors


def ref_source(ref: dict[str, Any] | None) -> dict[str, int] | None:
    if not ref:
        return None
    return {
        "row": int(ref.get("origin_row", 0)),
        "col": int(ref.get("origin_col", 0)),
    }


def grid_text(
    grid: list[list[dict[str, Any] | None]],
    row: int,
    col: int,
) -> str:
    if row < 0 or col < 0:
        return ""
    if row >= len(grid) or col >= len(grid[row]):
        return ""
    ref = grid[row][col]
    return clean_text(ref.get("text")) if ref else ""


def detect_row_kind(values: list[str]) -> str:
    joined = compact_text(" ".join(values))
    # "소계"에는 "계"가 포함되므로 subtotal을 먼저 판정한다.
    if any(word in joined for word in ("소계", "소계금액")):
        return "subtotal"
    if any(word in joined for word in ("총계", "합계")) or joined == "계":
        return "total"
    return "data"


def make_columns(labels: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "column": index,
            "header_path": [label],
        }
        for index, label in enumerate(labels)
    ]


def build_transposed_records(
    table: dict[str, Any],
    grid: list[list[dict[str, Any] | None]],
    *,
    label_start_row: int,
    orientation: str,
) -> dict[str, Any] | None:
    """첫 열이 필드명이고 나머지 열이 레코드인 가로형 표를 전치한다."""
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)

    if rows - label_start_row < 2 or cols < 3:
        return None

    labels = [
        grid_text(grid, row, 0)
        for row in range(label_start_row, rows)
    ]

    if any(not label for label in labels):
        return None

    records: list[dict[str, Any]] = []

    for col in range(1, cols):
        values: list[dict[str, Any]] = []

        for relative_index, row in enumerate(
            range(label_start_row, rows)
        ):
            value = grid_text(grid, row, col)
            if not value:
                continue

            ref = grid[row][col]
            values.append(
                {
                    "column": relative_index,
                    "header_path": [labels[relative_index]],
                    "value": value,
                    "source": ref_source(ref),
                    "inherited_from_row_span": bool(
                        ref and int(ref.get("origin_row", row)) < row
                    ),
                }
            )

        if not values:
            continue

        records.append(
            {
                "row_index": col,
                "record_index": col - 1,
                "row_kind": detect_row_kind(
                    [str(item.get("value") or "") for item in values]
                ),
                "values": values,
                "merged_values": [],
            }
        )

    if not records:
        return None

    return {
        "status": "structured",
        "layout": "row_records",
        "orientation": orientation,
        "header_rows": list(range(label_start_row, rows)),
        "columns": make_columns(labels),
        "records": records,
        "postprocessed": True,
    }


def build_schedule_records(
    table: dict[str, Any],
    grid: list[list[dict[str, Any] | None]],
) -> dict[str, Any] | None:
    """도입부의 3행×2열 공고·계약 일정 표를 열 단위 레코드로 전환한다."""
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)

    if rows != 3 or cols != 2:
        return None

    second_row = " ".join(
        grid_text(grid, 1, col)
        for col in range(cols)
    )
    if not re.search(r"\d{2,4}[.\-/]\d{1,2}", second_row):
        return None

    labels = ["구분", "일정", "장소"]
    records: list[dict[str, Any]] = []

    for col in range(cols):
        values: list[dict[str, Any]] = []
        for row, label in enumerate(labels):
            value = grid_text(grid, row, col)
            if not value:
                continue
            values.append(
                {
                    "column": row,
                    "header_path": [label],
                    "value": value,
                    "source": ref_source(grid[row][col]),
                    "inherited_from_row_span": False,
                }
            )

        if values:
            records.append(
                {
                    "row_index": col,
                    "record_index": col,
                    "row_kind": "data",
                    "values": values,
                    "merged_values": [],
                }
            )

    if not records:
        return None

    return {
        "status": "structured",
        "layout": "row_records",
        "orientation": "transposed_schedule",
        "header_rows": [],
        "columns": make_columns(labels),
        "records": records,
        "postprocessed": True,
    }



def looks_like_standard_header_row(
    table: dict[str, Any],
    grid: list[list[dict[str, Any] | None]],
) -> bool:
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)
    if rows < 2 or cols < 2:
        return False

    first_row_cells = [
        cell
        for cell in table.get("cells") or []
        if int(cell.get("row", 0) or 0) == 0
    ]
    if len(first_row_cells) < max(2, cols // 2):
        return False

    labels = [grid_text(grid, 0, col) for col in range(cols)]
    nonempty = [label for label in labels if label]
    if len(nonempty) < max(2, cols // 2):
        return False

    numeric_like = sum(
        bool(re.search(r"\d", label))
        for label in nonempty
    )
    long_count = sum(len(label) > 30 for label in nonempty)

    return (
        numeric_like <= max(1, len(nonempty) // 3)
        and long_count == 0
    )


def build_standard_row_records(
    table: dict[str, Any],
    grid: list[list[dict[str, Any] | None]],
) -> dict[str, Any] | None:
    """첫 행을 Header로 사용하고 row_span 값을 각 데이터 행에 상속한다."""
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)

    if rows < 2 or cols < 2:
        return None

    labels = [
        grid_text(grid, 0, col)
        for col in range(cols)
    ]
    if sum(bool(label) for label in labels) < max(2, cols // 2):
        return None

    records: list[dict[str, Any]] = []

    for row in range(1, rows):
        values: list[dict[str, Any]] = []
        merged_values: list[dict[str, Any]] = []
        seen_merged: set[tuple[int, int]] = set()

        for col in range(cols):
            ref = grid[row][col]
            value = clean_text(ref.get("text")) if ref else ""
            if not value:
                continue

            origin_row = int(ref.get("origin_row", row))
            origin_col = int(ref.get("origin_col", col))
            col_span = int(ref.get("col_span", 1) or 1)
            row_span = int(ref.get("row_span", 1) or 1)

            if col_span > 1:
                source_key = (origin_row, origin_col)
                if source_key in seen_merged:
                    continue
                seen_merged.add(source_key)

                covered_columns = list(
                    range(origin_col, min(cols, origin_col + col_span))
                )
                merged_values.append(
                    {
                        "value": value,
                        "source": {
                            "row": origin_row,
                            "col": origin_col,
                        },
                        "row_span": row_span,
                        "col_span": col_span,
                        "covered_columns": covered_columns,
                        "covered_header_paths": [
                            {
                                "column": covered_col,
                                "header_path": [
                                    labels[covered_col]
                                    or f"열 {covered_col}"
                                ],
                            }
                            for covered_col in covered_columns
                        ],
                        "inherited_from_row_span": origin_row < row,
                    }
                )
                continue

            label = labels[col] or f"열 {col}"
            values.append(
                {
                    "column": col,
                    "header_path": [label],
                    "value": value,
                    "source": {
                        "row": origin_row,
                        "col": origin_col,
                    },
                    "inherited_from_row_span": origin_row < row,
                }
            )

        if not values and not merged_values:
            continue

        all_values = [
            str(item.get("value") or "")
            for item in [*values, *merged_values]
        ]
        records.append(
            {
                "row_index": row,
                "row_kind": detect_row_kind(all_values),
                "values": values,
                "merged_values": merged_values,
            }
        )

    if not records:
        return None

    return {
        "status": "structured",
        "layout": "row_records",
        "orientation": "standard_rows_with_rowspan_inheritance",
        "header_rows": [0],
        "columns": make_columns(
            [
                label or f"열 {index}"
                for index, label in enumerate(labels)
            ]
        ),
        "records": records,
        "postprocessed": True,
    }


def structure_unresolved_table(
    table: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rows = int(table.get("row_count", 0) or 0)
    cols = int(table.get("col_count", 0) or 0)

    if rows <= 0 or cols <= 0:
        return None, "행·열 수가 없어 후처리할 수 없음"

    grid, errors = build_grid(table)
    if errors:
        return None, "; ".join(errors)

    # 문서 제목처럼 단일 셀뿐인 표는 의도적으로 fallback 유지.
    if rows == 1 and cols == 1:
        return None, "단일 셀 제목·레이아웃 표는 fallback 유지"

    schedule = build_schedule_records(table, grid)
    if schedule:
        return schedule, None

    # 첫 행 전체 병합 제목이 있는 가로형 표
    first_row_cells = [
        cell
        for cell in table.get("cells") or []
        if int(cell.get("row", 0) or 0) == 0
    ]
    title_row = (
        len(first_row_cells) == 1
        and int(first_row_cells[0].get("col_span", 1) or 1) >= cols
    )

    if title_row:
        transposed = build_transposed_records(
            table,
            grid,
            label_start_row=1,
            orientation="transposed_columns_with_title",
        )
        if transposed:
            transposed["table_title"] = clean_text(
                first_row_cells[0].get("text")
            )
            return transposed, None

    if looks_like_standard_header_row(table, grid):
        standard = build_standard_row_records(table, grid)
        if standard:
            return standard, None

    transposed = build_transposed_records(
        table,
        grid,
        label_start_row=0,
        orientation="transposed_columns",
    )
    if transposed:
        return transposed, None

    return None, "지원 가능한 후처리 표 패턴과 일치하지 않음"


_SKIP_RECURSIVE_KEYS = {
    "structured_table",
    "source",
    "domain",
    "hierarchy_method",
    "table_structuring_method",
    "domain_tagging_method",
}


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _table_key(table: dict[str, Any]) -> tuple[str, Any]:
    """같은 객체만 중복 처리하지 않도록 안전한 키를 만든다.

    서로 다른 표가 같은 table_index를 가질 수 있으므로 table_index만으로
    중복 제거하지 않는다.
    """
    return ("object", id(table))


def _iter_tables_in_value(
    value: Any,
    *,
    section_id: str,
    section_path: list[str],
    content_index: int,
    object_path: list[str],
    nested_depth: int,
    seen_objects: set[int],
):
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_tables_in_value(
                child,
                section_id=section_id,
                section_path=section_path,
                content_index=content_index,
                object_path=[*object_path, f"list:{index}"],
                nested_depth=nested_depth,
                seen_objects=seen_objects,
            )
        return

    if not isinstance(value, dict):
        return

    object_id = id(value)
    if object_id in seen_objects:
        return
    seen_objects.add(object_id)

    current_depth = nested_depth
    if value.get("type") == "table":
        yield {
            "section_id": section_id,
            "section_path": copy.deepcopy(section_path),
            "content_index": content_index,
            "table": value,
            "object_path": copy.deepcopy(object_path),
            "nested_depth": nested_depth,
        }
        current_depth = nested_depth + 1

        cells = [
            cell for cell in value.get("cells") or []
            if isinstance(cell, dict)
        ]
        cells.sort(
            key=lambda cell: (
                _safe_int(cell.get("row"), 0),
                _safe_int(cell.get("col", cell.get("column")), 0),
            )
        )
        for cell in cells:
            row = _safe_int(cell.get("row"), 0)
            col = _safe_int(cell.get("col", cell.get("column")), 0)
            yield from _iter_tables_in_value(
                cell.get("blocks") or [],
                section_id=section_id,
                section_path=section_path,
                content_index=content_index,
                object_path=[*object_path, f"cell:{row},{col}", "blocks"],
                nested_depth=current_depth,
                seen_objects=seen_objects,
            )
        return

    for key, child in value.items():
        if key in _SKIP_RECURSIVE_KEYS:
            continue
        if isinstance(child, (dict, list)):
            yield from _iter_tables_in_value(
                child,
                section_id=section_id,
                section_path=section_path,
                content_index=content_index,
                object_path=[*object_path, str(key)],
                nested_depth=current_depth,
                seen_objects=seen_objects,
            )


def iter_tables_recursive(document: dict[str, Any]):
    """intro와 모든 Section의 table/cell.blocks를 재귀 순회한다."""
    seen_objects: set[int] = set()

    for content_index, content in enumerate(document.get("intro") or []):
        yield from _iter_tables_in_value(
            content,
            section_id="intro",
            section_path=["문서 도입부"],
            content_index=content_index,
            object_path=["intro", str(content_index)],
            nested_depth=0,
            seen_objects=seen_objects,
        )

    def walk_sections(sections, parent_path: list[str]):
        for section in sections or []:
            if not isinstance(section, dict):
                continue

            title = clean_text(
                section.get("normalized_title")
                or section.get("title")
            )
            section_path = [*parent_path, *([title] if title else [])]
            section_id = str(section.get("section_id") or "")

            for content_index, content in enumerate(section.get("contents") or []):
                yield from _iter_tables_in_value(
                    content,
                    section_id=section_id,
                    section_path=section_path,
                    content_index=content_index,
                    object_path=[section_id or "section", "contents", str(content_index)],
                    nested_depth=0,
                    seen_objects=seen_objects,
                )

            yield from walk_sections(section.get("children") or [], section_path)

    yield from walk_sections(document.get("sections") or [], [])


def _sortable_table_index(value: Any) -> tuple[int, Any]:
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _display_table_indexes(values: set[str]) -> list[Any]:
    result: list[Any] = []
    for value in sorted(values, key=_sortable_table_index):
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            result.append(value)
    return result


def finalize_structured_document(document: dict[str, Any]) -> dict[str, Any]:
    """최상위 표와 중첩 표를 한 번의 재귀 흐름으로 후처리한다."""
    resolved_table_indexes: set[str] = set()
    processed_keys: set[tuple[str, Any]] = set()
    details: list[dict[str, Any]] = []
    nested_table_count = 0
    nested_table_resolved_count = 0
    processed_table_count = 0

    for record in iter_tables_recursive(document):
        table = record["table"]
        key = _table_key(table)
        if key in processed_keys:
            continue
        processed_keys.add(key)
        processed_table_count += 1

        table_index = table.get("table_index")
        table_index_key = str(table_index) if table_index is not None else None
        nested_depth = int(record.get("nested_depth") or 0)
        if nested_depth > 0:
            nested_table_count += 1

        structured = table.get("structured_table") or {}
        if (
            isinstance(structured, dict)
            and structured.get("status") in {"structured", "partially_structured"}
            and structured.get("layout") in {"row_records", "key_value"}
        ):
            details.append({
                "table_index": table_index,
                "status": "already_structured",
                "layout": structured.get("layout"),
                "section_id": record["section_id"],
                "nested_depth": nested_depth,
                "object_path": copy.deepcopy(record["object_path"]),
            })
            continue

        replacement, reason = structure_unresolved_table(table)
        if replacement:
            replacement["postprocess_source"] = {
                "section_id": record["section_id"],
                "section_path": copy.deepcopy(record["section_path"]),
                "content_index": record["content_index"],
                "object_path": copy.deepcopy(record["object_path"]),
                "nested_depth": nested_depth,
            }
            replacement["nested_table"] = nested_depth > 0
            table["structured_table"] = replacement

            if table_index_key is not None:
                resolved_table_indexes.add(table_index_key)
            if nested_depth > 0:
                nested_table_resolved_count += 1

            details.append({
                "table_index": table_index,
                "status": "structured",
                "layout": replacement.get("layout"),
                "orientation": replacement.get("orientation"),
                "section_id": record["section_id"],
                "nested_depth": nested_depth,
                "object_path": copy.deepcopy(record["object_path"]),
            })
        else:
            details.append({
                "table_index": table_index,
                "status": "unchanged",
                "reason": reason,
                "section_id": record["section_id"],
                "nested_depth": nested_depth,
                "object_path": copy.deepcopy(record["object_path"]),
            })

    unresolved = document.get("table_unresolved")
    if isinstance(unresolved, list) and resolved_table_indexes:
        document["table_unresolved"] = [
            item for item in unresolved
            if str(item.get("table_index")) not in resolved_table_indexes
        ]

    resolved_values = _display_table_indexes(resolved_table_indexes)
    method = document.setdefault("table_structuring_method", {})
    method["postprocessing"] = {
        "version": "step3-postprocess-v3-explicit-recursive",
        "processed_table_count": processed_table_count,
        "resolved_table_count": len(resolved_values),
        "resolved_table_indexes": resolved_values,
        "nested_table_count": nested_table_count,
        "nested_table_resolved_count": nested_table_resolved_count,
        "details": details,
        "rules": [
            "intro와 모든 Section의 표를 한 번의 재귀 순회로 검사",
            "각 cell.blocks 내부 중첩 표를 독립적으로 구조화",
            "동일 표 객체 참조에 한해서만 중복 처리 방지",
            "첫 열이 필드명인 가로형 표를 열 단위 레코드로 전치",
            "3행×2열 일정표를 구분·일정·장소 레코드로 전치",
            "첫 행 Header 표에서 row_span 값을 데이터 행에 상속",
            "부모 표가 fallback이어도 중첩 표 구조화 결과 유지",
            "단일 셀 제목 표는 fallback으로 유지",
        ],
    }

    document["stage"] = "structured"
    return document


def update_json_file(path: str | Path, transform) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"JSON 파일을 찾을 수 없습니다: {target}")

    try:
        with target.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {target} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(data, dict):
        raise ValueError("JSON 최상위 값은 객체여야 합니다.")

    transform(data)

    with target.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    return data


def finalize_step2_file(path: str | Path) -> dict[str, Any]:
    """Step 2 규칙은 build_domain_step2.py에서 모두 처리한다."""
    return update_json_file(path, lambda document: document)


def finalize_step3_file(path: str | Path) -> dict[str, Any]:
    return update_json_file(path, finalize_structured_document)
