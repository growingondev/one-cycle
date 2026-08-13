#!/usr/bin/env python3
"""의미 기반 구조화 3단계: 표 세부 구조화.

입력:
- 2단계 계층 보정 결과인 *_step2-5_domain_repaired.json

출력:
- *_step3-1_table_headers.json
    : 격자/헤더 분석 결과

- *_step3-2_table_mappings.json
    : 헤더-데이터 매핑 결과

- *_step3-3_structured_tables.json
    : structured_table이 추가된 최종 결과

목표:
- 공통 JSON의 row/col/row_span/col_span 정보를 이용해
  표의 의미 구조를 복원한다.
- 세로 병합(row_span)은 해당 데이터 행에 상속한다.
- 가로 병합(col_span > 1) 데이터 셀은 여러 Header에
  같은 값을 중복 매핑하지 않는다.
- 가로 병합 데이터 셀은 record.merged_values에 한 번만 저장하고,
  실제로 덮고 있는 column과 header_path를 별도로 기록한다.
- '소계', '합계', '총계' 등의 행은 subtotal/total 행으로 표시한다.
- 확실하지 않은 표는 억지로 구조화하지 않고 원본 cells를 유지한다.
"""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any

from tkinter import Tk, messagebox
from tkinter.filedialog import askopenfilename


# ===========================================================================
# 텍스트 처리
# ===========================================================================

def clean_text(
    value: Any,
) -> str:
    """일반 텍스트 정리.

    줄바꿈 자체는 보존한다.
    연속 공백과 연속 줄바꿈만 정리한다.
    """

    text = (
        ""
        if value is None
        else str(value)
    )

    text = text.replace(
        "\r",
        "\n",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n+",
        "\n",
        text,
    )

    return text.strip()


def compact(
    value: Any,
) -> str:
    """비교용 문자열.

    모든 공백과 줄바꿈을 제거한다.
    """

    return re.sub(
        r"\s+",
        "",
        clean_text(value),
    )


# ===========================================================================
# 값 유형 판단
# ===========================================================================

def looks_numeric_or_date(
    text: str,
) -> bool:
    """숫자, 날짜, 시간, 단위 값 여부를 단순 판별한다."""

    value = (
        compact(text)
        .replace(
            ",",
            "",
        )
    )

    if not value:
        return False

    patterns = [
        r"^[+-]?\d+(?:\.\d+)?$",
        r"^\d{4}[.\-/]\d{1,2}(?:[.\-/]\d{1,2})?",
        r"^\d{1,2}:\d{2}",
        r"^\d+(?:\.\d+)?(?:㎡|m2|세대|호|원|개월|년|%)$",
        r"^\d+동\d+호$",
    ]

    return any(
        re.search(
            pattern,
            value,
            re.IGNORECASE,
        )
        for pattern
        in patterns
    )


def looks_identifier(
    text: str,
) -> bool:
    """주택형 등의 식별자 형태인지 판단한다."""

    value = compact(text)

    return (
        bool(
            re.fullmatch(
                r"\d+(?:\.\d+)?[A-Za-z가-힣-]*",
                value,
            )
        )
        and any(
            char.isdigit()
            for char
            in value
        )
    )


# ===========================================================================
# 셀 범위
# ===========================================================================

def cell_range(
    cell: dict[str, Any],
) -> tuple[
    int,
    int,
    int,
    int,
]:
    """셀 시작 좌표와 병합 범위를 반환한다."""

    row = int(
        cell.get(
            "row",
            0,
        )
        or 0
    )

    col = int(
        cell.get(
            "col",
            0,
        )
        or 0
    )

    row_span = max(
        1,
        int(
            cell.get(
                "row_span",
                1,
            )
            or 1
        ),
    )

    col_span = max(
        1,
        int(
            cell.get(
                "col_span",
                1,
            )
            or 1
        ),
    )

    return (
        row,
        col,
        row_span,
        col_span,
    )


# ===========================================================================
# Grid 복원
# ===========================================================================

