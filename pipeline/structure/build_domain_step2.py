#!/usr/bin/env python3
"""규칙 기반 도메인 태깅 및 계층 보정 2단계.

입력:
- *_step1-3_hierarchy.json

출력:
1. *_step2-1_normalized_titles.json
   - 제목 정규화 결과

2. *_step2-2_domain_matches.json
   - 도메인 매칭 결과

3. *_step2-3_domain_tagged.json
   - 도메인 태그를 추가한 원본 계층 결과
   - 아직 계층 재배치는 수행하지 않음

4. *_step2-4_hierarchy_conflicts.json
   - 부모/자식 도메인과 다음 Level 1을 비교한
     계층 오류 후보

5. *_step2-5_domain_repaired.json
   - 안전 조건을 만족하는 경우에 한해
     연속된 Section 묶음을 다음 Level 1 아래로 재배치한 결과

재배치 원칙:
- domain 하나만 보고 무조건 이동하지 않는다.
- 다음 Level 1이 비어 있어야 한다.
- 현재 부모의 자식 중 최소 2개 이상이
  '현재 부모와 domain 불일치 + 다음 부모와 domain 일치'
  조건을 만족해야 한다.
- 충돌 Section들이 현재 부모 children의 연속된 마지막 구간이어야 한다.
- 같은 원본 컨테이너(origin_path)에 속한 바로 앞 Section까지
  하나의 연속 묶음으로 판단한다.
- 원본 내용, source, section_id는 변경하지 않는다.
- 애매한 경우 자동 이동하지 않고 원래 계층을 유지한다.
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from tkinter import Tk, messagebox
from tkinter.filedialog import askopenfilename


# ===========================================================================
# 도메인 규칙 로딩
# ===========================================================================

DEFAULT_RULES_PATH = Path(__file__).with_name("domain_rules.json")


def load_domain_config(path: str | Path | None = None) -> dict[str, Any]:
    """코드와 분리된 도메인 규칙 파일을 읽고 최소 스키마를 검증한다."""

    target = Path(path).expanduser().resolve() if path else DEFAULT_RULES_PATH
    if not target.is_file():
        raise FileNotFoundError(f"도메인 규칙 파일을 찾을 수 없습니다: {target}")

    try:
        with target.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 도메인 규칙 JSON입니다: {target} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(config, dict):
        raise ValueError("도메인 규칙 JSON 최상위 값은 객체여야 합니다.")
    if not isinstance(config.get("rules"), list) or not config["rules"]:
        raise ValueError("도메인 규칙 JSON에 rules 배열이 필요합니다.")
    if not isinstance(config.get("weights"), dict):
        raise ValueError("도메인 규칙 JSON에 weights 객체가 필요합니다.")

    required = {"category", "topic", "title_keywords", "threshold"}
    seen_topics: set[str] = set()
    for index, rule in enumerate(config["rules"]):
        if not isinstance(rule, dict) or not required.issubset(rule):
            raise ValueError(f"rules[{index}]의 필수 필드가 부족합니다: {required}")
        topic = str(rule["topic"])
        if topic in seen_topics:
            raise ValueError(f"중복된 topic 규칙입니다: {topic}")
        seen_topics.add(topic)

    return config


# ===========================================================================
# 2-1 제목 정규화
# ===========================================================================

def normalize_title(title: Any) -> str:
    """도메인 매칭용 제목 문자열을 생성한다."""

    text = "" if title is None else str(title)

    text = (
        text.replace("\n", " ")
        .replace("\r", " ")
    )

    patterns = [
        r"^\s*제\s*\d+\s*[장절편부]\s*",
        r"^\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+[.．]?\s*",
        r"^\s*\d+(?:\.\d+)+[.)]?\s*",
        r"^\s*\d+[.．)]\s*",
        r"^\s*\(\d+\)\s*",
        r"^\s*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*",
        r"^\s*[가-하][.．)]\s*",
    ]

    for pattern in patterns:
        new_text = re.sub(
            pattern,
            "",
            text,
        )

        if new_text != text:
            text = new_text
            break

    # 괄호 문자는 제거하고 내부 텍스트는 유지
    text = re.sub(
        r"[\[\]{}()<>〈〉《》「」『』【】]",
        " ",
        text,
    )

    text = (
        text.replace("․", " ")
        .replace("·", " ")
        .replace("ㆍ", " ")
    )

    text = re.sub(
        r"[,:;|/\\]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def compact_text(text: str) -> str:
    """키워드 비교용 문자열."""

    return re.sub(
        r"[^0-9A-Za-z가-힣]",
        "",
        text,
    ).lower()


def walk_sections(
    sections: list[dict[str, Any]],
    path: list[str] | None = None,
) -> Iterator[
    tuple[
        dict[str, Any],
        list[str],
    ]
]:
    """모든 Section을 계층 순서대로 순회."""

    path = path or []

    for section in sections:
        title = str(
            section.get("title") or ""
        )

        current_path = path + [title]

        yield section, current_path

        children = section.get("children") or []

        if isinstance(children, list):
            yield from walk_sections(
                children,
                current_path,
            )


# ===========================================================================
# 2-2 도메인 매핑
# ===========================================================================

def _clean_source_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _iter_texts(value: Any) -> Iterator[str]:
    """Section contents에서 문단과 셀 텍스트를 보수적으로 수집한다."""

    if isinstance(value, list):
        for child in value:
            yield from _iter_texts(child)
        return
    if not isinstance(value, dict):
        return

    node_type = value.get("type")
    if node_type in {"paragraph", "text"}:
        text = _clean_source_text(value.get("text"))
        if text:
            yield text
        return
    if node_type == "table":
        # 표 전체 값은 과분류 위험이 있어 표 헤더 수집 함수에서만 사용한다.
        return

    for key, child in value.items():
        if key in {"source", "domain", "structured_table"}:
            continue
        if isinstance(child, (dict, list)):
            yield from _iter_texts(child)


def _table_header_texts(value: Any) -> Iterator[str]:
    if isinstance(value, list):
        for child in value:
            yield from _table_header_texts(child)
        return
    if not isinstance(value, dict):
        return

    if value.get("type") == "table":
        cells = [cell for cell in value.get("cells") or [] if isinstance(cell, dict)]
        if cells:
            min_row = min(int(cell.get("row", 0) or 0) for cell in cells)
            for cell in cells:
                if int(cell.get("row", 0) or 0) == min_row:
                    header = _clean_source_text(cell.get("text"))
                    if header:
                        yield header
        for cell in cells:
            yield from _table_header_texts(cell.get("blocks") or [])
        return

    for key, child in value.items():
        if key in {"source", "domain", "structured_table"}:
            continue
        if isinstance(child, (dict, list)):
            yield from _table_header_texts(child)


def build_classification_sources(
    section: dict[str, Any],
    section_path: list[str],
    *,
    max_content_chars: int,
) -> dict[str, Any]:
    title = normalize_title(section.get("title"))
    parent_title = normalize_title(section_path[-2]) if len(section_path) >= 2 else ""

    content_parts: list[str] = []
    used = 0
    for part in _iter_texts(section.get("contents") or []):
        if used >= max_content_chars:
            break
        remaining = max_content_chars - used
        clipped = part[:remaining]
        if clipped:
            content_parts.append(clipped)
            used += len(clipped)

    headers = list(dict.fromkeys(_table_header_texts(section.get("contents") or [])))
    content = " ".join(content_parts)
    table_headers = " ".join(headers)
    classification_text = _clean_source_text(
        " ".join(value for value in (parent_title, title, table_headers, content) if value)
    )

    return {
        "title": title,
        "parent_title": parent_title,
        "table_headers": table_headers,
        "content": content,
        "classification_text": classification_text,
    }


def _keyword_hits(text: str, keywords: list[Any]) -> list[str]:
    compact = compact_text(text)
    hits: list[str] = []
    for keyword in keywords or []:
        original = str(keyword).strip()
        normalized = compact_text(original)
        if normalized and normalized in compact:
            hits.append(original)
    return list(dict.fromkeys(hits))


def score_domain_rule(
    sources: dict[str, Any],
    rule: dict[str, Any],
    weights: dict[str, Any],
) -> dict[str, Any] | None:
    matched: list[dict[str, Any]] = []
    score = 0

    source_specs = (
        ("title", rule.get("title_keywords") or [], int(weights.get("title", 5))),
        ("parent_title", rule.get("title_keywords") or [], int(weights.get("parent_title", 1))),
        ("table_header", [*(rule.get("title_keywords") or []), *(rule.get("content_keywords") or [])], int(weights.get("table_header", 3))),
        ("content", rule.get("content_keywords") or rule.get("title_keywords") or [], int(weights.get("content", 1))),
    )

    for source_name, keywords, weight in source_specs:
        source_key = "table_headers" if source_name == "table_header" else source_name
        hits = _keyword_hits(str(sources.get(source_key) or ""), list(keywords))
        if not hits:
            continue
        # 같은 위치에서 동의어가 여러 개 겹쳐도 한 번만 가중한다.
        score += weight
        matched.extend({"keyword": hit, "source": source_name, "weight": weight} for hit in hits)

    title_compact = compact_text(str(sources.get("title") or ""))
    for keyword in rule.get("title_keywords") or []:
        if title_compact and title_compact == compact_text(str(keyword)):
            bonus = int(weights.get("exact_title_bonus", 2))
            score += bonus
            matched.append({"keyword": str(keyword), "source": "exact_title", "weight": bonus})
            break

    negative_hits = _keyword_hits(
        str(sources.get("classification_text") or ""),
        list(rule.get("negative_keywords") or []),
    )
    if negative_hits:
        negative_weight = int(weights.get("negative", -3))
        score += negative_weight
        matched.extend({"keyword": hit, "source": "negative", "weight": negative_weight} for hit in negative_hits)

    threshold = int(rule.get("threshold", 5))
    if score < threshold:
        return None

    confidence = min(0.99, round(score / max(threshold + 3, 1), 4))
    return {
        "category": str(rule["category"]),
        "topic": str(rule["topic"]),
        "method": "rule_score",
        "score": score,
        "threshold": threshold,
        "confidence": confidence,
        "priority": int(rule.get("priority", 0)),
        "matched_keyword": matched[0]["keyword"] if matched else None,
        "matched_keywords": matched,
        "match_type": "scored_rule",
    }


def score_composite_rule(
    sources: dict[str, Any],
    rule: dict[str, Any],
    weights: dict[str, Any],
) -> dict[str, Any] | None:
    title = str(sources.get("title") or "")
    required = [str(value) for value in rule.get("required_keywords") or []]
    if not required or not all(compact_text(value) in compact_text(title) for value in required):
        return None

    score = int(rule.get("threshold", 6)) + int(weights.get("composite_bonus", 3))
    threshold = int(rule.get("threshold", 6))
    return {
        "category": str(rule["category"]),
        "topic": str(rule["topic"]),
        "method": "composite_rule",
        "score": score,
        "threshold": threshold,
        "confidence": min(0.99, round(score / max(threshold + 3, 1), 4)),
        "priority": 10_000,
        "matched_keyword": str(rule.get("matched_keyword") or "+".join(required)),
        "matched_keywords": [
            {"keyword": keyword, "source": "title", "weight": int(weights.get("title", 5))}
            for keyword in required
        ],
        "match_type": "composite",
    }


def match_domain(
    sources: dict[str, Any] | str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """제목·부모 제목·표 헤더·대표 본문을 이용한 점수 기반 1차 분류."""

    config = config or load_domain_config()
    if isinstance(sources, str):
        sources = {
            "title": sources,
            "parent_title": "",
            "table_headers": "",
            "content": "",
            "classification_text": sources,
        }

    weights = config["weights"]
    candidates: list[dict[str, Any]] = []

    for rule in config.get("composite_rules") or []:
        candidate = score_composite_rule(sources, rule, weights)
        if candidate:
            candidates.append(candidate)

    for rule in config["rules"]:
        candidate = score_domain_rule(sources, rule, weights)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(
        key=lambda value: (
            int(value.get("score", 0)),
            int(value.get("priority", 0)),
            len(str(value.get("matched_keyword") or "")),
        ),
        reverse=True,
    )
    selected = candidates[0]
    selected["candidate_count"] = len(candidates)
    selected.pop("priority", None)
    return selected


# ===========================================================================
# 공통 보조 함수
# ===========================================================================

def get_domain_category(
    section: dict[str, Any],
) -> str | None:
    """Section의 domain category 반환."""

    domain = section.get("domain")

    if not isinstance(
        domain,
        dict,
    ):
        return None

    category = domain.get("category")

    if not category:
        return None

    return str(category)


def get_origin_path(
    section: dict[str, Any],
) -> list[str]:
    """Section 제목의 원본 origin_path 반환."""

    source = section.get("source")

    if not isinstance(
        source,
        dict,
    ):
        return []

    origin_path = source.get(
        "origin_path"
    )

    if not isinstance(
        origin_path,
        list,
    ):
        return []

    return [
        str(value)
        for value in origin_path
    ]


def get_container_key(
    section: dict[str, Any],
) -> tuple[str, ...] | None:
    """같은 원본 레이아웃 컨테이너 여부를 판단할 key.

    예:
    [
        "block:7",
        "cell:0,0",
        "block:12"
    ]

    이 경우 마지막 block 번호는 컨테이너 내부 위치이므로 제거하고

    (
        "block:7",
        "cell:0,0"
    )

    를 같은 컨테이너 key로 사용한다.
    """

    origin_path = get_origin_path(
        section
    )

    if len(origin_path) < 2:
        return None

    return tuple(
        origin_path[:-1]
    )


def is_empty_section(
    section: dict[str, Any],
) -> bool:
    """Section 자체에 내용이나 자식이 없는지 검사."""

    contents = (
        section.get("contents")
        or []
    )

    children = (
        section.get("children")
        or []
    )

    return (
        len(contents) == 0
        and len(children) == 0
    )


# ===========================================================================
# 2-4 계층 충돌 검사
# ===========================================================================

def detect_hierarchy_conflicts(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Level 1 간 계층 충돌 후보 탐지.

    조건:
    - child domain != current parent domain
    - child domain == next Level 1 domain

    자동 이동은 하지 않는다.
    """

    conflicts: list[
        dict[str, Any]
    ] = []

    if len(sections) < 2:
        return conflicts

    for parent_index in range(
        len(sections) - 1
    ):
        current_parent = (
            sections[parent_index]
        )

        next_parent = (
            sections[
                parent_index + 1
            ]
        )

        current_category = (
            get_domain_category(
                current_parent
            )
        )

        next_category = (
            get_domain_category(
                next_parent
            )
        )

        if (
            current_category is None
            or next_category is None
        ):
            continue

        children = (
            current_parent.get(
                "children"
            )
            or []
        )

        if not isinstance(
            children,
            list,
        ):
            continue

        for (
            child_index,
            child,
        ) in enumerate(children):
            if not isinstance(
                child,
                dict,
            ):
                continue

            child_category = (
                get_domain_category(
                    child
                )
            )

            if child_category is None:
                continue

            if (
                child_category
                != current_category
                and child_category
                == next_category
            ):
                conflicts.append(
                    {
                        "type": (
                            "possible_wrong_parent"
                        ),
                        "severity": (
                            "warning"
                        ),
                        "parent_index": (
                            parent_index
                        ),
                        "child_index": (
                            child_index
                        ),
                        "child_section_id": (
                            child.get(
                                "section_id"
                            )
                        ),
                        "child_title": (
                            child.get(
                                "title"
                            )
                        ),
                        "child_domain": (
                            copy.deepcopy(
                                child.get(
                                    "domain"
                                )
                            )
                        ),
                        "child_origin_path": (
                            get_origin_path(
                                child
                            )
                        ),
                        "current_parent": {
                            "section_id": (
                                current_parent.get(
                                    "section_id"
                                )
                            ),
                            "title": (
                                current_parent.get(
                                    "title"
                                )
                            ),
                            "domain": (
                                copy.deepcopy(
                                    current_parent.get(
                                        "domain"
                                    )
                                )
                            ),
                        },
                        "suggested_parent": {
                            "section_id": (
                                next_parent.get(
                                    "section_id"
                                )
                            ),
                            "title": (
                                next_parent.get(
                                    "title"
                                )
                            ),
                            "domain": (
                                copy.deepcopy(
                                    next_parent.get(
                                        "domain"
                                    )
                                )
                            ),
                            "empty_before_repair": (
                                is_empty_section(
                                    next_parent
                                )
                            ),
                        },
                        "reason": (
                            "자식 Section의 domain "
                            "category가 현재 부모와 "
                            "다르고 바로 다음 Level 1 "
                            "Section의 category와 일치함"
                        ),
                        "action": (
                            "2-4에서는 자동 이동하지 않음. "
                            "2-5 안전 재배치 조건을 추가로 "
                            "검사함."
                        ),
                    }
                )

    return conflicts


