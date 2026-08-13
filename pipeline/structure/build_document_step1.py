#!/usr/bin/env python3
"""문서 계층 구조화 1단계.

1-1. 문서 요소를 순서대로 펼치고 제목 후보를 추출
1-2. 문서별 제목 표식(marker) 체계를 추론
1-3. 추론된 레벨을 이용해 계층 구조 생성

원칙:
- 확실하지 않은 제목은 억지로 계층화하지 않는다.
- 원문 문단/표는 삭제하지 않고 items 또는 contents에 보존한다.
- HWP/HWPX 공통 정규화 JSON만 입력으로 사용한다.
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Iterable
from tkinter import Tk, messagebox
from tkinter.filedialog import askopenfilename

ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"

MARKER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("chapter", re.compile(r"^\s*(제\s*\d+\s*[장편부])\s*(.+)$")),
    ("roman", re.compile(rf"^\s*([{ROMAN}])(?:[.．])?\s*(.+)$")),
    ("decimal", re.compile(r"^\s*(\d+(?:\.\d+)+)(?:[.)])?\s+(.+)$")),
    ("arabic_dot", re.compile(r"^\s*(\d+)[.．]\s*(.+)$")),
    ("arabic_paren", re.compile(r"^\s*\((\d+)\)\s*(.+)$")),
    ("arabic_rparen", re.compile(r"^\s*(\d+)\)\s*(.+)$")),
    ("circled", re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s*(.+)$")),
    ("korean_dot", re.compile(r"^\s*([가-하])[.．]\s*(.+)$")),
]

# 번호 표식이 없는 LH 공고문 제목을 보수적으로 판별하기 위한 규칙입니다.
# 일반 본문을 제목으로 오인하지 않도록 짧은 문장과 제목형 종결어만 허용합니다.
TITLE_BULLETS = "■□◆◇●○▣▶▷"

EXACT_UNNUMBERED_TITLES = {
    "알려드립니다",
    "계약 등 주요일정",
}

TITLE_SUFFIXES = (
    "안내",
    "일정",
    "자격",
    "대상",
    "규모",
    "가격",
    "금액",
    "납부",
    "방법",
    "절차",
    "서류",
    "제출서류",
    "구비서류",
    "유의사항",
    "문의처",
)

SENTENCE_ENDINGS = (
    "다.",
    "니다.",
    "합니다.",
    "됩니다.",
    "바랍니다.",
    "있습니다.",
    "없습니다.",
)

STANDALONE_MARKER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("chapter", re.compile(r"^(제\s*\d+\s*[장편부])$")),
    ("roman", re.compile(rf"^([{ROMAN}])(?:[.．])?$")),
    ("arabic_dot", re.compile(r"^(\d+)[.．]$")),
    ("arabic_paren", re.compile(r"^\((\d+)\)$")),
    ("arabic_rparen", re.compile(r"^(\d+)\)$")),
    ("circled", re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])$")),
    ("korean_dot", re.compile(r"^([가-하])[.．]$")),
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def parse_marker(text: str) -> dict[str, Any] | None:
    """강한 번호 표식이 있는 제목만 파싱한다."""
    text = clean_text(text)
    # 날짜(2026.07.10.)를 `2026.` 제목으로 오인하지 않는다.
    if re.fullmatch(r"\d{4}[.]\d{1,2}[.]\d{1,2}[.]?", text):
        return None
    for marker_type, pattern in MARKER_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        marker = clean_text(match.group(1))
        title = clean_text(match.group(2))
        if not title:
            return None
        return {
            "marker": marker,
            "marker_type": marker_type,
            "title": title,
            "full_text": text,
        }
    return None


def parse_standalone_marker(text: str) -> dict[str, str] | None:
    """표의 서로 다른 셀에 분리된 제목 번호만 판별합니다."""

    cleaned = clean_text(text)
    for marker_type, pattern in STANDALONE_MARKER_PATTERNS:
        match = pattern.fullmatch(cleaned)
        if match:
            return {
                "marker": clean_text(match.group(1)),
                "marker_type": marker_type,
            }
    return None


def table_texts(table: dict[str, Any]) -> list[str]:
    cells = sorted(table.get("cells", []), key=lambda c: (c.get("row", 0), c.get("col", 0)))
    return [clean_text(cell.get("text")) for cell in cells if clean_text(cell.get("text"))]


def table_heading_candidate(table: dict[str, Any]) -> dict[str, Any] | None:
    """작은 1행 표에서 강한 제목 표식을 찾는다.

    실제 데이터 표 오인을 줄이기 위해 1행, 4열 이하만 대상으로 한다.
    """
    if table.get("type") != "table":
        return None
    if table.get("row_count") != 1 or table.get("col_count", 999) > 4:
        return None

    texts = table_texts(table)
    if not texts:
        return None

    joined = clean_text(" ".join(texts))
    parsed = parse_marker(joined)
    if not parsed:
        return None

    parsed.update({
        "source_kind": "table",
        "source": copy.deepcopy(table.get("source", {})),
        "source_table_index": table.get("table_index"),
        "confidence": 1.0,
    })
    return parsed


def _strip_title_bullet(text: str) -> tuple[str, str | None]:
    """제목 앞의 장식용 글머리표를 분리합니다."""

    cleaned = clean_text(text)
    if cleaned and cleaned[0] in TITLE_BULLETS:
        return clean_text(cleaned[1:]), cleaned[0]
    return cleaned, None


def _looks_like_sentence(text: str) -> bool:
    """완전한 설명 문장처럼 보이면 제목 후보에서 제외합니다."""

    compact = clean_text(text)
    if not compact:
        return False
    if any(compact.endswith(ending) for ending in SENTENCE_ENDINGS):
        return True
    return len(compact) > 70


def semantic_heading_candidate(
    paragraph: dict[str, Any],
    *,
    next_block: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """번호가 없는 LH 공고문 제목을 보수적으로 판별합니다.

    강한 조건:
    - 정확히 알려진 단독 제목
    - ■ 등 제목형 글머리표 + 제목형 종결어
    - 짧은 제목형 문단 바로 뒤에 표가 오는 경우

    ※로 시작하는 주의 문장은 일반 본문으로 유지합니다.
    """

    original = clean_text(paragraph.get("text"))
    if not original or "\n" in original:
        return None

    title, bullet = _strip_title_bullet(original)
    if not title or _looks_like_sentence(title):
        return None

    exact_match = title in EXACT_UNNUMBERED_TITLES
    suffix_match = any(title.endswith(suffix) for suffix in TITLE_SUFFIXES)
    next_is_table = isinstance(next_block, dict) and next_block.get("type") == "table"

    marker_type: str | None = None
    level_hint: int | None = None
    confidence = 0.0
    reason = ""

    if exact_match:
        marker_type = "unnumbered_major"
        level_hint = 1 if title == "알려드립니다" else 3
        confidence = 0.98
        reason = "exact_unnumbered_title"
    elif bullet and suffix_match and len(title) <= 45:
        marker_type = "bullet_heading"
        level_hint = 3
        confidence = 0.94
        reason = "title_bullet_and_title_suffix"
    elif suffix_match and next_is_table and len(title) <= 45:
        marker_type = "context_heading"
        level_hint = 3
        confidence = 0.90
        reason = "short_title_followed_by_table"
    else:
        return None

    return {
        "marker": bullet,
        "marker_type": marker_type,
        "title": title,
        "full_text": original,
        "source_kind": "paragraph",
        "source": copy.deepcopy(paragraph.get("source", {})),
        "paragraph_index": paragraph.get("paragraph_index"),
        "confidence": confidence,
        "level_hint": level_hint,
        "detection_reason": reason,
    }


def paragraph_heading_candidate(
    paragraph: dict[str, Any],
    *,
    next_block: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    text = clean_text(paragraph.get("text"))

    parsed = parse_marker(text)
    if parsed:
        # 너무 긴 문장은 제목보다는 본문일 가능성이 높습니다.
        confidence = 0.95 if len(text) <= 120 and "\n" not in text else 0.65
        parsed.update({
            "source_kind": "paragraph",
            "source": copy.deepcopy(paragraph.get("source", {})),
            "paragraph_index": paragraph.get("paragraph_index"),
            "confidence": confidence,
            "detection_reason": "strong_number_marker",
        })
        return parsed

    return semantic_heading_candidate(
        paragraph,
        next_block=next_block,
    )


def is_layout_container(table: dict[str, Any]) -> bool:
    """본문 배치를 위해 사용된 외곽 표인지 보수적으로 판단합니다.

    LH 공고문은 문서 전체를 큰 표 하나에 넣고, 각 셀의 blocks 안에 실제 문단과
    중첩 데이터 표를 배치하는 경우가 있습니다. 이런 외곽 표를 그대로 데이터 표로
    취급하면 제목을 전혀 찾지 못하므로 셀의 blocks를 문서 흐름으로 펼칩니다.
    """

    if table.get("type") != "table":
        return False

    cells = [
        cell
        for cell in table.get("cells", [])
        if isinstance(cell, dict)
    ]
    nonempty_cells = [
        cell
        for cell in cells
        if cell.get("blocks")
    ]

    # 기존 규칙: 한 개의 실질 셀 안에 중첩 표와 여러 블록이 들어 있는 외형 상자.
    if len(nonempty_cells) == 1:
        inner = nonempty_cells[0].get("blocks", [])
        has_nested_table = any(
            isinstance(block, dict) and block.get("type") == "table"
            for block in inner
        )
        if has_nested_table and len(inner) >= 3:
            return True

    row_count = int(table.get("row_count") or 0)
    col_count = int(table.get("col_count") or 0)
    block_count = sum(
        len(cell.get("blocks") or [])
        for cell in nonempty_cells
    )

    has_split_major_heading = False
    for cell in nonempty_cells:
        cell_text = clean_text(cell.get("text"))
        if parse_standalone_marker(cell_text):
            has_split_major_heading = True
            break

    wide_cell_count = sum(
        1
        for cell in cells
        if int(cell.get("col_span") or 1) >= max(1, col_count)
    )

    # 문서 전체 외곽 표의 전형적 특징:
    # - 행이 많고 실제 block 수가 충분함
    # - 로마 숫자 등 단독 제목 표식이 별도 셀에 존재하거나
    # - 전체 열을 합친 넓은 셀이 반복됨
    return (
        row_count >= 8
        and block_count >= 10
        and (
            has_split_major_heading
            or wide_cell_count >= 3
        )
    )


def flatten_layout_table(
    table: dict[str, Any],
    block_path: list[str],
) -> list[dict[str, Any]]:
    """외곽 표의 셀 blocks를 논리 좌표 순서대로 펼칩니다."""

    items: list[dict[str, Any]] = []
    cells = sorted(
        (
            cell
            for cell in table.get("cells", [])
            if isinstance(cell, dict)
        ),
        key=lambda cell: (
            int(cell.get("row") or 0),
            int(cell.get("col") or 0),
        ),
    )

    for cell in cells:
        cell_blocks = cell.get("blocks") or []
        if not cell_blocks:
            continue

        row = int(cell.get("row") or 0)
        col = int(cell.get("col") or 0)
        cell_path = [
            *block_path,
            f"cell:{row},{col}",
        ]
        items.extend(
            flatten_blocks(
                cell_blocks,
                cell_path,
            )
        )

    return items


def compact_content(block: dict[str, Any]) -> dict[str, Any]:
    """원본 내용과 출처를 유지하되 deepcopy로 독립시킨다."""
    return copy.deepcopy(block)


def flatten_blocks(blocks: Iterable[dict[str, Any]], path: list[str] | None = None) -> list[dict[str, Any]]:
    """문단·표·중첩 표를 문서 순서대로 1차원 items로 펼친다."""
    path = path or []
    items: list[dict[str, Any]] = []

    block_list = list(blocks)

    for index, block in enumerate(block_list):
        block_path = path + [f"block:{index}"]
        block_type = block.get("type")
        next_block = (
            block_list[index + 1]
            if index + 1 < len(block_list)
            else None
        )

        if block_type == "table":
            candidate = table_heading_candidate(block)
            if candidate:
                items.append({
                    "type": "heading_candidate",
                    **candidate,
                    "level": None,
                    "resolved": False,
                    "origin_path": block_path,
                })
                continue

            if is_layout_container(block):
                items.extend(
                    flatten_layout_table(
                        block,
                        block_path,
                    )
                )
                continue

            items.append({
                "type": "table",
                "table_index": block.get("table_index"),
                "row_count": block.get("row_count"),
                "col_count": block.get("col_count"),
                "data": compact_content(block),
                "origin_path": block_path,
            })
            continue

        if block_type == "paragraph":
            candidate = paragraph_heading_candidate(
                block,
                next_block=next_block,
            )
            if candidate and candidate["confidence"] >= 0.8:
                items.append({
                    "type": "heading_candidate",
                    **candidate,
                    "level": None,
                    "resolved": False,
                    "origin_path": block_path,
                })
            else:
                items.append({
                    "type": "paragraph",
                    "text": clean_text(block.get("text")),
                    "data": compact_content(block),
                    "heading_candidate": bool(candidate),
                    "origin_path": block_path,
                })
            continue

        items.append({
            "type": block_type or "unknown",
            "data": compact_content(block),
            "origin_path": block_path,
        })

    return items


def merge_split_heading_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """별도 셀에 나뉜 제목 표식과 제목 문단을 하나의 후보로 합칩니다.

    예:
        셀 1: "Ⅰ"
        셀 2: "공급규모·공급대상 및 공급가격 등"
    """

    merged: list[dict[str, Any]] = []
    index = 0

    while index < len(items):
        current = items[index]

        if current.get("type") == "paragraph":
            standalone = parse_standalone_marker(
                current.get("text", "")
            )

            if standalone and index + 1 < len(items):
                following = items[index + 1]
                following_type = following.get("type")

                if following_type in {"paragraph", "heading_candidate"}:
                    title = clean_text(
                        following.get("title")
                        or following.get("text")
                        or following.get("full_text")
                    )

                    if title and not _looks_like_sentence(title):
                        merged.append({
                            "type": "heading_candidate",
                            "marker": standalone["marker"],
                            "marker_type": standalone["marker_type"],
                            "title": title,
                            "full_text": clean_text(
                                f"{standalone['marker']} {title}"
                            ),
                            "source_kind": "split_table_cells",
                            "source": copy.deepcopy(
                                following.get("source")
                                or following.get("data", {}).get("source")
                                or {}
                            ),
                            "paragraph_index": following.get(
                                "paragraph_index"
                            ),
                            "confidence": 0.99,
                            "detection_reason": (
                                "standalone_marker_followed_by_title"
                            ),
                            "level": None,
                            "resolved": False,
                            "origin_path": [
                                *(current.get("origin_path") or []),
                                "merged_with_next_cell",
                            ],
                            "merged_sources": [
                                copy.deepcopy(current),
                                copy.deepcopy(following),
                            ],
                        })
                        index += 2
                        continue

        merged.append(current)
        index += 1

    return merged


def marker_number(item: dict[str, Any]) -> int | None:
    marker_type = item.get("marker_type")
    marker = item.get("marker", "")
    if marker_type in {"arabic_dot", "arabic_paren", "arabic_rparen"} and marker.isdigit():
        return int(marker)
    if marker_type == "decimal":
        try:
            return int(marker.split(".")[-1])
        except ValueError:
            return None
    if marker_type == "roman" and marker in ROMAN:
        return ROMAN.index(marker) + 1
    if marker_type == "korean_dot" and marker:
        return ord(marker[0]) - ord("가") + 1
    return None


def infer_heading_scheme(items: list[dict[str, Any]]) -> dict[str, Any]:
    """문서 안의 반복·중첩 패턴으로 marker_type별 level을 추론한다.

    완벽한 일반 추론 대신 다음 보수적 근거를 사용한다.
    - 사용된 표식 종류의 출현 횟수
    - 서로 다른 표식이 교차해 등장하는 순서
    - 하위 후보 번호가 상위 후보 사이에서 다시 1로 시작하는지
    - decimal(1.1)은 arabic(1.)보다 하위라는 명시적 구조
    """
    headings = [item for item in items if item.get("type") == "heading_candidate"]
    types = [h["marker_type"] for h in headings]
    counts = Counter(types)
    positions: dict[str, list[int]] = defaultdict(list)
    for idx, h in enumerate(headings):
        positions[h["marker_type"]].append(idx)

    edges: Counter[tuple[str, str]] = Counter()
    evidence: list[dict[str, Any]] = []

    # 명시적으로 깊이가 드러나는 표식.
    if counts["decimal"] and counts["arabic_dot"]:
        edges[("arabic_dot", "decimal")] += 5
        evidence.append({"parent": "arabic_dot", "child": "decimal", "reason": "1. / 1.1 번호 구조"})

    # A 표식 두 개 사이에 B 표식이 있고 B가 1부터 다시 시작하면 A > B.
    unique_types = list(counts)
    for parent in unique_types:
        parent_pos = positions[parent]
        if len(parent_pos) < 2:
            continue
        for child in unique_types:
            if child == parent:
                continue
            restart_hits = 0
            contained_hits = 0
            for left, right in zip(parent_pos, parent_pos[1:]):
                between = headings[left + 1:right]
                child_items = [h for h in between if h["marker_type"] == child]
                if child_items:
                    contained_hits += 1
                    if marker_number(child_items[0]) == 1:
                        restart_hits += 1
            if restart_hits:
                weight = restart_hits * 4 + contained_hits
                edges[(parent, child)] += weight
                evidence.append({
                    "parent": parent,
                    "child": child,
                    "reason": f"상위 후보 사이에서 하위 번호가 1부터 재시작 {restart_hits}회",
                    "weight": weight,
                })

    # 첫 등장 순서가 명확하고 긴 범위를 감싸는 형식을 약한 상위 근거로 사용.
    for a, b in zip(headings, headings[1:]):
        if a["marker_type"] != b["marker_type"]:
            edges[(a["marker_type"], b["marker_type"])] += 0.2

    # 최대 가중치 부모 관계만 선택하고 순환은 피한다.
    parent_of: dict[str, str] = {}
    for child in unique_types:
        candidates = [(weight, parent) for (parent, c), weight in edges.items() if c == child and parent != child]
        if candidates:
            weight, parent = max(candidates)
            if weight >= 2:
                parent_of[child] = parent

    def depth(marker_type: str, visiting: set[str] | None = None) -> int:
        visiting = visiting or set()
        if marker_type in visiting:
            return 1
        parent = parent_of.get(marker_type)
        if not parent:
            return 1
        return depth(parent, visiting | {marker_type}) + 1

    levels = {marker_type: depth(marker_type) for marker_type in unique_types}

    # 상하관계가 전혀 추론되지 않은 단일 표식은 level 1로 둔다.
    # 여러 표식이 있지만 연결 근거가 약한 유형은 미확정(None)으로 둔다.
    connected = set(parent_of) | set(parent_of.values())
    if len(unique_types) > 1:
        for marker_type in unique_types:
            if marker_type not in connected:
                levels[marker_type] = None

    scheme: dict[str, Any] = {}
    for marker_type in unique_types:
        hinted_levels = [
            int(item["level_hint"])
            for item in headings
            if (
                item.get("marker_type") == marker_type
                and item.get("level_hint") is not None
            )
        ]

        if hinted_levels:
            level = Counter(hinted_levels).most_common(1)[0][0]
            confidence = 0.95
            level_source = "explicit_semantic_rule"
        else:
            level = levels.get(marker_type)
            confidence = (
                0.95
                if marker_type in connected
                else (0.8 if len(unique_types) == 1 else 0.45)
            )
            level_source = "document_marker_inference"

        scheme[marker_type] = {
            "level": level,
            "count": counts[marker_type],
            "confidence": confidence,
            "level_source": level_source,
        }

    return {
        "scheme": scheme,
        "evidence": evidence,
        "heading_count": len(headings),
    }


def assign_levels(items: list[dict[str, Any]], inference: dict[str, Any]) -> None:
    """문서 추론 결과와 안전한 표식 기본값으로 제목 레벨을 부여합니다."""

    scheme = inference["scheme"]
    canonical_levels = {
        "chapter": 1,
        "roman": 1,
        "arabic_dot": 2,
        "arabic_paren": 2,
        "arabic_rparen": 3,
        "decimal": 3,
        "circled": 3,
        "korean_dot": 3,
    }

    for item in items:
        if item.get("type") != "heading_candidate":
            continue

        marker_type = item.get("marker_type")
        rule = scheme.get(marker_type, {})

        if item.get("level_hint") is not None:
            level = int(item["level_hint"])
            level_confidence = float(item.get("confidence", 0.0))
            level_source = "item_level_hint"
        elif marker_type in canonical_levels:
            level = canonical_levels[marker_type]
            level_confidence = max(
                0.95,
                float(rule.get("confidence", 0.0)),
            )
            level_source = "canonical_marker_level"
        else:
            level = rule.get("level")
            level_confidence = float(rule.get("confidence", 0.0))
            level_source = "document_marker_inference"

        item["level"] = level
        item["resolved"] = (
            level is not None
            and item.get("confidence", 0) >= 0.8
        )
        item["level_confidence"] = level_confidence
        item["level_source"] = level_source


def make_section(item: dict[str, Any], section_id: str) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "level": item["level"],
        "marker": item.get("marker"),
        "marker_type": item.get("marker_type"),
        "title": item.get("title"),
        "heading_detection": {
            "confidence": item.get("confidence"),
            "reason": item.get("detection_reason"),
            "full_text": item.get("full_text"),
        },
        "contents": [],
        "children": [],
        "source": {
            "source_kind": item.get("source_kind"),
            "table_index": item.get("source_table_index"),
            "paragraph_index": item.get("paragraph_index"),
            "origin_path": item.get("origin_path"),
            **copy.deepcopy(item.get("source", {})),
        },
    }


def content_from_item(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("type") == "paragraph":
        result = copy.deepcopy(item.get("data", {}))
        result["type"] = "paragraph"
        result["text"] = item.get("text", "")
        if item.get("heading_candidate"):
            result["heading_candidate"] = True
        result["origin_path"] = item.get("origin_path")
        return result
    if item.get("type") == "table":
        result = copy.deepcopy(item.get("data", {}))
        result["origin_path"] = item.get("origin_path")
        return result
    return copy.deepcopy(item)


def build_hierarchy(document: dict[str, Any], items: list[dict[str, Any]], inference: dict[str, Any]) -> dict[str, Any]:
    intro: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    unresolved_items: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    section_counter = 0

    for item in items:
        if item.get("type") == "heading_candidate" and item.get("resolved"):
            section_counter += 1
            node = make_section(item, f"sec_{section_counter:04d}")
            level = int(item["level"])

            while stack and int(stack[-1]["level"]) >= level:
                stack.pop()

            if stack:
                stack[-1]["children"].append(node)
            else:
                sections.append(node)
            stack.append(node)
            continue

        if item.get("type") == "heading_candidate":
            # 미확정 후보는 원래 위치에 일반 내용으로 보존하고 별도 기록한다.
            unresolved = copy.deepcopy(item)
            unresolved["reason"] = "문서 내 제목 계층을 확정할 근거가 부족함"
            unresolved_items.append(unresolved)
            content = {
                "type": "unresolved_heading",
                "text": item.get("full_text", ""),
                "heading_candidate": True,
                "marker": item.get("marker"),
                "marker_type": item.get("marker_type"),
                "source": copy.deepcopy(item.get("source", {})),
                "origin_path": item.get("origin_path"),
            }
        else:
            content = content_from_item(item)

        if stack:
            stack[-1]["contents"].append(content)
        else:
            intro.append(content)

    return {
        "document": copy.deepcopy(document),
        "hierarchy_method": {
            "version": "step1-v2-auto-title",
            "stages": [
                "1-1 ordered_items_and_heading_candidates",
                "1-2 document_specific_heading_scheme",
                "1-3 hierarchy_building",
            ],
            "heading_scheme": copy.deepcopy(inference),
        },
        "intro": intro,
        "sections": sections,
        "unresolved_items": unresolved_items,
    }


def process(input_path: str, output_dir: str) -> tuple[str, str, str]:
    with open(input_path, "r", encoding="utf-8") as f:
        source = json.load(f)

    all_blocks: list[dict[str, Any]] = []
    for section in source.get("sections", []):
        all_blocks.extend(section.get("blocks", []))

    items = flatten_blocks(all_blocks)
    items = merge_split_heading_items(items)

    for idx, item in enumerate(items, start=1):
        item["item_id"] = f"item_{idx:04d}"
        item["order"] = idx

    inference = infer_heading_scheme(items)
    assign_levels(items, inference)
    hierarchy = build_hierarchy(source.get("document", {}), items, inference)

    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    p11 = os.path.join(output_dir, f"{stem}_step1-1_items.json")
    p12 = os.path.join(output_dir, f"{stem}_step1-2_heading_scheme.json")
    p13 = os.path.join(output_dir, f"{stem}_step1-3_hierarchy.json")

    with open(p11, "w", encoding="utf-8") as f:
        json.dump({"document": source.get("document", {}), "items": items}, f, ensure_ascii=False, indent=2)
    with open(p12, "w", encoding="utf-8") as f:
        json.dump({"document": source.get("document", {}), **inference}, f, ensure_ascii=False, indent=2)
    with open(p13, "w", encoding="utf-8") as f:
        json.dump(hierarchy, f, ensure_ascii=False, indent=2)

    return p11, p12, p13


def select_input_json() -> str | None:
    """파일 선택 창을 열어 정규화 JSON 경로를 반환한다."""
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    selected = askopenfilename(
        parent=root,
        title="정규화 JSON 파일 선택",
        filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
    )

    root.destroy()
    return selected or None


def main() -> None:
    input_path = select_input_json()
    if not input_path:
        print("JSON 파일을 선택하지 않아 실행을 종료합니다.")
        return

    # 이 Python 파일이 있는 structure 폴더를 기준으로 output 폴더를 사용한다.
    structure_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(structure_dir, "output")

    try:
        outputs = process(input_path, output_dir)
    except FileNotFoundError:
        messagebox.showerror("실행 오류", f"입력 파일을 찾을 수 없습니다.\n{input_path}")
        return
    except json.JSONDecodeError as exc:
        messagebox.showerror("실행 오류", f"올바른 JSON 파일이 아닙니다.\n{exc}")
        return
    except (KeyError, TypeError, ValueError) as exc:
        messagebox.showerror("실행 오류", f"예상한 공통 JSON 구조와 다릅니다.\n{exc}")
        return
    except OSError as exc:
        messagebox.showerror("실행 오류", f"파일을 읽거나 저장하는 중 오류가 발생했습니다.\n{exc}")
        return

    print("입력 파일:", input_path)
    print("출력 폴더:", output_dir)
    for path in outputs:
        print("생성 파일:", path)

    messagebox.showinfo(
        "구조화 완료",
        "1단계 문서 계층 구조화가 완료되었습니다.\n\n"
        f"저장 폴더:\n{output_dir}",
    )


if __name__ == "__main__":
    main()