def build_grid(
    table: dict[str, Any],
) -> tuple[
    list[
        list[
            dict[str, Any]
            | None
        ]
    ],
    list[str],
]:
    """row/col/span을 이용해 논리적 Grid를 복원한다."""

    rows = int(
        table.get(
            "row_count",
            0,
        )
        or 0
    )

    cols = int(
        table.get(
            "col_count",
            0,
        )
        or 0
    )

    grid: list[
        list[
            dict[str, Any]
            | None
        ]
    ] = [
        [
            None
            for _ in range(
                cols
            )
        ]
        for _ in range(
            rows
        )
    ]

    errors: list[str] = []

    for cell in (
        table.get(
            "cells",
            [],
        )
        or []
    ):
        (
            row,
            col,
            row_span,
            col_span,
        ) = cell_range(
            cell
        )

        if (
            row < 0
            or col < 0
            or row + row_span > rows
            or col + col_span > cols
        ):
            errors.append(
                "병합 범위 초과: "
                f"row={row}, "
                f"col={col}, "
                f"row_span={row_span}, "
                f"col_span={col_span}"
            )

            continue

        # 하나의 실제 원본 Cell을 나타내는 참조 객체
        ref = {
            "origin_row": row,
            "origin_col": col,
            "row_span": row_span,
            "col_span": col_span,
            "text": clean_text(
                cell.get(
                    "text"
                )
            ),
            "cell": cell,
        }

        for target_row in range(
            row,
            row + row_span,
        ):
            for target_col in range(
                col,
                col + col_span,
            ):
                if (
                    grid[
                        target_row
                    ][
                        target_col
                    ]
                    is not None
                    and grid[
                        target_row
                    ][
                        target_col
                    ]
                    is not ref
                ):
                    errors.append(
                        "셀 범위 겹침: "
                        f"row={target_row}, "
                        f"col={target_col}"
                    )

                grid[
                    target_row
                ][
                    target_col
                ] = ref

    return (
        grid,
        errors,
    )


# ===========================================================================
# 행 단위 원본 셀
# ===========================================================================

def origin_cells_in_row(
    table: dict[str, Any],
    row: int,
) -> list[
    dict[str, Any]
]:
    """해당 행에서 실제로 시작하는 원본 Cell만 반환한다."""

    cells: list[
        dict[str, Any]
    ] = []

    for cell in (
        table.get(
            "cells",
            [],
        )
        or []
    ):
        if (
            int(
                cell.get(
                    "row",
                    0,
                )
                or 0
            )
            == row
        ):
            cells.append(
                cell
            )

    return sorted(
        cells,
        key=lambda item: int(
            item.get(
                "col",
                0,
            )
            or 0
        ),
    )


# ===========================================================================
# Header 판단
# ===========================================================================

def row_is_header_like(
    table: dict[str, Any],
    row: int,
) -> bool:
    """행이 Header처럼 보이는지 판단한다."""

    cells = origin_cells_in_row(
        table,
        row,
    )

    texts = [
        clean_text(
            cell.get(
                "text"
            )
        )
        for cell
        in cells
        if clean_text(
            cell.get(
                "text"
            )
        )
    ]

    if not texts:
        return True

    numeric_count = sum(
        looks_numeric_or_date(
            text
        )
        or looks_identifier(
            text
        )
        for text
        in texts
    )

    avg_len = (
        sum(
            len(text)
            for text
            in texts
        )
        / len(texts)
    )

    long_count = sum(
        len(text) > 35
        for text
        in texts
    )

    # 다단 Header는 보통:
    # - 숫자형 실제 값이 적고
    # - 긴 문장이 적고
    # - 평균 문자열 길이가 짧다.
    return (
        numeric_count == 0
        and long_count == 0
        and avg_len <= 18
    )


# ===========================================================================
# Key-Value 표 판단
# ===========================================================================

def detect_key_value_layout(
    table: dict[str, Any],
    grid: list[
        list[
            dict[str, Any]
            | None
        ]
    ],
) -> tuple[
    bool,
    int,
]:
    """2열 Key-Value 형태의 표인지 판단한다."""

    rows = int(
        table.get(
            "row_count",
            0,
        )
        or 0
    )

    cols = int(
        table.get(
            "col_count",
            0,
        )
        or 0
    )

    if (
        cols != 2
        or rows < 2
    ):
        return (
            False,
            0,
        )

    start = 0

    first = origin_cells_in_row(
        table,
        0,
    )

    # 첫 행 전체가 병합된 경우
    # 표 제목 행일 가능성이 높다.
    if (
        len(first) == 1
        and int(
            first[0].get(
                "col_span",
                1,
            )
            or 1
        )
        >= 2
    ):
        start = 1

    label_rows = 0
    usable = 0

    for row in range(
        start,
        rows,
    ):
        left = clean_text(
            grid[row][0]["text"]
            if grid[row][0]
            else ""
        )

        right = clean_text(
            grid[row][1]["text"]
            if grid[row][1]
            else ""
        )

        if (
            left
            or right
        ):
            usable += 1

        if (
            left
            and len(left) <= 25
            and right
        ):
            label_rows += 1

    if usable == 0:
        return (
            False,
            start,
        )

    return (
        label_rows
        / usable
        >= 0.66,
        start,
    )


# ===========================================================================
# Header Row 탐지
# ===========================================================================