def build_hierarchy_conflict_result(
    tagged: dict[str, Any],
) -> dict[str, Any]:
    """2-4 결과 JSON."""

    sections = tagged.get(
        "sections"
    )

    if not isinstance(
        sections,
        list,
    ):
        raise ValueError(
            "도메인 태깅 결과에 "
            "sections 배열이 없습니다."
        )

    conflicts = (
        detect_hierarchy_conflicts(
            sections
        )
    )

    return {
        "document": copy.deepcopy(
            tagged.get(
                "document",
                {},
            )
        ),
        "step": "2-4",
        "description": (
            "도메인 기반 부모-자식 "
            "계층 정합성 검사 결과"
        ),
        "policy": {
            "automatic_repair": False,
            "rule": (
                "child domain != "
                "current parent domain AND "
                "child domain == "
                "next top-level section domain"
            ),
            "note": (
                "2-4 결과는 오류 후보이며, "
                "2-5 단계에서 추가 안전 조건을 "
                "통과한 경우에만 자동 재배치한다."
            ),
        },
        "summary": {
            "conflict_count": (
                len(conflicts)
            ),
        },
        "conflicts": conflicts,
    }


# ===========================================================================
# 2-5 안전한 연속 Section 묶음 재배치
# ===========================================================================

def group_conflicts_by_parent_pair(
    conflicts: list[dict[str, Any]],
) -> dict[
    tuple[str, str],
    list[dict[str, Any]],
]:
    """현재 부모/추천 부모 조합별 충돌 그룹."""

    grouped: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for conflict in conflicts:
        current_parent = (
            conflict.get(
                "current_parent"
            )
            or {}
        )

        suggested_parent = (
            conflict.get(
                "suggested_parent"
            )
            or {}
        )

        current_id = str(
            current_parent.get(
                "section_id"
            )
            or ""
        )

        suggested_id = str(
            suggested_parent.get(
                "section_id"
            )
            or ""
        )

        if (
            current_id
            and suggested_id
        ):
            grouped[
                (
                    current_id,
                    suggested_id,
                )
            ].append(
                conflict
            )

    return grouped