def detect_header_rows(
    table: dict[str, Any],
) -> list[int]:
    """표 상단의 연속 Header 행을 탐지한다."""

    rows = int(
        table.get(
            "row_count",
            0,
        )
        or 0
    )

    if rows <= 1:
        return []

    (
        grid,
        _,
    ) = build_grid(
        table
    )

    header_rows: list[
        int
    ] = []

    for row in range(
        rows
    ):
        if row_is_header_like(
            table,
            row,
        ):
            header_rows.append(
                row
            )

            continue

        # 바로 위 행의 가로 병합 Header를
        # 세분화하는 다음 행은 길이가 길더라도
        # Header일 가능성이 있다.
        if (
            row > 0
            and header_rows
        ):
            row_cells = (
                origin_cells_in_row(
                    table,
                    row,
                )
            )

            continuation = bool(
                row_cells
            )

            for cell in (
                row_cells
            ):
                col = int(
                    cell.get(
                        "col",
                        0,
                    )
                    or 0
                )

                above = (
                    grid[
                        row - 1
                    ][
                        col
                    ]
                    if (
                        grid
                        and col
                        < len(
                            grid[
                                row - 1
                            ]
                        )
                    )
                    else None
                )

                if (
                    not above
                    or int(
                        above.get(
                            "col_span",
                            1,
                        )
                        or 1
                    )
                    <= 1
                ):
                    continuation = False
                    break

            if continuation:
                header_rows.append(
                    row
                )

                continue

        break

    return header_rows


# ===========================================================================
# Header Path
# ===========================================================================

def dedupe_path(
    values: list[str],
) -> list[str]:
    """Header Path의 연속 중복을 제거한다."""

    result: list[
        str
    ] = []

    for value in (
        values
    ):
        value = clean_text(
            value
        )

        if (
            value
            and (
                not result
                or result[-1]
                != value
            )
        ):
            result.append(
                value
            )

    return result


def build_columns(
    grid: list[
        list[
            dict[str, Any]
            | None
        ]
    ],
    header_rows: list[int],
) -> list[
    dict[str, Any]
]:
    """각 Column별 Header Path를 생성한다."""

    if not grid:
        return []

    cols = len(
        grid[0]
    )

    result: list[
        dict[str, Any]
    ] = []

    for col in range(
        cols
    ):
        path: list[
            str
        ] = []

        sources: list[
            dict[str, int]
        ] = []

        for row in (
            header_rows
        ):
            ref = (
                grid[
                    row
                ][
                    col
                ]
            )

            if not ref:
                continue

            text = clean_text(
                ref[
                    "text"
                ]
            )

            if not text:
                continue

            path.append(
                text
            )

            source = {
                "row": (
                    ref[
                        "origin_row"
                    ]
                ),
                "col": (
                    ref[
                        "origin_col"
                    ]
                ),
            }

            if (
                source
                not in sources
            ):
                sources.append(
                    source
                )

        result.append(
            {
                "column": col,
                "header_path": (
                    dedupe_path(
                        path
                    )
                ),
                "header_sources": (
                    sources
                ),
            }
        )

    return result


# ===========================================================================
# 일반 Cell 값
# ===========================================================================

def value_for_position(
    grid: list[
        list[
            dict[str, Any]
            | None
        ]
    ],
    row: int,
    col: int,
) -> dict[str, Any] | None:
    """특정 Grid 좌표의 값을 반환한다."""

    ref = (
        grid[
            row
        ][
            col
        ]
    )

    if not ref:
        return None

    return {
        "value": clean_text(
            ref[
                "text"
            ]
        ),
        "source": {
            "row": (
                ref[
                    "origin_row"
                ]
            ),
            "col": (
                ref[
                    "origin_col"
                ]
            ),
        },
        "row_span": (
            ref[
                "row_span"
            ]
        ),
        "col_span": (
            ref[
                "col_span"
            ]
        ),
        "inherited": (
            ref[
                "origin_row"
            ]
            != row
            or ref[
                "origin_col"
            ]
            != col
        ),
    }


# ===========================================================================
# 행 종류 판별
# ===========================================================================

def classify_row_kind(
    merged_values: list[
        dict[str, Any]
    ],
) -> str:
    """병합 데이터의 텍스트를 보고 subtotal/total 여부를 판단한다."""

    labels = [
        compact(
            item.get(
                "value"
            )
        )
        for item
        in merged_values
    ]

    for label in labels:
        if label in {
            "소계",
            "부분합계",
        }:
            return "subtotal"

        if label in {
            "합계",
            "총계",
            "전체합계",
        }:
            return "total"

    return "data"


# ===========================================================================
# 가로 병합 데이터 처리
# ===========================================================================

def build_merged_value(
    ref: dict[str, Any],
    columns: list[
        dict[str, Any]
    ],
    row: int,
) -> dict[str, Any]:
    """가로 병합된 Data Cell을 한 개의 의미 객체로 만든다.

    예:
        row=4, col=1, col_span=9, text="소 계"

    기존:
        col1  -> 소 계
        col2  -> 소 계
        ...
        col9  -> 소 계

    수정:
        merged_values [
            {
                value: "소 계",
                source: {row: 4, col: 1},
                covered_columns: [1,2,...,9],
                covered_header_paths: [...]
            }
        ]

    즉, 값을 실제 Header 9개에 각각 중복 매핑하지 않는다.
    """

    origin_col = int(
        ref[
            "origin_col"
        ]
    )

    col_span = int(
        ref[
            "col_span"
        ]
    )

    end_col = min(
        origin_col
        + col_span,
        len(columns),
    )

    covered_columns = list(
        range(
            origin_col,
            end_col,
        )
    )

    covered_header_paths: list[
        dict[str, Any]
    ] = []

    for column_index in (
        covered_columns
    ):
        column_info = next(
            (
                column
                for column
                in columns
                if int(
                    column.get(
                        "column",
                        -1,
                    )
                )
                == column_index
            ),
            None,
        )

        if not column_info:
            continue

        covered_header_paths.append(
            {
                "column": (
                    column_index
                ),
                "header_path": (
                    copy.deepcopy(
                        column_info.get(
                            "header_path",
                            [],
                        )
                    )
                ),
            }
        )

    return {
        "value": clean_text(
            ref[
                "text"
            ]
        ),
        "source": {
            "row": (
                ref[
                    "origin_row"
                ]
            ),
            "col": (
                ref[
                    "origin_col"
                ]
            ),
        },
        "row_span": (
            ref[
                "row_span"
            ]
        ),
        "col_span": (
            ref[
                "col_span"
            ]
        ),
        "inherited": (
            ref[
                "origin_row"
            ]
            != row
        ),
        "status": (
            "merged_data_span"
        ),
        "covered_columns": (
            covered_columns
        ),
        "covered_header_paths": (
            covered_header_paths
        ),
    }


# ===========================================================================
# Row Record 매핑
# ===========================================================================

def build_row_record(
    grid: list[
        list[
            dict[str, Any]
            | None
        ]
    ],
    row: int,
    columns: list[
        dict[str, Any]
    ],
) -> dict[str, Any] | None:
    """한 데이터 행을 구조화한다.

    핵심:
    - col_span == 1
        일반 Header ↔ Value 매핑

    - col_span > 1
        같은 원본 셀을 여러 열에 반복 매핑하지 않고
        merged_values에 한 번만 저장
    """

    values: list[
        dict[str, Any]
    ] = []

    merged_values: list[
        dict[str, Any]
    ] = []

    # 같은 원본 가로 병합 Cell이 여러 Grid 좌표에서
    # 반복 발견되는 것을 방지한다.
    seen_merged_sources: set[
        tuple[
            int,
            int,
        ]
    ] = set()

    nonempty = 0

    for column in (
        columns
    ):
        col = int(
            column[
                "column"
            ]
        )

        ref = (
            grid[
                row
            ][
                col
            ]
        )

        if not ref:
            continue

        value = clean_text(
            ref[
                "text"
            ]
        )

        # ---------------------------------------------------------------
        # 가로 병합 Data Cell
        # ---------------------------------------------------------------

        if (
            int(
                ref[
                    "col_span"
                ]
            )
            > 1
        ):
            source_key = (
                int(
                    ref[
                        "origin_row"
                    ]
                ),
                int(
                    ref[
                        "origin_col"
                    ]
                ),
            )

            if (
                source_key
                not in seen_merged_sources
            ):
                merged_item = (
                    build_merged_value(
                        ref,
                        columns,
                        row,
                    )
                )

                merged_values.append(
                    merged_item
                )

                seen_merged_sources.add(
                    source_key
                )

                if value:
                    nonempty += 1

            # 중요:
            # 가로 병합 값을 개별 Header 값으로
            # 다시 values에 넣지 않는다.
            continue

        # ---------------------------------------------------------------
        # 일반 Cell 또는 세로 병합 Cell
        # ---------------------------------------------------------------

        mapped = value_for_position(
            grid,
            row,
            col,
        )

        if not mapped:
            continue

        if mapped[
            "value"
        ]:
            nonempty += 1

        values.append(
            {
                "column": col,
                "header_path": (
                    copy.deepcopy(
                        column.get(
                            "header_path",
                            [],
                        )
                    )
                ),
                "value": (
                    mapped[
                        "value"
                    ]
                ),
                "source": (
                    mapped[
                        "source"
                    ]
                ),
                "inherited": (
                    mapped[
                        "inherited"
                    ]
                ),
                "status": (
                    "mapped"
                    if column.get(
                        "header_path"
                    )
                    else (
                        "unresolved_header"
                    )
                ),
            }
        )

    if nonempty == 0:
        return None

    record: dict[
        str,
        Any,
    ] = {
        "row_index": row,
        "row_kind": (
            classify_row_kind(
                merged_values
            )
        ),
        "values": values,
    }

    if merged_values:
        record[
            "merged_values"
        ] = merged_values

    return record