def repair_contiguous_section_groups(
    tagged: dict[str, Any],
    conflicts: list[dict[str, Any]],
    min_strong_conflicts: int = 2,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
]:
    """안전 조건을 만족하는 연속 Section 묶음 재배치.

    현재 익산평화 케이스 예:

    Ⅱ 신청자격 및 확인사항
    ├─ 일정 및 장소
    ├─ 동호지정 세부일정 및 유의사항   <- strong conflict
    └─ 계약 시 구비서류               <- strong conflict

    Ⅲ 서류제출, 동호지정 및 계약체결 등
    └─ 비어 있음

    세 자식이 동일한 원본 컨테이너에 있고,
    충돌 2개가 마지막 연속 구간에 존재하며,
    다음 Level 1이 비어 있다면:

    Ⅱ 신청자격 및 확인사항

    Ⅲ 서류제출, 동호지정 및 계약체결 등
    ├─ 일정 및 장소
    ├─ 동호지정 세부일정 및 유의사항
    └─ 계약 시 구비서류

    로 보정한다.

    애매한 경우에는 이동하지 않는다.
    """

    repaired = copy.deepcopy(
        tagged
    )

    sections = repaired.get(
        "sections"
    )

    if not isinstance(
        sections,
        list,
    ):
        raise ValueError(
            "2-5 재배치 대상에 "
            "sections 배열이 없습니다."
        )

    repairs: list[
        dict[str, Any]
    ] = []

    grouped = (
        group_conflicts_by_parent_pair(
            conflicts
        )
    )

    # 인접 Level 1 쌍만 검사
    for parent_index in range(
        len(sections) - 1
    ):
        current_parent = (
            sections[parent_index]
        )

        next_parent = (
            sections[
                parent_index + 1
            ]
        )

        current_id = str(
            current_parent.get(
                "section_id"
            )
            or ""
        )

        next_id = str(
            next_parent.get(
                "section_id"
            )
            or ""
        )

        pair_conflicts = (
            grouped.get(
                (
                    current_id,
                    next_id,
                ),
                [],
            )
        )

        # ---------------------------------------------------------------
        # 조건 1
        # 최소 2개 이상의 명확한 충돌이 있어야 함
        # ---------------------------------------------------------------

        if (
            len(pair_conflicts)
            < min_strong_conflicts
        ):
            continue

        # ---------------------------------------------------------------
        # 조건 2
        # 다음 Level 1이 완전히 비어 있어야 함
        # ---------------------------------------------------------------

        if not is_empty_section(
            next_parent
        ):
            continue

        children = (
            current_parent.get(
                "children"
            )
            or []
        )

        if not isinstance(
            children,
            list,
        ):
            continue

        if not children:
            continue

        conflict_indices = sorted(
            {
                int(
                    conflict[
                        "child_index"
                    ]
                )
                for conflict
                in pair_conflicts
                if isinstance(
                    conflict.get(
                        "child_index"
                    ),
                    int,
                )
            }
        )

        if (
            len(conflict_indices)
            < min_strong_conflicts
        ):
            continue

        # ---------------------------------------------------------------
        # 조건 3
        # 강한 충돌들이 children 마지막 구간까지 이어져야 함
        #
        # 예:
        # idx 1, 2
        # children 길이 3
        #
        # 마지막 충돌 idx == 2 == len(children)-1
        # ---------------------------------------------------------------

        last_conflict_index = (
            conflict_indices[-1]
        )

        if (
            last_conflict_index
            != len(children) - 1
        ):
            continue

        first_conflict_index = (
            conflict_indices[0]
        )

        first_conflict_child = (
            children[
                first_conflict_index
            ]
        )

        common_container = (
            get_container_key(
                first_conflict_child
            )
        )

        if common_container is None:
            continue

        # ---------------------------------------------------------------
        # 조건 4
        # 강한 충돌들이 동일 원본 컨테이너에 있어야 함
        # ---------------------------------------------------------------

        all_conflicts_same_container = (
            all(
                get_container_key(
                    children[index]
                )
                == common_container
                for index in conflict_indices
            )
        )

        if not all_conflicts_same_container:
            continue

        # ---------------------------------------------------------------
        # 같은 컨테이너에 속한 바로 앞 Section까지 확장
        #
        # 익산평화에서는
        #
        # idx 0 일정 및 장소
        # idx 1 동호지정...
        # idx 2 계약 시 구비서류
        #
        # 모두 같은 block:7 내부이므로
        # idx 0까지 이동 범위 확장
        # ---------------------------------------------------------------

        move_start_index = (
            first_conflict_index
        )

        while (
            move_start_index > 0
        ):
            previous_child = (
                children[
                    move_start_index - 1
                ]
            )

            previous_container = (
                get_container_key(
                    previous_child
                )
            )

            if (
                previous_container
                != common_container
            ):
                break

            move_start_index -= 1

        move_candidates = (
            children[
                move_start_index:
            ]
        )

        # ---------------------------------------------------------------
        # 조건 5
        # 이동될 마지막 연속 구간 전체가 같은 컨테이너인지 확인
        # ---------------------------------------------------------------

        if not all(
            get_container_key(child)
            == common_container
            for child in move_candidates
        ):
            continue

        # ---------------------------------------------------------------
        # 안전 조건 통과
        # 실제 이동
        # ---------------------------------------------------------------

        remaining_children = (
            children[
                :move_start_index
            ]
        )

        moved_children = (
            move_candidates
        )

        current_parent[
            "children"
        ] = remaining_children

        next_parent[
            "children"
        ] = (
            moved_children
            + (
                next_parent.get(
                    "children"
                )
                or []
            )
        )

        repairs.append(
            {
                "type": (
                    "contiguous_section_group_repair"
                ),
                "current_parent": {
                    "section_id": (
                        current_parent.get(
                            "section_id"
                        )
                    ),
                    "title": (
                        current_parent.get(
                            "title"
                        )
                    ),
                    "domain": (
                        copy.deepcopy(
                            current_parent.get(
                                "domain"
                            )
                        )
                    ),
                },
                "new_parent": {
                    "section_id": (
                        next_parent.get(
                            "section_id"
                        )
                    ),
                    "title": (
                        next_parent.get(
                            "title"
                        )
                    ),
                    "domain": (
                        copy.deepcopy(
                            next_parent.get(
                                "domain"
                            )
                        )
                    ),
                },
                "strong_conflict_count": (
                    len(pair_conflicts)
                ),
                "move_start_index": (
                    move_start_index
                ),
                "source_container": list(
                    common_container
                ),
                "moved_sections": [
                    {
                        "section_id": (
                            child.get(
                                "section_id"
                            )
                        ),
                        "title": (
                            child.get(
                                "title"
                            )
                        ),
                        "domain": (
                            copy.deepcopy(
                                child.get(
                                    "domain"
                                )
                            )
                        ),
                        "origin_path": (
                            get_origin_path(
                                child
                            )
                        ),
                    }
                    for child
                    in moved_children
                ],
                "reason": (
                    "다음 Level 1이 비어 있고, "
                    "현재 부모의 마지막 연속 자식 구간에서 "
                    "최소 2개의 강한 domain 충돌이 발견되었으며, "
                    "해당 자식들이 동일한 원본 컨테이너에 "
                    "속해 있어 하나의 Section 묶음으로 재배치함"
                ),
            }
        )

    # ---------------------------------------------------------------
    # 재배치 후 다시 충돌 검사
    # ---------------------------------------------------------------

    remaining_conflicts = (
        detect_hierarchy_conflicts(
            sections
        )
    )

    repaired[
        "hierarchy_repair"
    ] = {
        "step": "2-5",
        "automatic_repair": True,
        "strategy": (
            "contiguous_tail_group_with_"
            "multiple_domain_conflicts"
        ),
        "safety_conditions": [
            (
                "현재 부모와 다음 Level 1이 "
                "문서상 인접해야 함"
            ),
            (
                "다음 Level 1의 contents와 "
                "children이 모두 비어 있어야 함"
            ),
            (
                "최소 2개의 자식이 현재 부모와 "
                "domain이 다르고 다음 부모와 "
                "domain이 일치해야 함"
            ),
            (
                "충돌 자식이 현재 children의 "
                "마지막 연속 구간에 있어야 함"
            ),
            (
                "이동 자식들이 동일 원본 "
                "origin_path 컨테이너에 속해야 함"
            ),
        ],
        "repair_count": (
            len(repairs)
        ),
        "repairs": repairs,
        "remaining_conflict_count": (
            len(
                remaining_conflicts
            )
        ),
        "remaining_conflicts": (
            remaining_conflicts
        ),
    }

    return (
        repaired,
        repairs,
    )