# ===========================================================================
# 표 분석
# ===========================================================================

def analyze_table(
    table: dict[str, Any],
    section_info: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    """표를 분석하고 Header/Data Mapping 결과를 생성한다."""

    table_index = (
        table.get(
            "table_index"
        )
    )

    rows = int(
        table.get(
            "row_count",
            0,
        )
        or 0
    )

    cols = int(
        table.get(
            "col_count",
            0,
        )
        or 0
    )

    (
        grid,
        errors,
    ) = build_grid(
        table
    )

    base = {
        "table_index": (
            table_index
        ),
        "section_id": (
            section_info.get(
                "section_id"
            )
        ),
        "section_path": (
            section_info.get(
                "section_path"
            )
        ),
        "domain": (
            copy.deepcopy(
                section_info.get(
                    "domain"
                )
            )
        ),
        "row_count": rows,
        "col_count": cols,
    }

    # -----------------------------------------------------------------------
    # Grid 오류
    # -----------------------------------------------------------------------

    if errors:
        reason = "; ".join(
            errors
        )

        analysis = {
            **base,
            "status": (
                "unresolved"
            ),
            "reason": reason,
            "layout": None,
            "header_rows": [],
            "columns": [],
        }

        mapping = {
            **base,
            "status": (
                "unresolved"
            ),
            "reason": reason,
            "records": [],
        }

        return (
            analysis,
            mapping,
        )

    # -----------------------------------------------------------------------
    # 1행 또는 1열 Layout Table
    # -----------------------------------------------------------------------

    if (
        rows <= 1
        or cols <= 1
    ):
        reason = (
            "행 또는 열이 하나뿐인 "
            "안내/레이아웃 표"
        )

        analysis = {
            **base,
            "status": (
                "skipped"
            ),
            "reason": reason,
            "layout": (
                "layout"
            ),
            "header_rows": [],
            "columns": [],
        }

        mapping = {
            **base,
            "status": (
                "skipped"
            ),
            "reason": reason,
            "records": [],
        }

        return (
            analysis,
            mapping,
        )

    # -----------------------------------------------------------------------
    # Key-Value Table
    # -----------------------------------------------------------------------

    (
        is_key_value,
        key_value_start,
    ) = detect_key_value_layout(
        table,
        grid,
    )

    if is_key_value:
        columns = [
            {
                "column": 0,
                "header_path": [
                    "항목"
                ],
                "header_sources": [],
            },
            {
                "column": 1,
                "header_path": [
                    "값"
                ],
                "header_sources": [],
            },
        ]

        analysis = {
            **base,
            "status": (
                "structured"
            ),
            "layout": (
                "key_value"
            ),
            "title_rows": list(
                range(
                    key_value_start
                )
            ),
            "header_rows": [],
            "columns": columns,
        }

        records: list[
            dict[str, Any]
        ] = []

        for row in range(
            key_value_start,
            rows,
        ):
            left = value_for_position(
                grid,
                row,
                0,
            )

            right = value_for_position(
                grid,
                row,
                1,
            )

            if (
                not left
                or not right
            ):
                continue

            if (
                not left[
                    "value"
                ]
                and not right[
                    "value"
                ]
            ):
                continue

            records.append(
                {
                    "row_index": (
                        row
                    ),
                    "key": (
                        left[
                            "value"
                        ]
                    ),
                    "value": (
                        right[
                            "value"
                        ]
                    ),
                    "key_source": (
                        left[
                            "source"
                        ]
                    ),
                    "value_source": (
                        right[
                            "source"
                        ]
                    ),
                }
            )

        mapping = {
            **base,
            "status": (
                "structured"
            ),
            "layout": (
                "key_value"
            ),
            "records": (
                records
            ),
        }

        return (
            analysis,
            mapping,
        )

    # -----------------------------------------------------------------------
    # Row Records
    # -----------------------------------------------------------------------

    header_rows = (
        detect_header_rows(
            table
        )
    )

    if (
        not header_rows
        or len(
            header_rows
        )
        >= rows
    ):
        reason = (
            "헤더 행과 데이터 행의 경계를 "
            "안정적으로 판단하지 못함"
        )

        analysis = {
            **base,
            "status": (
                "unresolved"
            ),
            "reason": reason,
            "layout": None,
            "header_rows": (
                header_rows
            ),
            "columns": [],
        }

        mapping = {
            **base,
            "status": (
                "unresolved"
            ),
            "reason": reason,
            "records": [],
        }

        return (
            analysis,
            mapping,
        )

    columns = build_columns(
        grid,
        header_rows,
    )

    missing = [
        column[
            "column"
        ]
        for column
        in columns
        if not column[
            "header_path"
        ]
    ]

    analysis_status = (
        "partially_structured"
        if missing
        else "structured"
    )

    analysis = {
        **base,
        "status": (
            analysis_status
        ),
        "layout": (
            "row_records"
        ),
        "header_rows": (
            header_rows
        ),
        "data_start_row": (
            max(
                header_rows
            )
            + 1
        ),
        "columns": (
            columns
        ),
        "unresolved_columns": (
            missing
        ),
    }

    records: list[
        dict[str, Any]
    ] = []

    for row in range(
        max(
            header_rows
        )
        + 1,
        rows,
    ):
        record = build_row_record(
            grid,
            row,
            columns,
        )

        if record:
            records.append(
                record
            )

    mapping_status = (
        analysis_status
        if records
        else "unresolved"
    )

    mapping = {
        **base,
        "status": (
            mapping_status
        ),
        "layout": (
            "row_records"
        ),
        "records": (
            records
        ),
        "unresolved_columns": (
            missing
        ),
    }

    return (
        analysis,
        mapping,
    )


# ===========================================================================
# Section 순회
# ===========================================================================

def walk_sections(
    sections: list[
        dict[str, Any]
    ],
    path: list[str]
    | None = None,
):
    """모든 Section을 재귀 순회한다."""

    path = (
        path
        or []
    )

    for section in (
        sections
    ):
        title = str(
            section.get(
                "title"
            )
            or ""
        )

        current = (
            path
            + [
                title
            ]
        )

        yield (
            section,
            current,
        )

        children = (
            section.get(
                "children"
            )
            or []
        )

        if isinstance(
            children,
            list,
        ):
            yield from walk_sections(
                children,
                current,
            )


# ===========================================================================
# 모든 표 재귀 순회
# ===========================================================================

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def iter_tables_recursive(source: dict[str, Any]):
    """intro, Section contents, cell.blocks 안의 중첩 표를 모두 순회한다."""

    seen: set[int] = set()

    def walk_value(
        value: Any,
        *,
        section_id: str,
        section_path: list[str],
        object_path: list[str],
        nested_depth: int,
    ):
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield from walk_value(
                    child,
                    section_id=section_id,
                    section_path=section_path,
                    object_path=[*object_path, str(index)],
                    nested_depth=nested_depth,
                )
            return

        if not isinstance(value, dict):
            return

        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)

        if value.get("type") == "table":
            yield {
                "table": value,
                "section_id": section_id,
                "section_path": list(section_path),
                "domain": None,
                "object_path": list(object_path),
                "nested_depth": nested_depth,
            }

            cells = [
                cell for cell in value.get("cells") or []
                if isinstance(cell, dict)
            ]
            cells.sort(
                key=lambda cell: (
                    _safe_int(cell.get("row")),
                    _safe_int(cell.get("col", cell.get("column"))),
                )
            )
            for cell in cells:
                row = _safe_int(cell.get("row"))
                col = _safe_int(cell.get("col", cell.get("column")))
                yield from walk_value(
                    cell.get("blocks") or [],
                    section_id=section_id,
                    section_path=section_path,
                    object_path=[*object_path, f"cell:{row},{col}", "blocks"],
                    nested_depth=nested_depth + 1,
                )
            return

        for key, child in value.items():
            if key in {"source", "domain", "structured_table"}:
                continue
            if isinstance(child, (dict, list)):
                yield from walk_value(
                    child,
                    section_id=section_id,
                    section_path=section_path,
                    object_path=[*object_path, str(key)],
                    nested_depth=nested_depth,
                )

    for index, content in enumerate(source.get("intro") or []):
        yield from walk_value(
            content,
            section_id="intro",
            section_path=["문서 도입부"],
            object_path=["intro", str(index)],
            nested_depth=0,
        )

    def walk_section_list(sections: list[dict[str, Any]], parent_path: list[str]):
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            title = str(section.get("normalized_title") or section.get("title") or "").strip()
            path = [*parent_path, *([title] if title else [])]
            section_id = str(section.get("section_id") or "")
            domain = copy.deepcopy(section.get("domain"))

            for index, content in enumerate(section.get("contents") or []):
                for record in walk_value(
                    content,
                    section_id=section_id,
                    section_path=path,
                    object_path=[section_id or "section", "contents", str(index)],
                    nested_depth=0,
                ):
                    record["domain"] = domain
                    yield record

            yield from walk_section_list(section.get("children") or [], path)

    yield from walk_section_list(source.get("sections") or [], [])


# ===========================================================================
# Step 3 결과 생성
# ===========================================================================

def build_results(
    source: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """Step 3-1 ~ Step 3-3 결과를 생성한다."""

    if not isinstance(
        source.get(
            "sections"
        ),
        list,
    ):
        raise ValueError(
            "2단계 최종 계층 JSON이 아닙니다. "
            "sections 배열이 없습니다."
        )

    final_doc = (
        copy.deepcopy(
            source
        )
    )

    analyses: list[
        dict[str, Any]
    ] = []

    mappings: list[
        dict[str, Any]
    ] = []

    unresolved: list[
        dict[str, Any]
    ] = []

    total = 0
    nested_total = 0

    for record in iter_tables_recursive(final_doc):
        content = record["table"]
        path = record["section_path"]
        nested_depth = int(record.get("nested_depth") or 0)
        object_path = list(record.get("object_path") or [])

        info = {
            "section_id": record.get("section_id"),
            "section_path": path,
            "domain": record.get("domain"),
        }

        total += 1
        if nested_depth > 0:
            nested_total += 1

        analysis, mapping = analyze_table(content, info)
        analysis["nested_depth"] = nested_depth
        analysis["object_path"] = object_path
        mapping["nested_depth"] = nested_depth
        mapping["object_path"] = object_path

        analyses.append(analysis)
        mappings.append(mapping)

        # 원본 cells는 그대로 두고 구조화 결과만 추가한다.
        content["structured_table"] = {
            "status": mapping["status"],
            "layout": mapping.get("layout"),
            "header_rows": analysis.get("header_rows", []),
            "columns": analysis.get("columns", []),
            "records": mapping.get("records", []),
            "nested_table": nested_depth > 0,
            "nested_depth": nested_depth,
            "object_path": object_path,
        }

        if analysis.get("reason"):
            content["structured_table"]["reason"] = analysis["reason"]
        if analysis.get("unresolved_columns"):
            content["structured_table"]["unresolved_columns"] = analysis["unresolved_columns"]

        if mapping["status"] in {
            "unresolved", "skipped", "partially_structured"
        }:
            unresolved.append({
                "table_index": content.get("table_index"),
                "section_id": record.get("section_id"),
                "section_path": path,
                "nested_depth": nested_depth,
                "object_path": object_path,
                "status": mapping["status"],
                "reason": analysis.get("reason") or (
                    "일부 열의 헤더 미해석"
                    if analysis.get("unresolved_columns") else None
                ),
                "unresolved_columns": analysis.get("unresolved_columns", []),
            })

    # -----------------------------------------------------------------------
    # Step 3-1
    # -----------------------------------------------------------------------

    step3_1 = {
        "document": (
            copy.deepcopy(
                source.get(
                    "document",
                    {},
                )
            )
        ),
        "step": "3-1",
        "description": (
            "표 격자 및 헤더 경로 분석 결과"
        ),
        "summary": {
            "total_tables": (
                total
            ),
            "analyzed_tables": (
                len(
                    analyses
                )
            ),
            "nested_tables": nested_total,
        },
        "tables": (
            analyses
        ),
    }

    # -----------------------------------------------------------------------
    # Step 3-2
    # -----------------------------------------------------------------------

    step3_2 = {
        "document": (
            copy.deepcopy(
                source.get(
                    "document",
                    {},
                )
            )
        ),
        "step": "3-2",
        "description": (
            "헤더와 데이터 값 매핑 결과"
        ),
        "summary": {
            "total_tables": (
                total
            ),
            "structured": sum(
                mapping[
                    "status"
                ]
                == "structured"
                for mapping
                in mappings
            ),
            "partially_structured": sum(
                mapping[
                    "status"
                ]
                == "partially_structured"
                for mapping
                in mappings
            ),
            "unresolved": sum(
                mapping[
                    "status"
                ]
                == "unresolved"
                for mapping
                in mappings
            ),
            "skipped": sum(
                mapping[
                    "status"
                ]
                == "skipped"
                for mapping
                in mappings
            ),
        },
        "tables": (
            mappings
        ),
    }

    # -----------------------------------------------------------------------
    # Step 3-3
    # -----------------------------------------------------------------------

    final_doc[
        "table_structuring_method"
    ] = {
        "step": "3-3",
        "version": "step3-v2-recursive-tables",
        "recursive_table_policy": (
            "intro, section contents, cell.blocks의 중첩 표까지 독립적으로 분석"
        ),
        "method": (
            "grid_restore_header_path_"
            "row_mapping_and_horizontal_merge_dedup"
        ),
        "domain_usage": (
            "부모 section 도메인은 기록/보조 정보로만 사용하고 "
            "실제 매핑은 셀 좌표와 헤더 텍스트 기준"
        ),
        "vertical_merge_policy": (
            "row_span 병합 값은 각 데이터 행에 상속"
        ),
        "horizontal_merge_policy": (
            "col_span > 1 데이터 셀은 개별 열에 반복 매핑하지 않고 "
            "record.merged_values에 한 번만 저장"
        ),
        "subtotal_policy": (
            "소계/합계/총계 가로 병합 행은 "
            "row_kind=subtotal 또는 total로 기록"
        ),
        "original_preservation": (
            "원본 cells 유지 후 structured_table 추가"
        ),
        "unresolved_policy": (
            "판단 불가 표는 원본 유지 및 "
            "unresolved/skipped 기록"
        ),
    }

    final_doc[
        "table_unresolved"
    ] = unresolved

    return (
        step3_1,
        step3_2,
        final_doc,
    )


# ===========================================================================
# JSON 저장
# ===========================================================================

def save_json(
    path: str,
    data: dict[str, Any],
) -> None:
    """JSON 저장."""

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ===========================================================================
# 파일 처리
# ===========================================================================

def process(
    input_path: str,
    output_dir: str,
) -> tuple[
    str,
    str,
    str,
]:
    """입력 파일을 처리하고 Step3 결과 3개를 저장한다."""

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Step 2 JSON 파일을 찾을 수 없습니다: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8") as file:
            source = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {input_path} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(source, dict):
        raise ValueError("Step 2 JSON 최상위 값은 객체여야 합니다.")

    (
        step3_1,
        step3_2,
        step3_3,
    ) = build_results(
        source
    )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    stem = os.path.splitext(
        os.path.basename(
            input_path
        )
    )[0]

    # Step2-3 또는 Step2-5를 입력해도
    # 최종 Step3 파일명은 동일하게 생성
    stem = re.sub(
        r"_(?:step2-3_domain_tagged|step2-5_domain_repaired)$",
        "",
        stem,
    )

    path_31 = os.path.join(
        output_dir,
        (
            f"{stem}_step3-1_"
            "table_headers.json"
        ),
    )

    path_32 = os.path.join(
        output_dir,
        (
            f"{stem}_step3-2_"
            "table_mappings.json"
        ),
    )

    path_33 = os.path.join(
        output_dir,
        (
            f"{stem}_step3-3_"
            "structured_tables.json"
        ),
    )

    save_json(
        path_31,
        step3_1,
    )

    save_json(
        path_32,
        step3_2,
    )

    save_json(
        path_33,
        step3_3,
    )

    return (
        path_31,
        path_32,
        path_33,
    )


# ===========================================================================
# 입력 파일 선택
# ===========================================================================

def select_input_json() -> str | None:
    """Step 2-5 보정 결과를 선택한다."""

    root = Tk()

    root.withdraw()

    root.attributes(
        "-topmost",
        True,
    )

    selected = (
        askopenfilename(
            title=(
                "2단계 계층 보정 JSON 선택"
            ),
            filetypes=[
                (
                    "Step2 repaired JSON",
                    "*_step2-5_domain_repaired.json",
                ),
                (
                    "JSON Files",
                    "*.json",
                ),
            ],
        )
    )

    root.destroy()

    return (
        selected
        or None
    )


# ===========================================================================
# 실행
# ===========================================================================

def main() -> None:
    input_path = (
        select_input_json()
    )

    if not input_path:
        print(
            "JSON 파일을 선택하지 않았습니다."
        )

        return

    script_dir = (
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        )
    )

    output_dir = (
        os.path.join(
            script_dir,
            "output",
        )
    )

    try:
        outputs = process(
            input_path,
            output_dir,
        )

    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
    ) as error:
        messagebox.showerror(
            "3단계 표 구조화 실패",
            str(error),
        )

        raise

    result = "\n".join(
        outputs
    )

    print(
        "3단계 표 구조화 완료\n"
        + result
    )

    messagebox.showinfo(
        "3단계 구조화 완료",
        (
            "다음 파일을 생성했습니다.\n\n"
            + result
        ),
    )


if __name__ == "__main__":
    main()