# ===========================================================================
# Step 2 전체 처리
# ===========================================================================

def build_step2_results(
    source: dict[str, Any],
    *,
    domain_config: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """Step 2-1 ~ Step 2-5 결과 생성."""

    if not isinstance(source.get("sections"), list):
        raise ValueError("1단계 계층 JSON의 sections 배열을 찾을 수 없습니다.")

    config = domain_config or load_domain_config()
    low_confidence = float(config.get("low_confidence_threshold", 0.65))
    max_content_chars = int(config.get("max_content_chars", 1200))
    tagged = copy.deepcopy(source)

    title_records: list[dict[str, Any]] = []
    match_records: list[dict[str, Any]] = []
    unmatched_records: list[dict[str, Any]] = []

    original_sections = list(walk_sections(source["sections"]))
    tagged_sections = list(walk_sections(tagged["sections"]))
    if len(original_sections) != len(tagged_sections):
        raise ValueError("원본과 복사본의 Section 수가 일치하지 않습니다.")

    for (original_section, section_path), (tagged_section, _) in zip(
        original_sections, tagged_sections
    ):
        title = str(original_section.get("title") or "")
        sources = build_classification_sources(
            original_section,
            section_path,
            max_content_chars=max_content_chars,
        )
        normalized = sources["title"]
        domain = match_domain(sources, config)

        title_record = {
            "section_id": original_section.get("section_id"),
            "level": original_section.get("level"),
            "section_path": section_path,
            "original_title": title,
            "normalized_title": normalized,
            "classification_text": sources["classification_text"],
            "classification_sources": {
                "title": sources["title"],
                "parent_title": sources["parent_title"],
                "table_headers": sources["table_headers"],
                "content_preview": sources["content"],
            },
        }
        title_records.append(title_record)

        tagged_section["normalized_title"] = normalized
        tagged_section["classification_text"] = sources["classification_text"]
        tagged_section["classification_sources"] = copy.deepcopy(
            title_record["classification_sources"]
        )
        tagged_section["domain"] = None
        tagged_section["needs_semantic_classification"] = True

        if domain is not None:
            final_domain = {
                key: copy.deepcopy(value)
                for key, value in domain.items()
                if key != "match_type"
            }
            tagged_section["domain"] = final_domain
            tagged_section["needs_semantic_classification"] = (
                float(final_domain.get("confidence", 0.0)) < low_confidence
            )
            match_records.append({
                **title_record,
                "domain": copy.deepcopy(final_domain),
                "match_type": domain.get("match_type"),
                "needs_semantic_classification": tagged_section[
                    "needs_semantic_classification"
                ],
            })
        else:
            unmatched = {
                **title_record,
                "reason": "규칙 점수가 임계값에 도달하지 않음",
                "needs_semantic_classification": True,
            }
            unmatched_records.append(unmatched)

    step2_1 = {
        "document": copy.deepcopy(source.get("document", {})),
        "step": "2-1",
        "description": "계층 제목 정규화 및 의미 분류 입력 생성 결과",
        "titles": title_records,
    }
    step2_2 = {
        "document": copy.deepcopy(source.get("document", {})),
        "step": "2-2",
        "description": "외부 규칙 파일 기반 점수형 도메인 매칭 결과",
        "rules_schema_version": config.get("schema_version"),
        "summary": {
            "total_sections": len(title_records),
            "matched_sections": len(match_records),
            "unmatched_sections": len(unmatched_records),
            "semantic_fallback_sections": sum(
                bool(record.get("needs_semantic_classification"))
                for record in match_records
            ) + len(unmatched_records),
        },
        "matches": match_records,
        "unmatched": unmatched_records,
    }

    tagged["domain_tagging_method"] = {
        "step": "2-3",
        "target": "section_title_parent_content_table_headers",
        "method": "external_rule_score",
        "rules_file": DEFAULT_RULES_PATH.name,
        "rules_schema_version": config.get("schema_version"),
        "low_confidence_threshold": low_confidence,
        "semantic_fallback_policy": (
            "domain=null 또는 confidence가 기준 미만인 Section만 후속 임베딩 분류 대상"
        ),
        "version": "step2-v3-external-scored-rules",
    }
    tagged["domain_unresolved"] = unmatched_records

    step2_4 = build_hierarchy_conflict_result(tagged)
    tagged["hierarchy_validation"] = {
        "step": "2-4",
        "checked": True,
        "automatic_repair": False,
        "conflict_count": step2_4["summary"]["conflict_count"],
        "conflicts": copy.deepcopy(step2_4["conflicts"]),
    }

    repaired, _repairs = repair_contiguous_section_groups(
        tagged, step2_4["conflicts"], min_strong_conflicts=2
    )
    return step2_1, step2_2, tagged, step2_4, repaired


# ===========================================================================
# 파일 저장
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


def process(
    input_path: str,
    output_dir: str,
    rules_path: str | Path | None = None,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
]:
    """Step 2 실행 및 저장."""

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Step 1 JSON 파일을 찾을 수 없습니다: {input_path}")

    try:
        with open(
            input_path,
            "r",
            encoding="utf-8",
        ) as file:
            source = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {input_path} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(source, dict):
        raise ValueError("Step 1 JSON 최상위 값은 객체여야 합니다.")

    (
        step2_1,
        step2_2,
        step2_3,
        step2_4,
        step2_5,
    ) = build_step2_results(
        source,
        domain_config=load_domain_config(rules_path),
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

    stem = re.sub(
        r"_step1-3_hierarchy$",
        "",
        stem,
    )

    path_21 = os.path.join(
        output_dir,
        (
            f"{stem}_step2-1_"
            "normalized_titles.json"
        ),
    )

    path_22 = os.path.join(
        output_dir,
        (
            f"{stem}_step2-2_"
            "domain_matches.json"
        ),
    )

    path_23 = os.path.join(
        output_dir,
        (
            f"{stem}_step2-3_"
            "domain_tagged.json"
        ),
    )

    path_24 = os.path.join(
        output_dir,
        (
            f"{stem}_step2-4_"
            "hierarchy_conflicts.json"
        ),
    )

    path_25 = os.path.join(
        output_dir,
        (
            f"{stem}_step2-5_"
            "domain_repaired.json"
        ),
    )

    save_json(
        path_21,
        step2_1,
    )

    save_json(
        path_22,
        step2_2,
    )

    save_json(
        path_23,
        step2_3,
    )

    save_json(
        path_24,
        step2_4,
    )

    save_json(
        path_25,
        step2_5,
    )

    return (
        path_21,
        path_22,
        path_23,
        path_24,
        path_25,
    )


# ===========================================================================
# 입력 파일 선택
# ===========================================================================

def select_input_json() -> str | None:
    """Step 1 최종 hierarchy JSON 선택."""

    root = Tk()

    root.withdraw()

    root.attributes(
        "-topmost",
        True,
    )

    selected = (
        askopenfilename(
            title=(
                "1단계 최종 계층 "
                "JSON 선택"
            ),
            filetypes=[
                (
                    "Step1 hierarchy JSON",
                    (
                        "*_step1-3_"
                        "hierarchy.json"
                    ),
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
# 콘솔 출력
# ===========================================================================

def print_conflict_summary(
    step2_4_path: str,
) -> None:
    """2-4 충돌 결과 출력."""

    with open(
        step2_4_path,
        "r",
        encoding="utf-8",
    ) as file:
        result = json.load(
            file
        )

    conflicts = (
        result.get(
            "conflicts",
            [],
        )
    )

    print()
    print("-" * 72)
    print(
        f"계층 충돌 후보: "
        f"{len(conflicts)}개"
    )
    print("-" * 72)

    if not conflicts:
        print(
            "계층 충돌 후보가 "
            "발견되지 않았습니다."
        )

        return

    for (
        index,
        conflict,
    ) in enumerate(
        conflicts,
        start=1,
    ):
        current_parent = (
            conflict.get(
                "current_parent",
                {},
            )
        )

        suggested_parent = (
            conflict.get(
                "suggested_parent",
                {},
            )
        )

        print(
            f"[{index}] "
            f"{conflict.get('child_title')}"
        )

        print(
            "  현재 부모 : "
            f"{current_parent.get('title')}"
        )

        print(
            "  추천 후보 : "
            f"{suggested_parent.get('title')}"
        )

        print(
            "  자식 domain : "
            f"{conflict.get('child_domain')}"
        )

        print()


def print_repair_summary(
    step2_5_path: str,
) -> None:
    """2-5 자동 재배치 결과 출력."""

    with open(
        step2_5_path,
        "r",
        encoding="utf-8",
    ) as file:
        result = json.load(
            file
        )

    repair_info = (
        result.get(
            "hierarchy_repair",
            {},
        )
    )

    repairs = (
        repair_info.get(
            "repairs",
            [],
        )
    )

    print()
    print("-" * 72)
    print(
        f"계층 자동 재배치: "
        f"{len(repairs)}건"
    )
    print("-" * 72)

    if not repairs:
        print(
            "안전 조건을 만족하는 "
            "자동 재배치 대상이 없습니다."
        )

        return

    for (
        index,
        repair,
    ) in enumerate(
        repairs,
        start=1,
    ):
        current_parent = (
            repair.get(
                "current_parent",
                {},
            )
        )

        new_parent = (
            repair.get(
                "new_parent",
                {},
            )
        )

        moved_sections = (
            repair.get(
                "moved_sections",
                [],
            )
        )

        print(
            f"[{index}] "
            f"{current_parent.get('title')}"
            " → "
            f"{new_parent.get('title')}"
        )

        print(
            "  이동 Section:"
        )

        for section in moved_sections:
            print(
                "   - "
                f"{section.get('title')}"
            )

        print()


# ===========================================================================
# 실행
# ===========================================================================

def main() -> None:
    input_path = (
        select_input_json()
    )

    if not input_path:
        print(
            "JSON 파일을 "
            "선택하지 않았습니다."
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
        KeyError,
        IndexError,
    ) as error:
        messagebox.showerror(
            "2단계 구조화 실패",
            str(error),
        )

        raise

    print()
    print("=" * 72)
    print(
        "2단계 도메인 태깅, "
        "계층 검사 및 재배치 완료"
    )
    print("=" * 72)

    for output in outputs:
        print(
            output
        )

    # 2-4
    print_conflict_summary(
        outputs[3]
    )

    # 2-5
    print_repair_summary(
        outputs[4]
    )

    messagebox.showinfo(
        "2단계 구조화 완료",
        (
            "2-1 ~ 2-5 결과를 "
            "생성했습니다.\n\n"
            + "\n".join(
                outputs
            )
            + "\n\n"
            + "다음 단계에서는 "
            "*_step2-5_domain_repaired.json을 "
            "사용하세요."
        ),
    )


if __name__ == "__main__":
    main()