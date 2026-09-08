from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


# ============================================================
# Backend key_information 테이블에 저장할 필수 7개 필드
# ============================================================
REQUIRED_FIELDS = (
    "application_period",
    "eligibility",
    "supply_information",
    "income_asset_criteria",
    "required_documents",
    "winner_announcement",
    "contact_information",
)


# ============================================================
# Structure Domain → 핵심정보 Field 연결 규칙
# ============================================================
FIELD_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "application_period": {
        "categories": (
            "schedule",
            "application",
        ),
        "topics": (
            "application_period",
            "application_schedule",
            "application_date",
            "application_reception",
            "application_method",
            "supply_schedule",
        ),
        "keywords": (
            "신청기간",
            "신청 기간",
            "접수기간",
            "접수 기간",
            "신청일정",
            "신청 일정",
            "공급일정",
            "공급 일정",
            "접수일정",
            "접수 일정",
            "청약일정",
            "청약 일정",
        ),
    },
    "eligibility": {
        "categories": (
            "eligibility",
            "qualification",
        ),
        "topics": (
            "application_qualification",
            "eligibility",
            "eligibility_criteria",
            "application_eligibility",
        ),
        "keywords": (
            "신청자격",
            "신청 자격",
            "입주자격",
            "입주 자격",
            "자격요건",
            "자격 요건",
            "신청대상",
            "신청 대상",
            "공급대상",
            "공급 대상",
            "무주택세대구성원",
            "무주택 세대구성원",
        ),
    },
    "supply_information": {
        "categories": (
            "supply",
            "housing",
            "price",
        ),
        "topics": (
            "supply_information",
            "supply_plan",
            "housing_supply",
            "supply_price",
            "rental_condition",
            "housing_information",
        ),
        "keywords": (
            "공급정보",
            "공급 정보",
            "공급대상",
            "공급 대상",
            "공급계획",
            "공급 계획",
            "공급위치",
            "공급 위치",
            "주택형",
            "주택형별",
            "임대조건",
            "임대 조건",
            "공급호수",
            "공급 호수",
            "모집호수",
            "모집 호수",
            "건설위치",
            "건설 위치",
        ),
    },
    "income_asset_criteria": {
        "categories": (
            "income_asset",
            "asset",
            "income",
        ),
        "topics": (
            "income_asset_criteria",
            "income_criteria",
            "asset_criteria",
            "income_asset",
            "income_and_asset",
        ),
        "keywords": (
            "소득 및 자산",
            "소득·자산",
            "소득자산",
            "소득 기준",
            "소득기준",
            "자산 기준",
            "자산기준",
            "총자산",
            "자동차가액",
            "자동차 가액",
        ),
    },
    "required_documents": {
        "categories": (
            "documents",
            "document",
            "submission",
        ),
        "topics": (
            "required_documents",
            "submission_documents",
            "documents",
            "document_submission",
        ),
        "keywords": (
            "제출서류",
            "제출 서류",
            "구비서류",
            "구비 서류",
            "신청서류",
            "신청 서류",
            "필요서류",
            "필요 서류",
            "증빙서류",
            "증빙 서류",
        ),
    },
    "winner_announcement": {
        "categories": (
            "winner",
            "selection",
            "schedule",
        ),
        "topics": (
            "winner_announcement",
            "winner_selection",
            "selection_result",
            "result_announcement",
            "candidate_announcement",
        ),
        "keywords": (
            "당첨자 발표",
            "당첨자발표",
            "당첨자 선정",
            "당첨자선정",
            "입주대상자 발표",
            "입주 대상자 발표",
            "예비입주자 발표",
            "예비입주자발표",
            "예비입주자 순번 발표",
            "예비 입주자 순번 발표",
            "예비자 순번 발표",
            "예비입주대상자 발표",
            "예비 입주 대상자 발표",
            "선정결과 발표",
            "선정 결과 발표",
            "당첨 발표",
        ),
    },
    "contact_information": {
        "categories": (
            "contact",
            "inquiry",
        ),
        "topics": (
            "contact_information",
            "contact",
            "inquiry",
            "customer_service",
        ),
        "keywords": (
            "문의처",
            "문의 처",
            "문의",
            "연락처",
            "연락 처",
            "콜센터",
            "주택전시관",
            "상담",
        ),
    },
}


INCOME_ASSET_KEYWORDS = FIELD_RULES[
    "income_asset_criteria"
]["keywords"]


WINNER_PRIORITY_KEYWORDS = (
    "예비입주자 순번 발표",
    "예비 입주자 순번 발표",
    "예비자 순번 발표",
    "입주대상자 발표",
    "입주 대상자 발표",
    "당첨자 발표",
)

WINNER_EXCLUSION_KEYWORDS = (
    "서류제출대상자 발표",
    "서류 제출 대상자 발표",
)


# ============================================================
# supply_information 검증 규칙
# ============================================================
SUPPLY_TITLE_KEYWORDS = (
    "공급정보",
    "공급 정보",
    "공급대상",
    "공급 대상",
    "공급계획",
    "공급 계획",
    "공급내역",
    "공급 내역",
    "공급현황",
    "공급 현황",
    "주택공급",
    "주택 공급",
    "주택형별",
    "임대조건",
    "임대 조건",
)

SUPPLY_DATA_KEYWORDS = (
    "주택형",
    "전용면적",
    "공급호수",
    "공급 호수",
    "모집호수",
    "모집 호수",
    "공급세대",
    "공급 세대",
    "공급세대수",
    "공급 세대수",
    "모집세대",
    "모집 세대",
    "모집세대수",
    "모집 세대수",
    "임대보증금",
    "임대 보증금",
    "월임대료",
    "월 임대료",
    "임대조건",
    "임대 조건",
    "공급위치",
    "공급 위치",
    "건설위치",
    "건설 위치",
)

SUPPLY_EXCLUSION_KEYWORDS = (
    "개인정보 수집",
    "개인정보 이용",
    "개인정보 제공",
    "개인정보 처리",
    "민감정보 수집",
    "민감정보 이용",
    "민감정보 활용",
    "동의 거부",
    "동의여부",
    "동의 여부",
    "제3자 제공",
    "개인정보의 제3자",
    "보유·이용 기간",
    "보유 이용 기간",
)


# ============================================================
# 신청자격 공급계층 규칙
#
# 이 값들은 "summary 문장 생성"에 사용하지 않는다.
# target_groups 구조화와 자세히 보기용 그룹 분리에만 사용한다.
# ============================================================
ELIGIBILITY_TARGET_GROUPS = (
    {
        "code": "college_student",
        "label": "대학생계층",
        "keywords": (
            "대학생계층",
            "대학생 계층",
            "대학생",
            "취업준비생",
        ),
    },
    {
        "code": "youth",
        "label": "청년계층",
        "keywords": (
            "청년계층",
            "청년 계층",
            "청년",
            "사회초년생",
        ),
    },
    {
        "code": "newlywed_family",
        "label": "신혼부부·예비신혼부부·한부모가족",
        "keywords": (
            "신혼부부",
            "예비신혼부부",
            "예비 신혼부부",
            "한부모가족",
            "한부모 가족",
            "신혼·신생아",
            "신혼 신생아",
        ),
    },
    {
        "code": "senior",
        "label": "고령자",
        "keywords": (
            "고령자계층",
            "고령자 계층",
            "고령자",
        ),
    },
    {
        "code": "housing_benefit",
        "label": "주거급여수급자",
        "keywords": (
            "주거급여수급자",
            "주거급여 수급자",
        ),
    },
)


# ============================================================
# JSON
# ============================================================
def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(
            f"파일이 없습니다: {path}"
        )

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"JSON 읽기 실패: {path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            f"JSON 최상위가 객체가 아닙니다: {path}"
        )

    return data


# ============================================================
# 문자열
# ============================================================
def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalized_match_text(value: Any) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r"\s+", "", text)
    return text


def _contains_keyword(
    text: str,
    keywords: Iterable[str],
) -> bool:
    normalized_text = _normalized_match_text(
        text
    )

    return any(
        _normalized_match_text(keyword)
        in normalized_text
        for keyword in keywords
    )


def _deduplicate_texts(
    values: Iterable[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _clean_text(value)

        if not cleaned:
            continue

        key = re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


# ============================================================
# Structure 내용 → 읽을 수 있는 텍스트
# ============================================================
def _iter_nested_dicts(
    value: Any,
) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from _iter_nested_dicts(
                child
            )

    elif isinstance(value, list):
        for child in value:
            yield from _iter_nested_dicts(
                child
            )


def _content_text(content: Any) -> str:
    """paragraph/table/structured_table을 보수적으로 문자열화한다."""

    if not isinstance(content, dict):
        return ""

    values: list[str] = []

    direct_text = _clean_text(
        content.get("text")
    )

    if direct_text:
        values.append(direct_text)

    structured_table = content.get(
        "structured_table"
    )

    if isinstance(
        structured_table,
        dict,
    ):
        for node in _iter_nested_dicts(
            structured_table
        ):
            value = node.get("value")

            if isinstance(
                value,
                (str, int, float),
            ):
                cleaned = _clean_text(
                    value
                )
                if cleaned:
                    values.append(
                        cleaned
                    )

            key = node.get("key")

            if isinstance(
                key,
                (str, int, float),
            ):
                cleaned = _clean_text(
                    key
                )
                if cleaned:
                    values.append(
                        cleaned
                    )

    cells = content.get("cells")

    if isinstance(cells, list):
        ordered_cells = sorted(
            (
                cell
                for cell in cells
                if isinstance(cell, dict)
            ),
            key=lambda cell: (
                int(cell.get("row", 0) or 0),
                int(cell.get("col", 0) or 0),
            ),
        )

        for cell in ordered_cells:
            cleaned = _clean_text(
                cell.get("text")
            )
            if cleaned:
                values.append(cleaned)

    return "\n".join(
        _deduplicate_texts(values)
    )


def _section_direct_text(
    section: dict[str, Any],
) -> str:
    values: list[str] = []

    title = _clean_text(
        section.get("title")
        or section.get(
            "normalized_title"
        )
    )

    if title:
        values.append(title)

    for content in section.get(
        "contents",
        [],
    ):
        text = _content_text(content)

        if text:
            values.append(text)

    return "\n".join(
        _deduplicate_texts(values)
    )


def _section_classification_text(
    section: dict[str, Any],
) -> str:
    return " ".join(
        _deduplicate_texts(
            (
                _clean_text(
                    section.get("title")
                ),
                _clean_text(
                    section.get(
                        "normalized_title"
                    )
                ),
                _clean_text(
                    section.get(
                        "search_title"
                    )
                ),
                _clean_text(
                    section.get(
                        "classification_text"
                    )
                ),
                _section_direct_text(
                    section
                ),
            )
        )
    )


# ============================================================
# Section 순회
# ============================================================
def _iter_sections(
    sections: Any,
    *,
    parent_path: tuple[str, ...] = (),
) -> Iterable[
    tuple[
        dict[str, Any],
        tuple[str, ...],
    ]
]:
    if not isinstance(sections, list):
        return

    for section in sections:
        if not isinstance(
            section,
            dict,
        ):
            continue

        title = _clean_text(
            section.get("title")
            or section.get(
                "normalized_title"
            )
        )

        current_path = (
            *parent_path,
            title,
        ) if title else parent_path

        yield section, current_path

        yield from _iter_sections(
            section.get("children"),
            parent_path=current_path,
        )


# ============================================================
# Domain / Section scoring
# ============================================================
def _domain_info(
    section: dict[str, Any],
) -> tuple[str, str, float]:
    domain = section.get("domain")

    if not isinstance(domain, dict):
        return "", "", 0.0

    category = _clean_text(
        domain.get("category")
    ).lower()

    topic = _clean_text(
        domain.get("topic")
    ).lower()

    try:
        confidence = float(
            domain.get("confidence")
            or 0.0
        )
    except (
        TypeError,
        ValueError,
    ):
        confidence = 0.0

    return (
        category,
        topic,
        confidence,
    )


def _count_keyword_matches(
    text: str,
    keywords: Iterable[str],
) -> int:
    normalized_text = (
        _normalized_match_text(text)
    )
    matched: set[str] = set()

    for keyword in keywords:
        normalized_keyword = (
            _normalized_match_text(
                keyword
            )
        )

        if (
            normalized_keyword
            and normalized_keyword
            in normalized_text
        ):
            matched.add(
                normalized_keyword
            )

    return len(matched)


def _is_valid_supply_section(
    section: dict[str, Any],
) -> bool:
    """실제 공급정보 특징과 제외 문맥을 함께 사용해 supply Section을 검증한다."""

    title_text = " ".join(
        _deduplicate_texts(
            (
                _clean_text(
                    section.get("title")
                ),
                _clean_text(
                    section.get(
                        "normalized_title"
                    )
                ),
                _clean_text(
                    section.get(
                        "search_title"
                    )
                ),
            )
        )
    )

    body_text = _section_direct_text(
        section
    )
    full_text = (
        f"{title_text} {body_text}"
    )

    category, topic, _ = (
        _domain_info(section)
    )

    supply_topics = {
        "supply_information",
        "supply_plan",
        "housing_supply",
        "supply_price",
        "rental_condition",
        "housing_information",
        "supply_target",
        "supply_scale",
    }
    supply_categories = {
        "supply",
        "housing",
        "price",
    }

    if (
        category
        and category
        not in supply_categories
    ):
        return False

    strong_topic = (
        topic in supply_topics
    )
    title_match = _contains_keyword(
        title_text,
        SUPPLY_TITLE_KEYWORDS,
    )
    data_evidence_count = (
        _count_keyword_matches(
            full_text,
            SUPPLY_DATA_KEYWORDS,
        )
    )
    excluded_context = (
        _contains_keyword(
            full_text,
            SUPPLY_EXCLUSION_KEYWORDS,
        )
    )

    if (
        excluded_context
        and data_evidence_count < 2
    ):
        return False

    if strong_topic:
        return True

    if title_match:
        return True

    if category in supply_categories:
        return (
            data_evidence_count >= 1
        )

    return data_evidence_count >= 2


def _score_section_for_field(
    section: dict[str, Any],
    field: str,
) -> int:
    rule = FIELD_RULES[field]

    if (
        field == "supply_information"
        and not _is_valid_supply_section(
            section
        )
    ):
        return 0

    category, topic, confidence = (
        _domain_info(section)
    )

    classification_text = (
        _section_classification_text(
            section
        )
    )

    score = 0

    if (
        topic
        and topic in set(
            rule["topics"]
        )
    ):
        score += 100

    if (
        category
        and category in set(
            rule["categories"]
        )
    ):
        score += 50

    if score > 0:
        score += int(
            max(
                0.0,
                min(
                    confidence,
                    1.0,
                ),
            )
            * 10
        )

    matched_keyword_count = sum(
        1
        for keyword in rule[
            "keywords"
        ]
        if _contains_keyword(
            classification_text,
            (keyword,),
        )
    )

    score += (
        min(
            matched_keyword_count,
            5,
        )
        * 10
    )

    if field == "eligibility":
        if _contains_keyword(
            classification_text,
            INCOME_ASSET_KEYWORDS,
        ):
            score -= 30

    if field == "income_asset_criteria":
        if (
            category == "eligibility"
            and _contains_keyword(
                classification_text,
                INCOME_ASSET_KEYWORDS,
            )
        ):
            score += 60

    if field == "winner_announcement":
        winner_keyword_match = (
            _contains_keyword(
                classification_text,
                rule["keywords"],
            )
        )

        if (
            category == "schedule"
            and topic not in set(
                rule["topics"]
            )
            and not winner_keyword_match
        ):
            return 0

    if field == "application_period":
        app_keyword_match = (
            _contains_keyword(
                classification_text,
                rule["keywords"],
            )
        )

        if (
            category == "schedule"
            and topic not in set(
                rule["topics"]
            )
            and not app_keyword_match
        ):
            return 0

    return max(
        score,
        0,
    )


# ============================================================
# 정규화 Entity 추출
# ============================================================
def _collect_entities(
    value: Any,
    *,
    entity_type: str,
) -> list[dict[str, Any]]:
    result: list[
        dict[str, Any]
    ] = []
    seen: set[
        tuple[str, str]
    ] = set()

    for node in _iter_nested_dicts(
        value
    ):
        entities = node.get(
            "entities"
        )

        if not isinstance(
            entities,
            list,
        ):
            continue

        for entity in entities:
            if not isinstance(
                entity,
                dict,
            ):
                continue

            if (
                _clean_text(
                    entity.get("type")
                ).lower()
                != entity_type.lower()
            ):
                continue

            raw = _clean_text(
                entity.get("raw")
            )
            normalized = _clean_text(
                entity.get(
                    "normalized_value"
                )
            )

            key = (
                raw,
                normalized,
            )

            if key in seen:
                continue

            seen.add(key)

            result.append(
                {
                    "raw": raw,
                    "normalized_value": (
                        normalized
                    ),
                    "precision": (
                        entity.get(
                            "precision"
                        )
                    ),
                }
            )

    return result


def _extract_date_bounds(
    matches: list[
        dict[str, Any]
    ],
) -> tuple[
    str | None,
    str | None,
    list[dict[str, Any]],
]:
    dates: list[
        dict[str, Any]
    ] = []
    seen: set[str] = set()

    for match in matches:
        section = match[
            "_section"
        ]

        for entity in (
            _collect_entities(
                section,
                entity_type="date",
            )
        ):
            normalized = _clean_text(
                entity.get(
                    "normalized_value"
                )
            )

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            dates.append(entity)

    normalized_dates = sorted(
        (
            entity[
                "normalized_value"
            ]
            for entity in dates
            if entity.get(
                "normalized_value"
            )
        )
    )

    start = (
        normalized_dates[0]
        if normalized_dates
        else None
    )
    end = (
        normalized_dates[-1]
        if normalized_dates
        else None
    )

    return (
        start,
        end,
        dates,
    )


# ============================================================
# Card summaries and date fallback
# ============================================================
_DATE_PATTERN = re.compile(
    r"(?P<year>20\d{2}|\d{2})"
    r"\s*[./-]\s*"
    r"(?P<month>\d{1,2})"
    r"\s*[./-]\s*"
    r"(?P<day>\d{1,2})"
    r"\s*\.?"
    r"(?:\s*\([^)]{1,3}\))?"
    r"(?:"
    r"\s*(?P<ampm>\uC624\uC804|\uC624\uD6C4)?"
    r"\s*(?P<hour>\d{1,2})"
    r"(?:"
    r":(?P<minute>\d{2})"
    r"|"
    r"\uC2DC(?:\s*(?P<minute_word>\d{1,2})\uBD84)?"
    r")"
    r")?"
)


def _date_match_to_entity(
    match: re.Match[str],
) -> dict[str, Any]:
    year = int(
        match.group("year")
    )

    if year < 100:
        year += 2000

    month = int(
        match.group("month")
    )
    day = int(
        match.group("day")
    )

    normalized = (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )

    hour_value = match.group(
        "hour"
    )

    if hour_value is not None:
        hour = int(hour_value)
        minute = int(
            match.group("minute")
            or match.group(
                "minute_word"
            )
            or 0
        )

        ampm = match.group("ampm")

        if (
            ampm == "\uC624\uD6C4"
            and hour < 12
        ):
            hour += 12

        if (
            ampm == "\uC624\uC804"
            and hour == 12
        ):
            hour = 0

        normalized += (
            f" {hour:02d}:"
            f"{minute:02d}"
        )

    return {
        "raw": (
            match.group(0).strip()
        ),
        "normalized_value": (
            normalized
        ),
        "precision": (
            "regex_fallback"
        ),
    }


_APPLICATION_RANGE_SEPARATORS = {
    "~",
    "～",
    "-",
    "–",
    "—",
    "부터",
}

_APPLICATION_RANGE_END_LABELS = {
    "마감일",
    "종료일",
    "마감",
    "종료",
    "접수마감일",
    "신청마감일",
    "접수종료일",
    "신청종료일",
    "접수마감",
    "신청마감",
    "접수종료",
    "신청종료",
}

_APPLICATION_RANGE_QUOTE_PATTERN = (
    re.compile(
        r"""[‘’'"“”`]"""
    )
)


def _is_application_range_bridge(
    value: str,
) -> bool:
    normalized = (
        _normalized_match_text(
            value
        )
    )

    normalized = (
        _APPLICATION_RANGE_QUOTE_PATTERN.sub(
            "",
            normalized,
        )
    )

    if not normalized:
        return False

    if (
        normalized
        in _APPLICATION_RANGE_SEPARATORS
    ):
        return True

    if len(normalized) > 32:
        return False

    if (
        normalized
        in _APPLICATION_RANGE_END_LABELS
    ):
        return True

    for separator in (
        _APPLICATION_RANGE_SEPARATORS
    ):
        if not normalized.startswith(
            separator
        ):
            continue

        remainder = normalized[
            len(separator):
        ]

        if (
            remainder
            in _APPLICATION_RANGE_END_LABELS
        ):
            return True

    return False


def _extract_application_range(
    matches: list[
        dict[str, Any]
    ],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
] | None:
    positive_keywords = {
        "\uC2E0\uCCAD\uC811\uC218": 20,
        "\uC811\uC218\uAE30\uAC04": 20,
        "\uC2E0\uCCAD\uAE30\uAC04": 20,
        "\uCCAD\uC57D\uC811\uC218": 20,
        "\uC778\uD130\uB137\uC2E0\uCCAD": 12,
        "\uC2E0\uCCAD": 5,
        "\uC811\uC218": 5,
    }

    negative_keywords = {
        "\uC11C\uB958\uC81C\uCD9C": 30,
        "\uC11C\uB958\uC811\uC218": 30,
        "\uBC1C\uD45C": 20,
        "\uACC4\uC57D": 20,
    }

    best = None

    for (
        match_index,
        item,
    ) in enumerate(matches[:8]):
        text = _clean_text(
            item.get("text")
        )

        found = list(
            _DATE_PATTERN.finditer(
                text
            )
        )

        for left, right in zip(
            found,
            found[1:],
        ):
            between = text[
                left.end():
                right.start()
            ]

            if (
                not _is_application_range_bridge(
                    between
                )
            ):
                continue

            label = text[
                max(
                    0,
                    left.start() - 180,
                ):
                left.start()
            ]

            normalized_label = (
                _normalized_match_text(
                    label
                )
            )

            score = 0

            for (
                keyword,
                weight,
            ) in (
                positive_keywords.items()
            ):
                if (
                    _normalized_match_text(
                        keyword
                    )
                    in normalized_label
                ):
                    score += weight

            for (
                keyword,
                weight,
            ) in (
                negative_keywords.items()
            ):
                if (
                    _normalized_match_text(
                        keyword
                    )
                    in normalized_label
                ):
                    score -= weight

            if score <= 0:
                continue

            start_entity = (
                _date_match_to_entity(
                    left
                )
            )
            end_entity = (
                _date_match_to_entity(
                    right
                )
            )

            candidate = (
                score,
                -match_index,
                start_entity,
                end_entity,
            )

            if (
                best is None
                or candidate[:2]
                > best[:2]
            ):
                best = candidate

    if best is None:
        return None

    return (
        best[2],
        best[3],
    )


def _summary_lines(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    result: list[str] = []

    for match in matches[:8]:
        text = _clean_text(
            match.get("text")
        )

        for line in text.splitlines():
            line = re.sub(
                r"\s+",
                " ",
                line,
            ).strip()

            if (
                line
                and line not in result
            ):
                result.append(line)

    return result


def _compact_summary(
    value: Any,
    max_length: int = 200,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        _clean_text(value),
    ).strip()

    if len(text) <= max_length:
        return text

    return (
        text[:max_length]
        .rstrip(" ,;/")
        + "\u2026"
    )


def _best_summary_line(
    matches: list[
        dict[str, Any]
    ],
    required: tuple[
        str,
        ...
    ],
    preferred: tuple[
        str,
        ...
    ],
    max_length: int = 200,
) -> str:
    best = None

    for index, line in enumerate(
        _summary_lines(matches)
    ):
        normalized = (
            _normalized_match_text(
                line
            )
        )

        if not any(
            _normalized_match_text(
                keyword
            )
            in normalized
            for keyword in required
        ):
            continue

        score = sum(
            10
            for keyword in preferred
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            )
        )

        candidate = (
            score,
            -index,
            line,
        )

        if (
            best is None
            or candidate[:2]
            > best[:2]
        ):
            best = candidate

    if best is None:
        return ""

    return _compact_summary(
        best[2],
        max_length,
    )


# ============================================================
# 신청자격 - 공급계층 구조화
# ============================================================
def _normalize_eligibility_line(
    value: Any,
) -> str:
    text = _clean_text(value)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _eligibility_search_lines(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for match in matches[:10]:
        text = _clean_text(
            match.get("text")
        )

        if not text:
            continue

        for raw_line in (
            text.splitlines()
        ):
            line = (
                _normalize_eligibility_line(
                    raw_line
                )
            )

            if not line:
                continue

            normalized = (
                _normalized_match_text(
                    line
                )
            )

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(line)

    return result


def _line_has_group_keyword(
    line: str,
    keywords: tuple[str, ...],
) -> bool:
    normalized = (
        _normalized_match_text(
            line
        )
    )

    return any(
        _normalized_match_text(
            keyword
        )
        in normalized
        for keyword in keywords
    )


def _is_probable_target_group_line(
    line: str,
    keywords: tuple[str, ...],
) -> bool:
    """
    실제 공급계층의 제목/자격 시작 문장인지 판별한다.

    공고 제목이나 단순 언급에 포함된
    '청년', '고령자' 등은 계층 시작점에서 제외한다.
    """

    if not _line_has_group_keyword(
        line,
        keywords,
    ):
        return False

    cleaned = (
        _normalize_eligibility_line(
            line
        )
    )

    normalized = (
        _normalized_match_text(
            cleaned
        )
    )

    # -----------------------------------------------
    # 공고 제목 / 일반 안내에서 우연히 등장한 경우 제외
    # -----------------------------------------------
    exclusion_keywords = (
        "주택관리번호",
        "주택명",
        "입주자 모집공고",
        "입주자모집공고문",
        "행복주택 입주자 모집",
        "영구임대 입주자 모집",
        "청약통장",
        "은행 방문",
        "문의처",
    )

    if _contains_keyword(
        cleaned,
        exclusion_keywords,
    ):
        return False

    # -----------------------------------------------
    # 1. 가장 강한 근거:
    #
    # 3-1. 대학생 계층
    # 3-2. 청년 계층
    # 3-3. 신혼부부·한부모가족 계층
    # -----------------------------------------------
    if re.search(
        r"^\s*\d+(?:-\d+)+(?:[.)])?\s*.*계층",
        cleaned,
    ):
        return True

    # -----------------------------------------------
    # 2. 짧은 계층 제목
    #
    # 대학생 계층
    # 청년계층
    # 고령자
    # -----------------------------------------------
    if (
        len(cleaned) <= 50
        and (
            "계층" in normalized
            or normalized
            in {
                _normalized_match_text(
                    keyword
                )
                for keyword in keywords
            }
        )
    ):
        return True

    # -----------------------------------------------
    # 3. 실제 신청자격 시작 문장
    # -----------------------------------------------
    qualification_contexts = (
        "입주자모집공고일",
        "모집공고일현재",
        "신청자격",
        "입주자격",
        "아래의요건",
        "모두갖춘자",
    )

    if any(
        _normalized_match_text(
            keyword
        )
        in normalized
        for keyword
        in qualification_contexts
    ):
        return True

    return False


def _extract_eligibility_target_groups(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    eligibility 후보에서 실제 모집 공급계층을 구조화한다.

    핵심 원칙:
    - 단순히 키워드가 등장한 줄 뒤 5개를 가져오지 않는다.
    - 각 공급계층의 시작점을 찾는다.
    - 현재 공급계층 시작점부터 다음 공급계층 시작점 직전까지를
      해당 계층의 details 후보로 사용한다.
    - 공통 안내문/타 계층 내용이 섞이는 것을 줄인다.
    """

    lines = _eligibility_search_lines(
        matches
    )

    if not lines:
        return []

    # --------------------------------------------------------
    # 1. 각 공급계층의 "시작점" 탐색
    # --------------------------------------------------------
    group_starts: list[
        dict[str, Any]
    ] = []

    for index, line in enumerate(lines):
        for rule in ELIGIBILITY_TARGET_GROUPS:
            keywords = rule["keywords"]

            if not _line_has_group_keyword(
                line,
                keywords,
            ):
                continue

            if not _is_probable_target_group_line(
                line,
                keywords,
            ):
                continue

            group_starts.append(
                {
                    "index": index,
                    "rule": rule,
                    "line": line,
                }
            )

    if not group_starts:
        return []

    # 같은 index에서 여러 계층이 동시에 잡힐 수 있다.
    # 예:
    # "대학생, 청년, 예비신혼부부..." 같은 공통 안내문
    #
    # 이런 줄은 개별 계층의 시작점으로 쓰지 않는 것이 안전하다.
    index_counts: dict[int, int] = {}

    for item in group_starts:
        index = int(item["index"])

        index_counts[index] = (
            index_counts.get(
                index,
                0,
            )
            + 1
        )

    filtered_starts: list[
        dict[str, Any]
    ] = []

    for item in group_starts:
        index = int(item["index"])
        line = str(item["line"])

        # 한 줄에서 여러 계층이 동시에 발견되면
        # 공통 설명일 가능성이 높으므로
        # 개별 계층 블록 시작점으로 사용하지 않는다.
        if index_counts[index] > 1:
            continue

        # 너무 긴 문장은 제목/소제목보다 본문 설명일 가능성이 높다.
        if len(line) > 120:
            continue

        filtered_starts.append(
            item
        )

    # --------------------------------------------------------
    # 2. 위 필터에서 시작점이 하나도 안 남은 경우
    #    짧은 계층명 라인을 한 번 더 탐색
    # --------------------------------------------------------
    if not filtered_starts:
        for index, line in enumerate(lines):
            normalized_line = (
                _normalized_match_text(
                    line
                )
            )

            for rule in ELIGIBILITY_TARGET_GROUPS:
                matched_keywords = [
                    keyword
                    for keyword
                    in rule["keywords"]
                    if (
                        _normalized_match_text(
                            keyword
                        )
                        in normalized_line
                    )
                ]

                if not matched_keywords:
                    continue

                # 짧은 제목/소제목 형태만 인정
                if len(line) <= 60:
                    filtered_starts.append(
                        {
                            "index": index,
                            "rule": rule,
                            "line": line,
                        }
                    )
                    break

    if not filtered_starts:
        return []

    # 문서 순서대로 정렬
    filtered_starts.sort(
        key=lambda item: (
            int(item["index"]),
        )
    )

    # --------------------------------------------------------
    # 3. 같은 계층이 여러 번 시작점으로 잡혔을 경우
    #    첫 번째 유효 시작점만 사용
    # --------------------------------------------------------
    unique_starts: list[
        dict[str, Any]
    ] = []

    seen_codes: set[str] = set()

    for item in filtered_starts:
        rule = item["rule"]
        code = str(
            rule["code"]
        )

        if code in seen_codes:
            continue

        seen_codes.add(code)
        unique_starts.append(
            item
        )

    # --------------------------------------------------------
    # 4. 각 계층 시작점 ~ 다음 계층 시작점 직전까지
    # --------------------------------------------------------
    groups: list[
        dict[str, Any]
    ] = []

    detail_exclusion_keywords = (
        "청약통장 가입은행",
        "은행 방문",
        "직접 발급",
        "인터넷",
        "문의처",
        "문의",
        "콜센터",
        "제출서류",
        "신청방법",
        "신청절차",
        "주택관리번호",
    )

    for start_position, item in enumerate(
        unique_starts
    ):
        start_index = int(
            item["index"]
        )
        rule = item["rule"]

        if (
            start_position + 1
            < len(unique_starts)
        ):
            end_index = int(
                unique_starts[
                    start_position + 1
                ]["index"]
            )
        else:
            # 마지막 계층은 너무 멀리까지 먹지 않도록
            # 최대 20줄까지만 사용한다.
            end_index = min(
                len(lines),
                start_index + 20,
            )

        block = lines[
            start_index:end_index
        ]

        details: list[str] = []
        seen_details: set[str] = set()

        for detail in block:
            detail = (
                _normalize_eligibility_line(
                    detail
                )
            )

            if not detail:
                continue

            normalized = (
                _normalized_match_text(
                    detail
                )
            )

            if normalized in seen_details:
                continue

            # 자격 상세와 무관한 안내 문구 제거
            if _contains_keyword(
                detail,
                detail_exclusion_keywords,
            ):
                continue

            # 지나치게 짧고 일반적인 텍스트 제외
            if len(detail) <= 2:
                continue

            # UI 과다 노출 방지
            detail = _compact_summary(
                detail,
                350,
            )

            seen_details.add(
                normalized
            )
            details.append(
                detail
            )

            if len(details) >= 8:
                break

        groups.append(
            {
                "code": rule["code"],
                "label": rule["label"],
                "details": details,
            }
        )

    return groups


def _eligibility_detail_lines(
    value: Any,
) -> list[str]:
    """
    '입주자격 확인서류' 표의 한 셀을
    UI에 그대로 보여줄 수 있는 상세 문장 목록으로 정리한다.

    원문에 없는 내용을 새로 만들지 않고,
    줄바꿈/불릿만 정리한다.
    """
    text = _clean_text(value)

    if not text:
        return []

    parts = re.split(
        r"(?:\n+|[•▪●■◆]+)",
        text,
    )

    result: list[str] = []
    seen: set[str] = set()

    for part in parts:
        cleaned = re.sub(
            r"^\s*[-*·]+\s*",
            "",
            _clean_text(part),
        ).strip()

        if not cleaned:
            continue

        normalized = (
            _normalized_match_text(
                cleaned
            )
        )

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(cleaned)

    return result


def _eligibility_group_code(
    label: str,
) -> str:
    """
    상세 자격 카드용 안정적인 code를 반환한다.
    label은 실제 문서의 '대상자' 셀 원문을 그대로 사용한다.
    """
    normalized = (
        _normalized_match_text(
            label
        )
    )

    if "취업준비생" in normalized:
        return "job_seeker"

    if "대학생" in normalized:
        return "college_student"

    if "청년" in normalized:
        return "youth"

    if (
        "신혼부부" in normalized
        or "예비신혼부부" in normalized
        or "한부모" in normalized
    ):
        return "newlywed_family"

    if "고령자" in normalized:
        return "senior"

    if "주거급여" in normalized:
        return "housing_benefit"

    safe = re.sub(
        r"[^0-9a-z가-힣]+",
        "_",
        label.lower(),
    ).strip("_")

    return (
        safe[:50]
        if safe
        else "eligibility_group"
    )


def _extract_eligibility_verification_groups(
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    '입주자격 확인서류' 표를 기준으로 상세 자격을 구조화한다.

    기대하는 표 형태:
        대상자 | 제출서류 | 발급처

    예:
        청년(19세~39세) | 없음(단, 본인 나이 확인 필요)
        대학생 | 재학증명서 / 입학증명서 ...
        취업준비생 | 건강보험 자격득실확인서 / 졸업증명서 ...

    핵심 원칙:
    - 상세 자격은 일반 '입주자격' 본문에서 임의로 잘라오지 않는다.
    - '입주자격 확인서류' 표의 대상자별 제출서류를 사용한다.
    - 병합셀 때문에 다음 행의 대상자가 비어 있으면 직전 대상자를 이어받는다.
    """
    target_section: dict[str, Any] | None = None
    best_score = -1

    for section, _ in _iter_sections(
        structure.get("sections")
    ):
        title = _clean_text(
            section.get("title")
            or section.get(
                "normalized_title"
            )
        )

        normalized = (
            _normalized_match_text(
                title
            )
        )

        score = 0

        if (
            "입주자격확인서류"
            in normalized
            or "자격요건확인구비서류"
            in normalized
        ):
            score = 100
        elif (
            "자격확인서류" in normalized
            or "자격요건확인" in normalized
            or (
                "입주자격" in normalized
                and "서류" in normalized
            )
        ):
            score = 80

        if score > best_score:
            best_score = score
            target_section = section

    if (
        target_section is None
        or best_score <= 0
    ):
        return []

    groups_by_label: dict[
        str,
        dict[str, Any],
    ] = {}
    group_order: list[str] = []

    for node in _iter_nested_dicts(
        target_section
    ):
        cells = node.get("cells")

        if not isinstance(cells, list):
            continue

        table_cells = [
            cell
            for cell in cells
            if isinstance(cell, dict)
        ]

        if not table_cells:
            continue

        rows: dict[
            int,
            dict[int, str],
        ] = {}

        for cell in table_cells:
            row = cell.get("row")
            col = cell.get("col")

            if (
                not isinstance(row, int)
                or not isinstance(col, int)
            ):
                continue

            value = _clean_text(
                cell.get("text")
            )

            if not value:
                continue

            rows.setdefault(
                row,
                {},
            )[col] = value

        if not rows:
            continue

        header_row: int | None = None
        target_col: int | None = None
        document_col: int | None = None
        issuer_col: int | None = None

        for row_number in sorted(rows):
            candidate_target = None
            candidate_document = None
            candidate_issuer = None

            for col, value in rows[
                row_number
            ].items():
                normalized = (
                    _normalized_match_text(
                        value
                    )
                )

                if normalized in {
                    "대상자",
                    "대상",
                    "신청대상",
                }:
                    candidate_target = col

                if (
                    "제출서류" in normalized
                    or normalized == "서류"
                    or "확인서류" in normalized
                ):
                    candidate_document = col

                if (
                    "발급처" in normalized
                    or "발급기관" in normalized
                    or "발행처" in normalized
                ):
                    candidate_issuer = col

            if (
                candidate_target is not None
                and candidate_document is not None
            ):
                header_row = row_number
                target_col = candidate_target
                document_col = (
                    candidate_document
                )
                issuer_col = candidate_issuer
                break

        if (
            header_row is None
            or target_col is None
            or document_col is None
        ):
            continue

        current_target = ""

        for row_number in sorted(rows):
            if row_number <= header_row:
                continue

            row_values = rows[
                row_number
            ]

            target_value = _clean_text(
                row_values.get(
                    target_col
                )
            )

            if target_value:
                # 반복 header는 data로 사용하지 않는다.
                if _normalized_match_text(
                    target_value
                ) in {
                    "대상자",
                    "대상",
                    "신청대상",
                }:
                    continue

                current_target = target_value

            if not current_target:
                continue

            documents_value = _clean_text(
                row_values.get(
                    document_col
                )
            )

            issuer_value = (
                _clean_text(
                    row_values.get(
                        issuer_col
                    )
                )
                if issuer_col is not None
                else ""
            )

            if not documents_value:
                continue

            group_key = (
                _normalized_match_text(
                    current_target
                )
            )

            if group_key not in (
                groups_by_label
            ):
                groups_by_label[
                    group_key
                ] = {
                    "code": (
                        _eligibility_group_code(
                            current_target
                        )
                    ),
                    "label": (
                        current_target
                    ),
                    "details": [],
                }
                group_order.append(
                    group_key
                )

            details = (
                groups_by_label[
                    group_key
                ]["details"]
            )

            for detail in (
                _eligibility_detail_lines(
                    documents_value
                )
            ):
                if detail not in details:
                    details.append(detail)

            if issuer_value:
                issuer_line = (
                    f"발급처: {issuer_value}"
                )

                if issuer_line not in details:
                    details.append(
                        issuer_line
                    )

    return [
        groups_by_label[key]
        for key in group_order
        if groups_by_label[
            key
        ]["details"]
    ]


def _build_eligibility_summary_from_structure(
    structure: dict[str, Any],
) -> str:
    """
    상단 '신청 자격'에는 실제 입주자격/신청자격 Section의
    공통·기본 자격만 짧게 표시한다.

    핵심 원칙:
    - 문서 전체의 eligibility 후보를 섞지 않는다.
    - 정확한 '입주자격/신청자격' Section을 우선한다.
    - 무주택세대구성원 정의, 미성년자 예외, 일반 유의사항처럼
      기본 자격 뒤에 이어지는 설명은 summary에서 제거한다.
    - 대상별 세부조건은 target_groups로 분리한다.
    """
    best: tuple[int, str] | None = None

    detail_group_names = (
        "대학생",
        "대학원생",
        "취업준비생",
        "청년",
        "신혼부부",
        "예비신혼부부",
        "한부모가족",
        "지원대상 한부모가족",
        "유자녀 혼인가구",
        "신생아 가구",
        "신생아가구",
        "혼인가구",
        "고령자",
        "주거급여수급자",
    )

    group_start_pattern = re.compile(
        r"(?:^|\s)"
        r"(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+(?:-\d+)?)"
        r"\s*"
        r"(?:"
        + "|".join(
            re.escape(name)
            for name in detail_group_names
        )
        + r")",
        re.IGNORECASE,
    )

    # 기본 자격 뒤에 붙는 정의/예외/유의사항의 대표 시작점.
    # 이 문자열이 나오기 전까지만 카드 summary로 사용한다.
    summary_stop_keywords = (
        "무주택세대구성원 :",
        "무주택세대구성원:",
        "세대구성원 :",
        "세대구성원:",
        "자격 요건",
        "자격요건 확인",
        "입주자격 확인서류",
        "신청자격별",
        "공고내용을 숙지",
        "공고내용을 반드시 숙지",
        "당해주택 입주자는",
        "선정기준",
        "입주순위",
        "제출서류",
        "■ 성년자",
        "성년자 「민법",
    )

    for section, _ in _iter_sections(
        structure.get("sections")
    ):
        title = _clean_text(
            section.get("title")
            or section.get("normalized_title")
        )
        normalized_title = _normalized_match_text(title)

        if (
            "입주자격" not in normalized_title
            and "신청자격" not in normalized_title
        ):
            continue

        if any(
            excluded in normalized_title
            for excluded in (
                "입주자격확인서류",
                "자격확인서류",
                "자격요건확인구비서류",
                "제출서류",
                "확인서류",
            )
        ):
            continue

        # summary는 해당 Section 자체의 직접 내용만 사용한다.
        # 자식 Section까지 합치면 다른 계층 설명이 카드 상단으로
        # 올라오는 경우가 있어 의도적으로 제외한다.
        compact = re.sub(
            r"\s+",
            " ",
            _clean_text(_section_direct_text(section)),
        ).strip()

        if not compact:
            continue

        for prefix in (
            "입주자격 ",
            "신청자격 ",
        ):
            if compact.startswith(prefix):
                compact = compact[len(prefix):].strip()

        # 번호가 붙은 대상별 상세조건 시작 전까지만 사용.
        detail_match = group_start_pattern.search(compact)
        if detail_match:
            compact = compact[:detail_match.start()].strip()

        # 정의/예외/유의사항이 이어지는 경우 가장 먼저 등장하는
        # 위치에서 잘라 핵심 자격 한 문단만 유지한다.
        stop_positions = [
            pos
            for keyword in summary_stop_keywords
            if (pos := compact.find(keyword)) > 0
        ]
        if stop_positions:
            compact = compact[:min(stop_positions)].strip()

        # 동일 공고에서 실제로 자주 나타나는 형태:
        #   "... 소득 및 자산기준을 충족하는, 무주택세대구성원 : ..."
        # 쉼표 뒤 정의가 붙는 경우 정의를 버린다.
        compact = re.sub(
            r"[,，]\s*(?=무주택(?:세대구성원|자)|세대구성원\s*:)",
            "",
            compact,
            count=1,
        ).strip()

        compact = re.sub(r"[,，;；]\s*$", "", compact).strip()

        if not compact:
            continue

        score = 0
        if normalized_title in {"입주자격", "신청자격"}:
            score += 100
        elif (
            normalized_title.endswith("입주자격")
            or normalized_title.endswith("신청자격")
        ):
            score += 80
        else:
            score += 60

        if _contains_keyword(
            compact,
            (
                "무주택",
                "미혼 청년",
                "신혼·신생아",
                "자동차",
                "소득",
                "자산",
            ),
        ):
            score += 20

        # 지나치게 긴 일반 설명은 우선순위를 낮춘다.
        if len(compact) > 350:
            score -= 30

        candidate = (score, _compact_summary(compact, 350))
        if best is None or candidate[0] > best[0]:
            best = candidate

    return best[1] if best is not None else ""


def _eligibility_type_group_code(
    label: str,
) -> str:
    normalized = (
        _normalized_match_text(
            label
        )
    )

    if (
        "예비신혼부부"
        in normalized
    ):
        return "prospective_newlywed"

    if (
        "지원대상한부모가족"
        in normalized
    ):
        return "supported_single_parent"

    if (
        "한부모가족"
        in normalized
    ):
        return "single_parent_family"

    if (
        "유자녀혼인가구"
        in normalized
    ):
        return "married_with_children"

    if (
        "신생아가구"
        in normalized
    ):
        return "newborn_family"

    if (
        normalized == "혼인가구"
        or "혼인가구" in normalized
    ):
        return "married_household"

    if (
        "신혼부부"
        in normalized
    ):
        return "newlywed"

    if (
        "취업준비생"
        in normalized
    ):
        return "job_seeker"

    if (
        "대학생"
        in normalized
        or "대학원생"
        in normalized
    ):
        return "college_student"

    if "청년" in normalized:
        return "youth"

    return (
        _eligibility_group_code(
            label
        )
    )


def _extract_eligibility_type_groups_from_structure(
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    실제 '입주자격/신청자격' 영역 안에서만 대상별 상세조건을
    target_groups로 구조화한다.

    문서 전체 키워드 검색은 하지 않는다. 따라서 다른 표/유의사항의
    '고령자', '청년' 같은 단어가 현재 공고의 대상 계층으로 잘못
    들어오는 것을 방지한다.
    """
    target_section: dict[str, Any] | None = None
    best_score = -1

    for section, _ in _iter_sections(structure.get("sections")):
        title = _clean_text(
            section.get("title")
            or section.get("normalized_title")
        )
        normalized = _normalized_match_text(title)

        if any(
            excluded in normalized
            for excluded in (
                "입주자격확인서류",
                "자격확인서류",
                "자격요건확인구비서류",
                "제출서류",
                "확인서류",
            )
        ):
            continue

        score = 0
        if normalized in {"입주자격", "신청자격"}:
            score = 100
        elif (
            normalized.endswith("입주자격")
            or normalized.endswith("신청자격")
        ):
            score = 80

        if score > best_score:
            best_score = score
            target_section = section

    if target_section is None or best_score <= 0:
        return []

    # 해당 자격 Section과 그 자식 Section만 범위로 사용한다.
    # 구조화 과정에서 ① 신혼부부, ② 예비신혼부부 등이 자식
    # Section으로 분리되는 경우가 있으므로 direct text만 보지 않는다.
    scoped_parts: list[str] = []
    root_text = _section_direct_text(target_section)
    if root_text:
        scoped_parts.append(root_text)

    for child, _ in _iter_sections(target_section.get("children")):
        child_text = _section_direct_text(child)
        if child_text:
            scoped_parts.append(child_text)

    section_text = re.sub(
        r"\s+",
        " ",
        _clean_text("\n".join(_deduplicate_texts(scoped_parts))),
    ).strip()

    if not section_text:
        return []

    # 긴 표현부터 배치한다.
    label_patterns: tuple[tuple[str, str], ...] = (
        ("supported_single_parent", r"지원대상\s*한부모가족"),
        ("prospective_newlywed", r"예비\s*신혼부부"),
        ("married_with_children", r"유자녀\s*혼인가구"),
        ("newborn_family", r"신생아\s*가구"),
        ("single_parent_family", r"한부모가족"),
        ("newlywed", r"신혼부부"),
        ("married_household", r"혼인가구"),
        ("job_seeker", r"취업준비생"),
        ("college_student", r"대학원생|대학생"),
        ("youth", r"청년"),
        ("elderly", r"고령자"),
    )

    label_regex = (
        "(?:"
        + "|".join(
            f"(?P<{code}>{pattern})"
            for code, pattern in label_patterns
        )
        + ")"
    )

    # ① 신혼부부 / 3-1 한부모가족 / 1. 청년 등 명시적
    # 번호가 붙은 대상 시작점만 1차로 인정한다.
    start_pattern = re.compile(
        r"(?P<marker>(?:[①②③④⑤⑥⑦⑧⑨⑩](?:-\d+)?|\d+(?:-\d+)?[.)]?))\s*"
        + label_regex
        + r"\s*[:：]?\s*",
        re.IGNORECASE,
    )

    matches = list(start_pattern.finditer(section_text))

    groups: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    def _append_group(
        *,
        code: str,
        label: str,
        detail: str,
    ) -> None:
        detail = _clean_text(detail)

        # 다음 공통 설명/표 제목을 현재 계층 상세로 먹지 않는다.
        stop_keywords = (
            "※ 무주택세대구성원",
            "무주택세대구성원 :",
            "무주택세대구성원:",
            "입주순위",
            "소득 · 자산 기준",
            "소득·자산 기준",
            "소득 및 자산 기준",
            "선정기준",
            "제출서류",
            "자격요건 확인",
            "공고내용을 반드시 숙지",
        )
        positions = [
            pos
            for keyword in stop_keywords
            if (pos := detail.find(keyword)) >= 0
        ]
        if positions:
            detail = detail[:min(positions)].strip()

        detail = re.sub(r"\s+", " ", detail).strip(" ,;·")
        if not detail or code in seen_codes:
            return

        seen_codes.add(code)
        groups.append(
            {
                "code": code,
                "label": re.sub(r"\s+", " ", label).strip(),
                "details": [_compact_summary(detail, 500)],
            }
        )

    if matches:
        for index, match in enumerate(matches):
            code = ""
            label = ""
            for candidate_code, _ in label_patterns:
                value = match.group(candidate_code)
                if value:
                    code = candidate_code
                    label = value
                    break

            if not code or not label:
                continue

            start_index = match.end()
            end_index = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(section_text)
            )
            _append_group(
                code=code,
                label=label,
                detail=section_text[start_index:end_index],
            )

    # 번호가 파싱에서 사라지고 각 대상이 자식 Section 제목으로만
    # 남은 경우를 보완한다. 이때도 target_section의 자식만 본다.
    if len(groups) < 2:
        for child, _ in _iter_sections(target_section.get("children")):
            title = _clean_text(
                child.get("title")
                or child.get("normalized_title")
            )
            normalized_title = _normalized_match_text(title)
            if not normalized_title:
                continue

            matched_code = ""
            matched_label = ""
            for code, pattern in label_patterns:
                label_match = re.search(pattern, title, re.IGNORECASE)
                if label_match:
                    # 자격 영역의 짧은 제목 또는 번호가 붙은 제목만 허용.
                    # 일반 문장 속 단순 언급은 대상 그룹으로 보지 않는다.
                    stripped_title = re.sub(
                        r"^[①②③④⑤⑥⑦⑧⑨⑩\d\-.)\s]+",
                        "",
                        title,
                    ).strip()
                    if (
                        len(stripped_title) <= 40
                        and _normalized_match_text(label_match.group(0))
                        in _normalized_match_text(stripped_title)
                    ):
                        matched_code = code
                        matched_label = label_match.group(0)
                        break

            if not matched_code or matched_code in seen_codes:
                continue

            child_text = _section_direct_text(child)
            detail = child_text
            if detail.startswith(title):
                detail = detail[len(title):].strip()

            _append_group(
                code=matched_code,
                label=matched_label,
                detail=detail,
            )

    return groups



def _extract_common_eligibility_conditions(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    lines = (
        _eligibility_search_lines(
            matches
        )
    )

    result: list[str] = []

    no_home_keywords = (
        "무주택세대구성원",
        "무주택 세대구성원",
        "무주택자",
        "무주택자인",
        "무주택자로서",
    )

    if any(
        _contains_keyword(
            line,
            no_home_keywords,
        )
        for line in lines
    ):
        result.append("무주택자")

    return result


def _build_eligibility_summary(
    matches: list[
        dict[str, Any]
    ],
) -> str:
    """
    신청자격 카드에 표시할 대표 문장을 원문에서 선택한다.

    중요:
    - 새 문장을 조립하지 않는다.
    - "실제 모집하는 공급계층은 ..." 같은 고정 문구를 생성하지 않는다.
    - eligibility 후보 Section에 실제 존재하는 원문 한 줄을 점수화한다.
    """
    best: tuple[
        int,
        int,
        str,
    ] | None = None

    target_keywords = (
        "대학생",
        "취업준비생",
        "청년",
        "사회초년생",
        "신혼부부",
        "예비신혼부부",
        "한부모가족",
        "고령자",
        "주거급여수급자",
    )

    qualification_keywords = (
        "무주택",
        "신청자격",
        "입주자격",
        "자격요건",
        "공급대상",
        "신청대상",
        "모집공고일 현재",
        "입주자모집공고일 현재",
        "모두 갖춘 자",
    )

    negative_keywords = (
        "확인하시기 바랍니다",
        "자세한 내용",
        "참고자료",
        "이해를 돕기 위한",
        "자격 해당여부는",
        "서류제출",
        "제출서류",
        "신청방법",
        "문의",
        "페이지",
    )

    for index, line in enumerate(
        _summary_lines(matches)
    ):
        cleaned = re.sub(
            r"^\s*[•▪■※◆●*-]+\s*",
            "",
            line,
        ).strip()

        if not cleaned:
            continue

        normalized = (
            _normalized_match_text(
                cleaned
            )
        )

        target_count = sum(
            1
            for keyword
            in target_keywords
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            )
        )

        qualification_count = (
            sum(
                1
                for keyword
                in qualification_keywords
                if (
                    _normalized_match_text(
                        keyword
                    )
                    in normalized
                )
            )
        )

        # 아무 자격/대상 문맥도 없는 줄은 카드 대표문장에서 제외한다.
        if (
            target_count == 0
            and qualification_count == 0
        ):
            continue

        score = 0

        # 실제 공급계층이 여러 개 포함된 원문을 강하게 우선한다.
        score += (
            target_count * 25
        )

        # 자격/무주택/공고일 문맥을 우선한다.
        score += (
            qualification_count * 15
        )

        positive_weights = {
            "모집공고일 현재": 35,
            "입주자모집공고일 현재": 35,
            "무주택세대구성원": 35,
            "무주택자로서": 30,
            "무주택자": 20,
            "아래의 요건": 25,
            "모두 갖춘 자": 30,
            "신청자격": 15,
            "입주자격": 15,
            "자격요건": 15,
            "공급대상": 15,
        }

        for (
            keyword,
            weight,
        ) in (
            positive_weights.items()
        ):
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score += weight

        for keyword in (
            negative_keywords
        ):
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score -= 40

        # 단독 제목보다는 실제 서술 문장을 선호한다.
        if len(cleaned) < 15:
            score -= 25

        # 지나치게 긴 안내문은 대표문장 후보에서 감점한다.
        if len(cleaned) > 350:
            score -= 25

        candidate = (
            score,
            -index,
            _compact_summary(
                cleaned,
                250,
            ),
        )

        if (
            best is None
            or candidate[:2]
            > best[:2]
        ):
            best = candidate

    if (
        best is None
        or best[0] <= 0
    ):
        return ""

    return best[2]


def _build_supply_summary(
    matches: list[
        dict[str, Any]
    ],
) -> str:
    best: tuple[
        int,
        int,
        str,
    ] | None = None

    for index, line in enumerate(
        _summary_lines(matches)
    ):
        cleaned = re.sub(
            r"^\s*[•▪■※*-]+\s*",
            "",
            line,
        ).strip()

        normalized = (
            _normalized_match_text(
                cleaned
            )
        )

        data_keywords = (
            "세대",
            "호수",
            "주택형",
            "전용면적",
            "공급면적",
        )

        data_count = sum(
            1
            for keyword
            in data_keywords
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            )
        )

        if data_count == 0:
            continue

        if any(
            _normalized_match_text(
                keyword
            )
            in normalized
            for keyword in (
                "입주자격",
                "신청자격",
                "선정이 불가",
            )
        ):
            continue

        if (
            len(cleaned) < 12
            or not re.search(
                r"\d",
                cleaned,
            )
        ):
            continue

        score = data_count * 25

        # 공급 정보 요약은 "어떤 주택을 몇 호 공급하는지"를 우선한다.
        # 임대보증금/월임대료/전환이율 문장은 별도 rental_condition_summary로
        # 보존되므로 카드의 공급 내용 요약 후보에서는 제외한다.
        if (
            any(
                _normalized_match_text(keyword) in normalized
                for keyword in (
                    "임대보증금",
                    "월임대료",
                    "전환이율",
                    "상호전환",
                )
            )
            and not any(
                _normalized_match_text(keyword) in normalized
                for keyword in (
                    "공급대상",
                    "공급호수",
                    "모집호수",
                    "주택형",
                    "전용면적",
                )
            )
        ):
            continue

        for (
            keyword,
            weight,
        ) in {
            "공급대상": 40,
            "모집호수": 45,
            "공급호수": 45,
            "건설호수": 40,
            "주택호수": 40,
            "예비입주자": 15,
        }.items():
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score += weight

        for (
            keyword,
            weight,
        ) in {
            "입주자격": 40,
            "신청자격": 40,
            "새로 계약": 30,
            "최대 거주기간": 25,
            "제출서류": 40,
            "면제": 50,
            "변경이 불가": 50,
            "감액": 30,
            "증액": 30,
            "용도로만 쓰이는": 50,
            "공용면적": 40,
            "불법양도": 60,
            "전대자": 60,
            "선정이 불가": 50,
            "신청자의 세대구성원": 40,
        }.items():
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score -= weight

        if score <= 0:
            continue

        candidate = (
            score,
            -index,
            _compact_summary(
                cleaned,
                220,
            ),
        )

        if (
            best is None
            or candidate[:2]
            > best[:2]
        ):
            best = candidate

    return (
        best[2]
        if best is not None
        else ""
    )


def _build_income_asset_summary(
    matches: list[
        dict[str, Any]
    ],
) -> str:
    best: tuple[
        int,
        int,
        str,
    ] | None = None

    for index, line in enumerate(
        _summary_lines(matches)
    ):
        cleaned = re.sub(
            r"^\s*[•▪■※*-]+\s*",
            "",
            line,
        ).strip()

        cleaned = re.sub(
            r"^\s*\d+[.)]?\s*",
            "",
            cleaned,
        ).strip()

        cleaned = re.sub(
            r"\[(?:완화조건|배제조건)\]\s*",
            "",
            cleaned,
        ).strip()

        normalized = (
            _normalized_match_text(
                cleaned
            )
        )

        has_income = (
            _normalized_match_text(
                "소득"
            )
            in normalized
        )
        has_asset = any(
            _normalized_match_text(
                keyword
            )
            in normalized
            for keyword in (
                "자산",
                "총자산",
                "자동차",
            )
        )

        if (
            not has_income
            and not has_asset
        ):
            continue

        score = 0

        positive_weights = {
            "소득기준": 25,
            "자산기준": 25,
            "총자산": 25,
            "자동차가액": 25,
            "이하": 15,
            "초과": 15,
            "배제": 20,
            "관계없이": 20,
            "소유하고 있지 않을 것": 25,
        }
        negative_weights = {
            "참고자료": 40,
            "확인하시기 바랍니다": 30,
            "자세한 내용": 20,
        }

        for (
            keyword,
            weight,
        ) in positive_weights.items():
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score += weight

        for (
            keyword,
            weight,
        ) in negative_weights.items():
            if (
                _normalized_match_text(
                    keyword
                )
                in normalized
            ):
                score -= weight

        candidate = (
            score,
            -index,
            _compact_summary(
                cleaned,
                220,
            ),
        )

        if (
            best is None
            or candidate[:2]
            > best[:2]
        ):
            best = candidate

    return (
        best[2]
        if best is not None
        else ""
    )


def _extract_document_items(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    text = _normalized_match_text(
        "\n".join(
            match.get(
                "text",
                "",
            )
            for match in matches[:8]
        )
    )

    rules = (
        (
            "\uC8FC\uBBFC\uB4F1\uB85D\uD45C\uB4F1\uBCF8",
            "\uC8FC\uBBFC\uB4F1\uB85D\uB4F1\uBCF8",
        ),
        (
            "\uC8FC\uBBFC\uB4F1\uB85D\uB4F1\uBCF8",
            "\uC8FC\uBBFC\uB4F1\uB85D\uB4F1\uBCF8",
        ),
        (
            "\uC8FC\uBBFC\uB4F1\uB85D\uD45C\uCD08\uBCF8",
            "\uC8FC\uBBFC\uB4F1\uB85D\uCD08\uBCF8",
        ),
        (
            "\uAC00\uC871\uAD00\uACC4\uC99D\uBA85\uC11C",
            "\uAC00\uC871\uAD00\uACC4\uC99D\uBA85\uC11C",
        ),
        (
            "\uC2E0\uBD84\uC99D",
            "\uC2E0\uBD84\uC99D",
        ),
        (
            "\uC778\uAC10\uC99D\uBA85\uC11C",
            "\uC778\uAC10\uC99D\uBA85\uC11C",
        ),
    )

    result: list[str] = []

    for (
        keyword,
        display,
    ) in rules:
        if (
            _normalized_match_text(
                keyword
            )
            in text
            and display
            not in result
        ):
            result.append(display)

    return result[:6]


def _collect_phone_numbers(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()

    for match in matches:
        section = match[
            "_section"
        ]

        for entity in (
            _collect_entities(
                section,
                entity_type="phone",
            )
        ):
            value = (
                _clean_text(
                    entity.get(
                        "normalized_value"
                    )
                )
                or _clean_text(
                    entity.get("raw")
                )
            )

            if (
                value
                and value not in seen
            ):
                seen.add(value)
                phones.append(value)

    phone_pattern = re.compile(
        r"(?<!\d)"
        r"(?:0\d{1,2}[-\s]?"
        r"\d{3,4}[-\s]?\d{4}|"
        r"1\d{3}[-\s]?\d{4})"
        r"(?!\d)"
    )

    for match in matches:
        for value in (
            phone_pattern.findall(
                match["text"]
            )
        ):
            normalized = re.sub(
                r"\s+",
                "",
                value,
            )

            if normalized not in seen:
                seen.add(normalized)
                phones.append(
                    normalized
                )

    return phones


# ============================================================
# 핵심값 단위 추출 보조 함수
# ============================================================
def _extract_structured_key_values(
    section: dict[str, Any],
) -> list[dict[str, str]]:
    result: list[
        dict[str, str]
    ] = []
    seen: set[
        tuple[str, str]
    ] = set()

    for node in _iter_nested_dicts(
        section
    ):
        key_values = node.get(
            "key_values"
        )

        if isinstance(
            key_values,
            list,
        ):
            for item in key_values:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                key = _clean_text(
                    item.get("key")
                    or item.get(
                        "label"
                    )
                    or item.get(
                        "header"
                    )
                )
                value = _clean_text(
                    item.get("value")
                    or item.get(
                        "text"
                    )
                )

                if (
                    not key
                    and not value
                ):
                    continue

                pair = (
                    key,
                    value,
                )

                if pair in seen:
                    continue

                seen.add(pair)

                result.append(
                    {
                        "key": key,
                        "value": value,
                    }
                )

        key = _clean_text(
            node.get("key")
        )
        value = node.get("value")

        if (
            key
            and isinstance(
                value,
                (
                    str,
                    int,
                    float,
                ),
            )
        ):
            value_text = _clean_text(
                value
            )
            pair = (
                key,
                value_text,
            )

            if pair not in seen:
                seen.add(pair)

                result.append(
                    {
                        "key": key,
                        "value": (
                            value_text
                        ),
                    }
                )

    return result


def _extract_relevant_snippets(
    text: str,
    keywords: Iterable[str],
    *,
    max_items: int = 12,
    max_length: int = 500,
) -> list[str]:
    if not text:
        return []

    parts = re.split(
        r"(?:\n+|[•■※◆●]+)",
        text,
    )

    result: list[str] = []

    for part in parts:
        cleaned = _clean_text(part)

        if not cleaned:
            continue

        if not _contains_keyword(
            cleaned,
            keywords,
        ):
            continue

        if (
            len(cleaned)
            > max_length
        ):
            sentences = re.split(
                r"(?<=[.!?。])\s+"
                r"|(?<=다\.)\s*",
                cleaned,
            )

            selected = [
                _clean_text(
                    sentence
                )
                for sentence
                in sentences
                if (
                    _clean_text(
                        sentence
                    )
                    and _contains_keyword(
                        sentence,
                        keywords,
                    )
                )
            ]

            result.extend(
                selected
            )
        else:
            result.append(cleaned)

    return (
        _deduplicate_texts(
            result
        )[:max_items]
    )


def _key_value_matches_for_field(
    matches: list[
        dict[str, Any]
    ],
    field: str,
) -> list[dict[str, str]]:
    keywords = FIELD_RULES[
        field
    ]["keywords"]

    result: list[
        dict[str, str]
    ] = []
    seen: set[
        tuple[str, str]
    ] = set()

    for match in matches:
        section = match[
            "_section"
        ]

        for item in (
            _extract_structured_key_values(
                section
            )
        ):
            key = item["key"]
            value = item["value"]

            if not key:
                continue

            if not _contains_keyword(
                key,
                keywords,
            ):
                continue

            pair = (
                key,
                value,
            )

            if pair in seen:
                continue

            seen.add(pair)
            result.append(item)

    return result


# ============================================================
# 날짜 정규화
# ============================================================
_YEARLESS_DATE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?P<month>\d{1,2})"
    r"\s*(?:[./]|월)\s*"
    r"(?P<day>\d{1,2})"
    r"\s*(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]{1,3}\))?"
)

_YEARLESS_DATE_RANGE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?P<start_month>\d{1,2})"
    r"\s*(?:[./]|월)\s*"
    r"(?P<start_day>\d{1,2})"
    r"\s*(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]{1,3}\))?"
    r"\s*(?:~|∼|～|–|—|부터)\s*"
    r"(?P<end_month>\d{1,2})"
    r"\s*(?:[./]|월)\s*"
    r"(?P<end_day>\d{1,2})"
    r"\s*(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]{1,3}\))?"
)


_DATE_WITH_TIME_PATTERN = re.compile(
    r"[‘’']?"
    r"(?P<year>\d{2,4})[.\-/년]\s*"
    r"(?P<month>\d{1,2})[.\-/월]\s*"
    r"(?P<day>\d{1,2})(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]*\))?"
    r"\s*"
    r"(?:(?P<ampm>오전|오후)\s*)?"
    r"(?P<hour>\d{1,2})?"
    r"(?::|시)?\s*"
    r"(?P<minute>\d{1,2})?"
    r"(?:분)?"
)


_DATE_RANGE_PATTERN = re.compile(
    r"[‘’']?"
    r"(?P<start_year>\d{2,4})"
    r"(?:[.\-/]|년)\s*"
    r"(?P<start_month>\d{1,2})"
    r"(?:[.\-/]|월)\s*"
    r"(?P<start_day>\d{1,2})"
    r"(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]*\))?"
    r"\s*"
    r"(?:(?P<start_ampm>오전|오후)\s*)?"
    r"(?P<start_hour>\d{1,2})?"
    r"(?::|시)?\s*"
    r"(?P<start_minute>\d{1,2})?"
    r"(?:분)?"
    r"\s*(?:~|∼|～|부터)\s*"
    r"[‘’']?"
    r"(?:(?P<end_year>\d{2,4})"
    r"(?:[.\-/]|년)\s*)?"
    r"(?P<end_month>\d{1,2})"
    r"(?:[.\-/]|월)\s*"
    r"(?P<end_day>\d{1,2})"
    r"(?:일)?"
    r"\s*\.?"
    r"(?:\s*\([^)]*\))?"
    r"\s*"
    r"(?:(?P<end_ampm>오전|오후)\s*)?"
    r"(?P<end_hour>\d{1,2})?"
    r"(?::|시)?\s*"
    r"(?P<end_minute>\d{1,2})?"
    r"(?:분)?"
    r"\s*(?:까지)?"
)


def _normalize_year_value(
    value: str | int,
) -> int:
    year = int(value)

    if year < 100:
        year += 2000

    return year


def _normalize_time_parts(
    ampm: str | None,
    hour_raw: str | None,
    minute_raw: str | None,
) -> str | None:
    if not hour_raw:
        return None

    hour = int(hour_raw)
    minute = int(
        minute_raw or 0
    )

    if (
        ampm == "오후"
        and hour < 12
    ):
        hour += 12
    elif (
        ampm == "오전"
        and hour == 12
    ):
        hour = 0

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return None

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def _format_date_time(
    *,
    year: int,
    month: int,
    day: int,
    time_value: str | None,
) -> str:
    # 핵심정보 카드에는 시간대를 노출하지 않고 날짜만 저장한다.
    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def _normalize_date_match(
    match: re.Match[str],
) -> str:
    year = _normalize_year_value(
        match.group("year")
    )
    month = int(
        match.group("month")
    )
    day = int(
        match.group("day")
    )

    time_value = (
        _normalize_time_parts(
            match.group("ampm"),
            match.group("hour"),
            match.group("minute"),
        )
    )

    return _format_date_time(
        year=year,
        month=month,
        day=day,
        time_value=time_value,
    )


def _normalize_date_range_match(
    match: re.Match[str],
) -> tuple[str, str]:
    start_year = (
        _normalize_year_value(
            match.group(
                "start_year"
            )
        )
    )
    start_month = int(
        match.group(
            "start_month"
        )
    )
    start_day = int(
        match.group(
            "start_day"
        )
    )

    end_year_raw = match.group(
        "end_year"
    )

    if end_year_raw:
        end_year = (
            _normalize_year_value(
                end_year_raw
            )
        )
    else:
        end_year = start_year

    end_month = int(
        match.group(
            "end_month"
        )
    )
    end_day = int(
        match.group(
            "end_day"
        )
    )

    if (
        not end_year_raw
        and (
            end_month,
            end_day,
        )
        < (
            start_month,
            start_day,
        )
    ):
        end_year += 1

    start_time = (
        _normalize_time_parts(
            match.group(
                "start_ampm"
            ),
            match.group(
                "start_hour"
            ),
            match.group(
                "start_minute"
            ),
        )
    )

    end_time = (
        _normalize_time_parts(
            match.group(
                "end_ampm"
            ),
            match.group(
                "end_hour"
            ),
            match.group(
                "end_minute"
            ),
        )
    )

    start = _format_date_time(
        year=start_year,
        month=start_month,
        day=start_day,
        time_value=start_time,
    )
    end = _format_date_time(
        year=end_year,
        month=end_month,
        day=end_day,
        time_value=end_time,
    )

    return start, end


def _normalize_yearless_date(
    *,
    month: int,
    day: int,
    reference_year: int,
) -> str:
    if not 1 <= month <= 12:
        raise ValueError(
            f"잘못된 month: {month}"
        )

    if not 1 <= day <= 31:
        raise ValueError(
            f"잘못된 day: {day}"
        )

    return (
        f"{reference_year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def _normalize_yearless_date_range_match(
    match: re.Match[str],
    *,
    reference_year: int,
) -> tuple[str, str]:
    start_month = int(
        match.group(
            "start_month"
        )
    )
    start_day = int(
        match.group(
            "start_day"
        )
    )

    end_month = int(
        match.group(
            "end_month"
        )
    )
    end_day = int(
        match.group(
            "end_day"
        )
    )

    start_year = reference_year
    end_year = reference_year

    if (
        (end_month, end_day)
        < (start_month, start_day)
    ):
        end_year += 1

    start = _normalize_yearless_date(
        month=start_month,
        day=start_day,
        reference_year=start_year,
    )
    end = _normalize_yearless_date(
        month=end_month,
        day=end_day,
        reference_year=end_year,
    )

    return start, end


def _normalize_yearless_single_date(
    value: str,
    *,
    reference_year: int | None,
) -> str | None:
    if reference_year is None:
        return None

    match = _YEARLESS_DATE_PATTERN.search(
        _clean_text(value)
    )

    if not match:
        return None

    try:
        return _normalize_yearless_date(
            month=int(
                match.group("month")
            ),
            day=int(
                match.group("day")
            ),
            reference_year=reference_year,
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _keyword_positions(
    text: str,
    keywords: Iterable[str],
) -> list[int]:
    normalized = text.lower()
    result: list[int] = []

    for keyword in keywords:
        needle = _clean_text(
            keyword
        ).lower()

        if not needle:
            continue

        start = 0

        while True:
            index = normalized.find(
                needle,
                start,
            )

            if index < 0:
                break

            result.append(index)
            start = (
                index
                + len(needle)
            )

    return sorted(set(result))


def _distance_to_nearest_keyword(
    position: int,
    keyword_positions: list[int],
) -> int:
    if not keyword_positions:
        return 10**9

    return min(
        abs(
            position
            - keyword_position
        )
        for keyword_position
        in keyword_positions
    )


def _extract_reference_year(
    structure: dict[str, Any],
    context: dict[str, Any],
) -> int | None:
    announcement_date = _clean_text(
        context.get(
            "announcement_date"
        )
    )

    context_match = re.match(
        r"(?P<year>20\d{2})",
        announcement_date,
    )

    if context_match:
        return int(
            context_match.group(
                "year"
            )
        )

    structure_text = json.dumps(
        structure,
        ensure_ascii=False,
    )

    announcement_match = re.search(
        r"(?:입주자\s*모집공고일|모집공고일|공고일)"
        r".{0,50}?"
        r"(?P<year>20\d{2})"
        r"\s*(?:[./]|년)",
        structure_text,
    )

    if announcement_match:
        return int(
            announcement_match.group(
                "year"
            )
        )

    return None


def _collect_application_search_texts(
    matches: list[
        dict[str, Any]
    ],
) -> list[str]:
    """
    application_period 후보 Section과 하위 Section을 함께 탐색한다.
    """
    result: list[str] = []
    seen: set[str] = set()

    def add_text(
        value: str,
    ) -> None:
        cleaned = _clean_text(
            value
        )

        if not cleaned:
            return

        normalized = re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip()

        if normalized in seen:
            return

        seen.add(normalized)
        result.append(cleaned)

    for match in matches:
        add_text(
            _clean_text(
                match.get("text")
            )
        )

        section = match.get(
            "_section"
        )

        if not isinstance(
            section,
            dict,
        ):
            continue

        for child, _ in (
            _iter_sections(
                section.get(
                    "children"
                )
            )
        ):
            add_text(
                _section_direct_text(
                    child
                )
            )

    return result


def _extract_application_period_values(
    matches: list[
        dict[str, Any]
    ],
    *,
    reference_year: int | None = None,
) -> tuple[
    str | None,
    str | None,
    list[dict[str, Any]],
]:
    """
    신청/접수 문맥에서 실제 신청기간을 추출한다.

    우선순위:
    1. 날짜 범위
    2. 개별 날짜 1~2개
    3. 하위 Section/Table까지 탐색
    """
    positive_keywords = tuple(
        dict.fromkeys(
            (
                *FIELD_RULES[
                    "application_period"
                ]["keywords"],
                "모집일정",
                "모집 일정",
                "접수시작",
                "접수 시작",
                "접수마감",
                "접수 마감",
                "신청시작",
                "신청 시작",
                "신청마감",
                "신청 마감",
                "청약접수",
                "청약 접수",
                "신청접수",
                "신청 접수",
                "신청접수일",
                "신청 접수일",
                "인터넷신청",
                "인터넷 신청",
            )
        )
    )

    search_texts = (
        _collect_application_search_texts(
            matches
        )
    )

    range_candidates: list[
        dict[str, Any]
    ] = []

    for (
        text_index,
        text_value,
    ) in enumerate(search_texts):
        keyword_positions = (
            _keyword_positions(
                text_value,
                positive_keywords,
            )
        )

        for range_match in (
            _DATE_RANGE_PATTERN.finditer(
                text_value
            )
        ):
            try:
                start, end = (
                    _normalize_date_range_match(
                        range_match
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            distance = (
                _distance_to_nearest_keyword(
                    range_match.start(),
                    keyword_positions,
                )
            )

            left = max(
                0,
                range_match.start()
                - 180,
            )
            right = min(
                len(text_value),
                range_match.end()
                + 180,
            )

            context = _clean_text(
                text_value[
                    left:right
                ]
            )

            context_has_keyword = (
                _contains_keyword(
                    context,
                    positive_keywords,
                )
            )

            if (
                distance > 500
                and not context_has_keyword
            ):
                continue

            range_candidates.append(
                {
                    "start": start,
                    "end": end,
                    "raw": (
                        _clean_text(
                            range_match.group(
                                0
                            )
                        )
                    ),
                    "context": context,
                    "distance": (
                        distance
                    ),
                    "text_index": (
                        text_index
                    ),
                }
            )

    if (
        not range_candidates
        and reference_year is not None
    ):
        for (
            text_index,
            text_value,
        ) in enumerate(search_texts):
            keyword_positions = (
                _keyword_positions(
                    text_value,
                    positive_keywords,
                )
            )

            for range_match in (
                _YEARLESS_DATE_RANGE_PATTERN.finditer(
                    text_value
                )
            ):
                distance = (
                    _distance_to_nearest_keyword(
                        range_match.start(),
                        keyword_positions,
                    )
                )

                left = max(
                    0,
                    range_match.start()
                    - 180,
                )
                right = min(
                    len(text_value),
                    range_match.end()
                    + 180,
                )

                range_context = _clean_text(
                    text_value[
                        left:right
                    ]
                )

                context_has_keyword = (
                    _contains_keyword(
                        range_context,
                        positive_keywords,
                    )
                )

                if (
                    distance > 500
                    and not context_has_keyword
                ):
                    continue

                try:
                    start, end = (
                        _normalize_yearless_date_range_match(
                            range_match,
                            reference_year=reference_year,
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                range_candidates.append(
                    {
                        "start": start,
                        "end": end,
                        "raw": _clean_text(
                            range_match.group(
                                0
                            )
                        ),
                        "context": (
                            range_context
                        ),
                        "distance": (
                            distance
                        ),
                        "text_index": (
                            text_index
                        ),
                    }
                )

    if range_candidates:
        range_candidates.sort(
            key=lambda item: (
                item["distance"],
                item[
                    "text_index"
                ],
                item["start"],
                item["end"],
            )
        )

        selected = (
            range_candidates[0]
        )

        return (
            selected["start"],
            selected["end"],
            [
                {
                    "raw": (
                        selected["raw"]
                    ),
                    "normalized_value": (
                        f"{selected['start']}"
                        " ~ "
                        f"{selected['end']}"
                    ),
                    "context": (
                        selected[
                            "context"
                        ]
                    ),
                }
            ],
        )

    date_candidates: list[
        dict[str, Any]
    ] = []

    for (
        text_index,
        text_value,
    ) in enumerate(search_texts):
        keyword_positions = (
            _keyword_positions(
                text_value,
                positive_keywords,
            )
        )

        for date_match in (
            _DATE_WITH_TIME_PATTERN.finditer(
                text_value
            )
        ):
            try:
                normalized = (
                    _normalize_date_match(
                        date_match
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            distance = (
                _distance_to_nearest_keyword(
                    date_match.start(),
                    keyword_positions,
                )
            )

            left = max(
                0,
                date_match.start()
                - 160,
            )
            right = min(
                len(text_value),
                date_match.end()
                + 160,
            )

            context = _clean_text(
                text_value[
                    left:right
                ]
            )

            context_has_keyword = (
                _contains_keyword(
                    context,
                    positive_keywords,
                )
            )

            if (
                distance > 500
                and not context_has_keyword
            ):
                continue

            date_candidates.append(
                {
                    "raw": (
                        _clean_text(
                            date_match.group(
                                0
                            )
                        )
                    ),
                    "normalized_value": (
                        normalized
                    ),
                    "context": context,
                    "distance": (
                        distance
                    ),
                    "text_index": (
                        text_index
                    ),
                }
            )

    date_candidates.sort(
        key=lambda item: (
            item["distance"],
            item["text_index"],
            item[
                "normalized_value"
            ],
        )
    )

    unique: list[
        dict[str, Any]
    ] = []
    seen: set[str] = set()

    for item in date_candidates:
        value = item[
            "normalized_value"
        ]

        if value in seen:
            continue

        seen.add(value)
        unique.append(item)

    if not unique:
        return None, None, []

    selected = unique[:2]
    selected.sort(
        key=lambda item: (
            item[
                "normalized_value"
            ]
        )
    )

    start = selected[0][
        "normalized_value"
    ]
    end = (
        selected[-1][
            "normalized_value"
        ]
        if len(selected) > 1
        else start
    )

    public_dates = [
        {
            "raw": item["raw"],
            "normalized_value": (
                item[
                    "normalized_value"
                ]
            ),
            "context": (
                item["context"]
            ),
        }
        for item in selected
    ]

    return (
        start,
        end,
        public_dates,
    )


# ============================================================
# Match 결과
# ============================================================
def _collect_field_matches(
    structure: dict[str, Any],
    field: str,
) -> list[
    dict[str, Any]
]:
    candidates: list[
        dict[str, Any]
    ] = []

    for (
        section,
        section_path,
    ) in _iter_sections(
        structure.get("sections")
    ):
        score = (
            _score_section_for_field(
                section,
                field,
            )
        )

        if score <= 0:
            continue

        category, topic, confidence = (
            _domain_info(section)
        )

        text = _section_direct_text(
            section
        )

        if not text:
            continue

        candidates.append(
            {
                "section_id": (
                    section.get(
                        "section_id"
                    )
                ),
                "title": _clean_text(
                    section.get("title")
                    or section.get(
                        "normalized_title"
                    )
                ),
                "section_path": [
                    value
                    for value
                    in section_path
                    if value
                ],
                "domain": {
                    "category": (
                        category
                        or None
                    ),
                    "topic": (
                        topic
                        or None
                    ),
                    "confidence": (
                        confidence
                    ),
                },
                "score": score,
                "text": text,
                "_section": section,
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(
                item["score"]
            ),
        )
    )

    return candidates


def _public_sources(
    matches: list[
        dict[str, Any]
    ],
    *,
    limit: int = 8,
) -> list[
    dict[str, Any]
]:
    result: list[
        dict[str, Any]
    ] = []

    for match in matches[:limit]:
        result.append(
            {
                "section_id": (
                    match[
                        "section_id"
                    ]
                ),
                "title": (
                    match["title"]
                ),
                "section_path": (
                    match[
                        "section_path"
                    ]
                ),
                "domain": (
                    match["domain"]
                ),
                "score": (
                    match["score"]
                ),
            }
        )

    return result


def _build_generic_field(
    field: str,
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    if not matches:
        return {
            "status": "not_found",
            "text": "",
            "key_values": [],
            "sources": [],
        }

    key_values = (
        _key_value_matches_for_field(
            matches,
            field,
        )
    )

    snippets: list[str] = []

    for match in matches[:5]:
        snippets.extend(
            _extract_relevant_snippets(
                match["text"],
                FIELD_RULES[
                    field
                ]["keywords"],
            )
        )

    snippets = _deduplicate_texts(
        snippets
    )

    text_value = "\n".join(
        snippets[:10]
    )

    if (
        not key_values
        and not text_value
    ):
        return {
            "status": "not_found",
            "text": "",
            "key_values": [],
            "sources": (
                _public_sources(
                    matches
                )
            ),
        }

    return {
        "status": "extracted",
        "text": text_value,
        "key_values": (
            key_values[:20]
        ),
        "sources": (
            _public_sources(
                matches
            )
        ),
    }


# ============================================================
# 최종 7개 필드 생성
# ============================================================
def _collect_structure_texts(
    structure: dict[str, Any],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for node in _iter_nested_dicts(
        structure
    ):
        for key in (
            "text",
            "search_text",
        ):
            value = node.get(key)

            if not isinstance(
                value,
                str,
            ):
                continue

            cleaned = _clean_text(
                value
            )

            if not cleaned:
                continue

            normalized = (
                _normalized_match_text(
                    cleaned
                )
            )

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(cleaned)

    return result


def _extract_schedule_table_value(
    structure: dict[str, Any],
    *,
    target_keywords: tuple[str, ...],
    exclusion_keywords: tuple[str, ...] = (),
) -> str | None:
    for node in _iter_nested_dicts(
        structure
    ):
        cells = node.get("cells")

        if not isinstance(
            cells,
            list,
        ):
            continue

        headers: dict[
            int,
            str,
        ] = {}
        values: dict[
            int,
            str,
        ] = {}

        for cell in cells:
            if not isinstance(
                cell,
                dict,
            ):
                continue

            row = cell.get("row")
            col = cell.get("col")
            cell_text = _clean_text(
                cell.get("text")
            )

            if (
                not isinstance(row, int)
                or not isinstance(col, int)
                or not cell_text
            ):
                continue

            if row == 0:
                headers[col] = cell_text
            elif row == 1:
                values[col] = cell_text

        for col, header in (
            headers.items()
        ):
            if (
                exclusion_keywords
                and _contains_keyword(
                    header,
                    exclusion_keywords,
                )
            ):
                continue

            if not _contains_keyword(
                header,
                target_keywords,
            ):
                continue

            value = values.get(col)

            if value:
                return value

    return None


def _extract_application_period_from_schedule_table(
    structure: dict[str, Any],
    *,
    reference_year: int | None,
) -> tuple[
    str | None,
    str | None,
    list[dict[str, Any]],
]:
    if reference_year is None:
        return None, None, []

    raw_value = (
        _extract_schedule_table_value(
            structure,
            target_keywords=(
                "신청",
                "신청접수",
                "신청 접수",
                "청약접수",
                "청약 접수",
                "신청기간",
                "신청 기간",
                "접수기간",
                "접수 기간",
            ),
        )
    )

    if not raw_value:
        return None, None, []

    explicit_range = (
        _DATE_RANGE_PATTERN.search(
            raw_value
        )
    )

    if explicit_range:
        try:
            start, end = (
                _normalize_date_range_match(
                    explicit_range
                )
            )

            return (
                start,
                end,
                [
                    {
                        "raw": (
                            _clean_text(
                                raw_value
                            )
                        ),
                        "normalized_value": (
                            f"{start} ~ {end}"
                        ),
                        "context": (
                            "structured_schedule_table"
                        ),
                    }
                ],
            )
        except (
            TypeError,
            ValueError,
        ):
            pass

    yearless_range = (
        _YEARLESS_DATE_RANGE_PATTERN.search(
            raw_value
        )
    )

    if not yearless_range:
        return None, None, []

    try:
        start, end = (
            _normalize_yearless_date_range_match(
                yearless_range,
                reference_year=reference_year,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return None, None, []

    return (
        start,
        end,
        [
            {
                "raw": (
                    _clean_text(
                        raw_value
                    )
                ),
                "normalized_value": (
                    f"{start} ~ {end}"
                ),
                "context": (
                    "structured_schedule_table"
                ),
            }
        ],
    )


def _build_application_period(
    matches: list[
        dict[str, Any]
    ],
    *,
    structure: dict[str, Any] | None = None,
    reference_year: int | None = None,
) -> dict[str, Any]:
    result = _build_generic_field(
        "application_period",
        matches,
    )

    table_start = None
    table_end = None
    table_dates: list[
        dict[str, Any]
    ] = []

    if structure is not None:
        (
            table_start,
            table_end,
            table_dates,
        ) = (
            _extract_application_period_from_schedule_table(
                structure,
                reference_year=reference_year,
            )
        )

    if table_start and table_end:
        start = table_start
        end = table_end
        dates = table_dates
    else:
        start, end, dates = (
            _extract_application_period_values(
                matches,
                reference_year=reference_year,
            )
        )

    result.update(
        {
            "start": start,
            "end": end,
            "dates": dates,
            "summary": (
                f"{start} ~ {end}"
                if start and end
                else start
                or end
                or ""
            ),
        }
    )

    if start or end:
        result["status"] = (
            "extracted"
        )
    elif not result.get(
        "key_values"
    ):
        result["status"] = (
            "not_found"
        )

    return result



def _extract_eligibility_key_criteria(
    structure: dict[str, Any],
) -> dict[str, Any]:
    """
    신청자격/입주자격 관련 섹션에서 카드용 핵심 기준을 추출한다.

    예:
    - 소득 기준 적용 배제
    - 총자산 기준 적용 배제
    - 자동차가액 4,542만원 이하
    """
    candidate_texts: list[str] = []

    for section, _ in _iter_sections(
        structure.get("sections")
    ):
        title = _clean_text(
            section.get("title")
            or section.get(
                "normalized_title"
            )
        )

        normalized = (
            _normalized_match_text(
                title
            )
        )

        if not any(
            keyword in normalized
            for keyword in (
                "신청자격",
                "입주자격",
                "소득및자산보유기준",
                "소득자산기준",
                "입주자격완화",
            )
        ):
            continue

        section_text = (
            _section_direct_text(
                section
            )
        )

        if section_text:
            candidate_texts.append(
                section_text
            )

    combined = "\n".join(
        candidate_texts
    )

    normalized_combined = (
        _normalized_match_text(
            combined
        )
    )

    result: dict[str, Any] = {}

    if any(
        token in normalized_combined
        for token in (
            "소득적용배제",
            "소득기준적용배제",
            "소득요건배제",
            "소득및총자산요건적용배제",
        )
    ):
        result[
            "income_criteria"
        ] = "적용 배제"

    if any(
        token in normalized_combined
        for token in (
            "총자산가액적용배제",
            "총자산기준적용배제",
            "총자산가액배제",
            "총자산요건배제",
            "자산요건배제",
            "소득및총자산요건적용배제",
        )
    ):
        result[
            "total_asset_criteria"
        ] = "적용 배제"

    car_match = re.search(
        r"자동차(?:가액|기준)?"
        r"[^0-9]{0,30}"
        r"([0-9][0-9,]*)"
        r"\s*만원\s*이하",
        combined,
    )

    if car_match:
        result[
            "car_value_limit"
        ] = (
            f"{car_match.group(1)}만원 이하"
        )

    return result


def _filter_eligibility_target_groups_for_summary(
    groups: list[dict[str, Any]],
    summary: str,
) -> list[dict[str, Any]]:
    """
    명확한 공고 기본 자격과 양립하지 않는 fallback 계층을 제거한다.

    예: 신혼·신생아 공고에서 문서 주변의 '고령자' 단순 언급이
    target_groups로 들어오는 것을 방지한다.
    """
    if not groups:
        return []

    normalized = _normalized_match_text(summary)

    family_signal = any(
        token in normalized
        for token in (
            "신혼·신생아",
            "신혼신생아",
            "신혼부부",
            "예비신혼부부",
            "한부모가족",
            "혼인가구",
        )
    )

    if family_signal:
        allowed = {
            "newlywed",
            "prospective_newlywed",
            "single_parent_family",
            "supported_single_parent",
            "married_with_children",
            "newborn_family",
            "married_household",
            # 구버전 fallback code가 남아 있는 경우까지 허용하되
            # 고령자/청년 등 이질 계층은 제거한다.
            "newlywed_family",
        }
        return [
            group
            for group in groups
            if str(group.get("code") or "") in allowed
        ]

    return groups


def _build_eligibility(
    matches: list[dict[str, Any]],
    *,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _build_generic_field(
        "eligibility",
        matches,
    )

    # 먼저 실제 입주자격/신청자격 Section에서 카드 상단 summary를
    # 결정한다. 이후 fallback target_groups를 이 summary와 교차검증한다.
    summary = ""
    if structure is not None:
        summary = _build_eligibility_summary_from_structure(structure)
    if not summary:
        summary = _build_eligibility_summary(matches)

    # 상세 자격 결정 순서:
    # 1) 실제 입주자격/신청자격 Section 및 그 자식 Section
    # 2) 자격요건 확인 구비서류 표
    # 3) 기존 키워드 기반 fallback
    target_groups: list[dict[str, Any]] = []

    if structure is not None:
        target_groups = _extract_eligibility_type_groups_from_structure(
            structure
        )

    if not target_groups and structure is not None:
        target_groups = _extract_eligibility_verification_groups(
            structure
        )

    if not target_groups:
        target_groups = _extract_eligibility_target_groups(matches)

    target_groups = _filter_eligibility_target_groups_for_summary(
        target_groups,
        summary,
    )

    common_conditions = _extract_common_eligibility_conditions(matches)

    key_criteria: dict[str, Any] = {}
    if structure is not None:
        key_criteria = _extract_eligibility_key_criteria(structure)

    result.update(
        {
            "summary": summary,
            "target_groups": target_groups,
            "common_conditions": common_conditions,
            "key_criteria": key_criteria,
        }
    )

    return result


SUPPLY_TABLE_HEADER_RULES = (
    (
        "complex_name",
        (
            "단지명",
            "단지 명",
        ),
    ),
    (
        "housing_group",
        (
            "주택군",
            "주택 군",
        ),
    ),
    (
        "housing_type",
        (
            "주택형",
            "주택 형",
        ),
    ),
    (
        "location",
        (
            "주택소재지",
            "주택 소재지",
            "소재지",
        ),
    ),
    (
        "area",
        (
            "전용면적",
            "전용 면적",
            "공급면적",
            "공급 면적",
            "면적",
        ),
    ),
    (
        "supply_units",
        (
            "공급호수",
            "공급 호수",
            "주택호수",
            "주택 호수",
            "건설호수",
            "건설 호수",
        ),
    ),
    (
        "recruitment_units",
        (
            "모집호수",
            "모집 호수",
        ),
    ),
    (
        "recruitment_waitlist",
        (
            "금회모집예비자수",
            "금회 모집 예비자수",
            "모집할예비자수",
            "모집할 예비자수",
            "모집예비자수",
            "모집 예비자수",
            "모집예비자",
            "모집 예비자",
            "모집하는예비자수",
            "모집하는 예비자수",
        ),
    ),
    (
        "waiting_waitlist",
        (
            "대기중인예비자수",
            "대기 중인 예비자수",
            "대기중 예비자수",
            "대기 예비자수",
        ),
    ),
    (
        "deposit",
        (
            "임대보증금",
            "임대 보증금",
        ),
    ),
    (
        "monthly_rent",
        (
            "월임대료",
            "월 임대료",
        ),
    ),
    (
        "rental_condition",
        (
            "임대조건",
            "임대 조건",
        ),
    ),
)


SUPPLY_TABLE_NUMERIC_FIELDS = {
    "supply_units",
    "recruitment_units",
    "recruitment_waitlist",
    "waiting_waitlist",
}


def _supply_table_header_field(
    value: Any,
) -> str | None:
    """
    공급 표의 헤더명을 내부 field명으로 변환한다.
    """
    text_value = _clean_text(
        value
    )

    if not text_value:
        return None

    for field, keywords in (
        SUPPLY_TABLE_HEADER_RULES
    ):
        if _contains_keyword(
            text_value,
            keywords,
        ):
            return field

    return None


def _parse_supply_table_integer(
    value: Any,
) -> int | None:
    """
    '58', '58호', '260명', '1,200' 형태의 숫자를 정수로 변환한다.
    숫자가 없으면 None.
    """
    text_value = _clean_text(
        value
    )

    if not text_value:
        return None

    found = re.search(
        r"(?<!\d)"
        r"(?P<number>\d[\d,]*)"
        r"(?!\d)",
        text_value,
    )

    if not found:
        return None

    try:
        return int(
            found.group(
                "number"
            ).replace(
                ",",
                "",
            )
        )
    except ValueError:
        return None



def _is_strong_supply_header_set(
    header_fields: dict[int, str],
) -> bool:
    """
    공급표 오탐 방지 + 실제 LH 표 헤더 분할 대응.

    인정 기준:
    1. 주택 식별자 계열 + 공급/모집 수량 계열이 함께 존재
    2. 공급/모집 수량 계열이 2개 이상 존재

    임대조건/보증금/월임대료만 있는 표는 공급표로 인정하지 않는다.
    """
    fields = set(
        header_fields.values()
    )

    identity_fields = {
        "complex_name",
        "housing_group",
        "housing_type",
        "location",
    }

    count_fields = {
        "supply_units",
        "recruitment_units",
        "recruitment_waitlist",
        "waiting_waitlist",
    }

    identity_count = len(
        fields & identity_fields
    )

    supply_count = len(
        fields & count_fields
    )

    if (
        identity_count >= 1
        and supply_count >= 1
    ):
        return True

    if supply_count >= 2:
        return True

    return False


def _looks_like_supply_item(
    item: dict[str, Any],
) -> bool:
    """
    실제 공급행인지 최소 검증한다.

    다음 중 하나를 만족해야 한다.
    - 단지명/주택군/주택형/소재지 중 하나 존재
    - 실제 공급/모집 수량 값 존재

    임대조건 장문만 있는 행은 제외한다.
    """
    identity_fields = (
        "complex_name",
        "housing_group",
        "housing_type",
        "location",
    )

    count_fields = (
        "supply_units",
        "recruitment_units",
        "recruitment_waitlist",
        "waiting_waitlist",
    )

    has_identity = any(
        _clean_text(
            item.get(
                field
            )
        )
        for field in identity_fields
    )

    has_count = any(
        item.get(
            field
        )
        not in (
            None,
            "",
        )
        for field in count_fields
    )

    return (
        has_identity
        or has_count
    )


def _extract_supply_table_rows(
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Structure의 원본 table cells를 기준으로 공급 표를 구조화한다.

    지원 예:
    - 단지명
    - 주택군
    - 주택형
    - 소재지
    - 면적
    - 공급호수
    - 모집호수
    - 모집예비자 / 모집예비자수 / 모집하는 예비자수
    - 임대보증금
    - 월임대료
    - 임대조건

    표에서 '공급호수'와 '모집예비자'는 서로 다른 값으로 유지한다.
    """

    rows_result: list[
        dict[str, Any]
    ] = []

    seen_rows: set[
        tuple[
            tuple[str, str],
            ...
        ]
    ] = set()

    for node in _iter_nested_dicts(
        structure
    ):
        cells = node.get(
            "cells"
        )

        if not isinstance(
            cells,
            list,
        ):
            continue

        table_cells = [
            cell
            for cell in cells
            if isinstance(
                cell,
                dict,
            )
        ]

        if not table_cells:
            continue

        rows: dict[
            int,
            dict[int, str],
        ] = {}

        for cell in table_cells:
            row = cell.get(
                "row"
            )
            col = cell.get(
                "col"
            )

            if (
                not isinstance(
                    row,
                    int,
                )
                or not isinstance(
                    col,
                    int,
                )
            ):
                continue

            cell_text = _clean_text(
                cell.get(
                    "text"
                )
            )

            if not cell_text:
                continue

            rows.setdefault(
                row,
                {},
            )[col] = cell_text

        if not rows:
            continue

        sorted_row_numbers = sorted(
            rows
        )

        # -----------------------------------------------
        # 이 table에서 공급정보 header row를 찾는다.
        # 최소 2개 공급 헤더가 있거나,
        # 공급호수/모집예비자처럼 강한 헤더가 1개 이상 있어야 한다.
        # -----------------------------------------------
        header_row_number: (
            int | None
        ) = None
        header_fields: dict[
            int,
            str,
        ] = {}

        for row_index, row_number in enumerate(
            sorted_row_numbers
        ):
            # LH 표는 헤더가 2~3줄로 분리되는 경우가 많다.
            # 예:
            #   주택 / 호수
            #   대기중인 / 예비자수
            #   금회 모집 / 예비자수
            #
            # 따라서 현재 행부터 최대 3개 행을 같은 열 기준으로
            # 합쳐서 헤더 후보를 판정한다.
            candidate_fields: dict[
                int,
                str,
            ] = {}

            last_header_row = (
                row_number
            )

            max_window = min(
                row_index + 3,
                len(
                    sorted_row_numbers
                ),
            )

            combined_by_col: dict[
                int,
                list[str],
            ] = {}

            for window_index in range(
                row_index,
                max_window,
            ):
                current_row_number = (
                    sorted_row_numbers[
                        window_index
                    ]
                )

                # 실제로 연속된 표 header row만 묶는다.
                if (
                    current_row_number
                    - row_number
                    > 2
                ):
                    break

                for (
                    col,
                    cell_text,
                ) in rows[
                    current_row_number
                ].items():
                    combined_by_col.setdefault(
                        col,
                        [],
                    ).append(
                        cell_text
                    )

                temporary_fields: dict[
                    int,
                    str,
                ] = {}

                for (
                    col,
                    values,
                ) in combined_by_col.items():
                    combined_text = (
                        " ".join(
                            values
                        )
                    )

                    field = (
                        _supply_table_header_field(
                            combined_text
                        )
                    )

                    if field:
                        temporary_fields[
                            col
                        ] = field

                if _is_strong_supply_header_set(
                    temporary_fields
                ):
                    candidate_fields = (
                        temporary_fields
                    )
                    last_header_row = (
                        current_row_number
                    )
                    break

            if candidate_fields:
                header_row_number = (
                    last_header_row
                )
                header_fields = (
                    candidate_fields
                )
                break

        if (
            header_row_number
            is None
            or not header_fields
        ):
            continue

        # -----------------------------------------------
        # header 아래의 실제 data row를 구조화한다.
        # -----------------------------------------------
        for row_number in (
            sorted_row_numbers
        ):
            if (
                row_number
                <= header_row_number
            ):
                continue

            row_cells = rows[
                row_number
            ]

            item: dict[
                str,
                Any,
            ] = {}

            for (
                col,
                field,
            ) in header_fields.items():
                raw_value = _clean_text(
                    row_cells.get(
                        col
                    )
                )

                if not raw_value:
                    continue

                if (
                    field
                    in SUPPLY_TABLE_NUMERIC_FIELDS
                ):
                    numeric_value = (
                        _parse_supply_table_integer(
                            raw_value
                        )
                    )

                    if (
                        numeric_value
                        is not None
                    ):
                        item[
                            field
                        ] = (
                            numeric_value
                        )
                        continue

                    # 공급호수/모집호수는 반드시 숫자여야 한다.
                    # "모집인원", "예비입주자 모집인원" 같은
                    # 다음 단계 header 문자열을 data로 넣지 않는다.
                    if field in {
                        "supply_units",
                        "recruitment_units",
                    }:
                        continue

                    # 대기중 예비자수는 실제 값이 "선정 중"처럼
                    # 숫자가 아닐 수 있으므로 상태 표현만 허용한다.
                    normalized_status = (
                        _normalized_match_text(
                            raw_value
                        )
                    )

                    allowed_statuses = (
                        "선정중",
                        "없음",
                        "해당없음",
                        "미정",
                    )

                    if any(
                        status
                        in normalized_status
                        for status in allowed_statuses
                    ):
                        item[
                            field
                        ] = raw_value

                    continue

                item[
                    field
                ] = raw_value

            if not item:
                continue

            # 헤더 반복행을 data로 잘못 잡지 않도록 제외
            repeated_header = any(
                _supply_table_header_field(
                    value
                )
                is not None
                for value in item.values()
                if isinstance(
                    value,
                    str,
                )
            )

            if repeated_header:
                continue

            # 공급정보로 쓸 수 있는 실제 값이 하나라도 있어야 한다.
            if not _looks_like_supply_item(
                item
            ):
                continue

            row_key = tuple(
                sorted(
                    (
                        str(key),
                        str(value),
                    )
                    for key, value
                    in item.items()
                )
            )

            if row_key in seen_rows:
                continue

            seen_rows.add(
                row_key
            )

            item[
                "source"
            ] = {
                "type": (
                    "structured_supply_table"
                ),
                "row": (
                    row_number
                ),
            }

            rows_result.append(
                item
            )

    return rows_result


def _summarize_supply_table_rows(
    rows: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    """
    표에서 추출한 여러 행을 top-level 카드 값으로 요약한다.

    우선순위:
    1. '소계' / '합계' / '총계' 행이 있으면 해당 값을 사용
    2. 합계 행이 없을 때만 상세 행 값을 합산

    이렇게 해야 아래와 같은 표에서
    소계 58 / 260
    + 상세 행들
    을 모두 더해서 99 / 450으로 중복 집계하는 문제를 막을 수 있다.
    """

    total_row_keywords = (
        "소계",
        "합계",
        "총계",
        "계",
    )

    total_rows: list[
        dict[str, Any]
    ] = []

    for item in rows:
        labels = [
            _clean_text(
                item.get(key)
            )
            for key in (
                "complex_name",
                "housing_group",
                "housing_type",
                "location",
            )
            if _clean_text(
                item.get(key)
            )
        ]

        if any(
            label in total_row_keywords
            for label in labels
        ):
            total_rows.append(
                item
            )

    # 표 안에 명시적인 소계/합계가 있으면 그 값을 최우선으로 사용
    if total_rows:
        supply_units = next(
            (
                item.get(
                    "supply_units"
                )
                for item in total_rows
                if isinstance(
                    item.get(
                        "supply_units"
                    ),
                    int,
                )
            ),
            None,
        )

        recruitment_units = next(
            (
                item.get(
                    "recruitment_units"
                )
                for item in total_rows
                if isinstance(
                    item.get(
                        "recruitment_units"
                    ),
                    int,
                )
            ),
            None,
        )

        recruitment_waitlist = next(
            (
                item.get(
                    "recruitment_waitlist"
                )
                for item in total_rows
                if isinstance(
                    item.get(
                        "recruitment_waitlist"
                    ),
                    int,
                )
            ),
            None,
        )

        waiting_waitlist = next(
            (
                item.get(
                    "waiting_waitlist"
                )
                for item in total_rows
                if isinstance(
                    item.get(
                        "waiting_waitlist"
                    ),
                    int,
                )
            ),
            None,
        )

        return {
            "supply_units": (
                supply_units
            ),
            "recruitment_waitlist": (
                recruitment_waitlist
            ),
            "waiting_waitlist": (
                waiting_waitlist
            ),
            "recruitment_units": (
                recruitment_units
            ),
        }

    # 합계 행이 없는 표만 상세 행을 합산
    supply_values = [
        item.get(
            "supply_units"
        )
        for item in rows
        if isinstance(
            item.get(
                "supply_units"
            ),
            int,
        )
    ]

    waitlist_values = [
        item.get(
            "recruitment_waitlist"
        )
        for item in rows
        if isinstance(
            item.get(
                "recruitment_waitlist"
            ),
            int,
        )
    ]

    recruitment_unit_values = [
        item.get(
            "recruitment_units"
        )
        for item in rows
        if isinstance(
            item.get(
                "recruitment_units"
            ),
            int,
        )
    ]

    waiting_waitlist_values = [
        item.get(
            "waiting_waitlist"
        )
        for item in rows
        if isinstance(
            item.get(
                "waiting_waitlist"
            ),
            int,
        )
    ]

    return {
        "supply_units": (
            sum(
                supply_values
            )
            if supply_values
            else None
        ),
        "recruitment_waitlist": (
            sum(
                waitlist_values
            )
            if waitlist_values
            else None
        ),
        "waiting_waitlist": (
            sum(
                waiting_waitlist_values
            )
            if waiting_waitlist_values
            else None
        ),
        "recruitment_units": (
            sum(
                recruitment_unit_values
            )
            if recruitment_unit_values
            else None
        ),
    }


def _extract_supply_from_structure(
    structure: dict[str, Any],
) -> dict[str, Any]:
    texts = _collect_structure_texts(
        structure
    )

    total_units: int | None = None
    total_units_text = ""
    details_reference = ""
    rental_condition_summary = ""

    total_pattern = re.compile(
        r"공급대상\s*주택"
        r"\s*[:：]?\s*"
        r"총\s*"
        r"(?P<count>\d[\d,]*)"
        r"\s*호"
    )

    supply_count_pattern = re.compile(
        r"(?:공급|모집)\s*호수"
        r"\s*[:：]?\s*"
        r"(?P<count>\d[\d,]*)"
        r"\s*호?"
    )

    for text_value in texts:
        found = total_pattern.search(
            text_value
        )

        if found:
            total_units = int(
                found.group(
                    "count"
                ).replace(
                    ",",
                    "",
                )
            )
            total_units_text = (
                _clean_text(
                    found.group(0)
                )
            )
            break

    if total_units is None:
        for text_value in texts:
            found = (
                supply_count_pattern.search(
                    text_value
                )
            )

            if not found:
                continue

            total_units = int(
                found.group(
                    "count"
                ).replace(
                    ",",
                    "",
                )
            )
            total_units_text = (
                _clean_text(
                    found.group(0)
                )
            )
            break

    for text_value in texts:
        for line in (
            text_value.splitlines()
        ):
            cleaned = _clean_text(
                line
            )

            if (
                not details_reference
                and "주택내역"
                in cleaned
                and any(
                    keyword in cleaned
                    for keyword in (
                        "세부내역",
                        "주택군",
                        "소재지",
                        "면적",
                        "임대조건",
                    )
                )
            ):
                details_reference = (
                    cleaned
                )

            if (
                not rental_condition_summary
                and "시중 시세"
                in cleaned
                and (
                    "임대료"
                    in cleaned
                    or "임대보증금"
                    in cleaned
                )
            ):
                rental_condition_summary = (
                    cleaned
                )

    return {
        "total_units": total_units,
        "total_units_text": (
            total_units_text
        ),
        "details_reference": (
            details_reference
        ),
        "rental_condition_summary": (
            rental_condition_summary
        ),
    }


def _extract_total_supply_units(
    matches: list[
        dict[str, Any]
    ],
) -> int | None:
    priority_patterns = (
        re.compile(
            r"공급대상\s*주택"
            r"\s*[:：]?\s*"
            r"총\s*"
            r"(?P<count>\d[\d,]*)"
            r"\s*호"
        ),
        re.compile(
            r"(?:공급|모집)"
            r"\s*호수"
            r"\s*[:：]?\s*"
            r"(?P<count>\d[\d,]*)"
            r"\s*호?"
        ),
    )

    fallback_pattern = re.compile(
        r"총\s*"
        r"(?P<count>\d[\d,]*)"
        r"\s*호"
    )

    for item in matches:
        text_value = _clean_text(
            item.get("text")
        )

        for pattern in (
            priority_patterns
        ):
            found = pattern.search(
                text_value
            )

            if found:
                return int(
                    found.group(
                        "count"
                    ).replace(
                        ",",
                        "",
                    )
                )

    for item in matches:
        text_value = _clean_text(
            item.get("text")
        )

        found = fallback_pattern.search(
            text_value
        )

        if found:
            return int(
                found.group(
                    "count"
                ).replace(
                    ",",
                    "",
                )
            )

    return None


def _extract_supply_details_reference(
    matches: list[
        dict[str, Any]
    ],
) -> str:
    for item in matches:
        text_value = _clean_text(
            item.get("text")
        )

        for line in (
            text_value.splitlines()
        ):
            cleaned = _clean_text(
                line
            )

            if (
                "주택내역"
                not in cleaned
            ):
                continue

            if any(
                keyword in cleaned
                for keyword in (
                    "세부내역",
                    "주택군",
                    "소재지",
                    "면적",
                    "임대조건",
                )
            ):
                return cleaned

    return ""


def _extract_supply_rental_condition_summary(
    matches: list[
        dict[str, Any]
    ],
) -> str:
    for item in matches:
        text_value = _clean_text(
            item.get("text")
        )

        for line in (
            text_value.splitlines()
        ):
            cleaned = _clean_text(
                line
            )

            if (
                "시중 시세"
                in cleaned
                and (
                    "임대료"
                    in cleaned
                    or "임대보증금"
                    in cleaned
                )
            ):
                return cleaned

    for item in matches:
        text_value = _clean_text(
            item.get("text")
        )

        for line in (
            text_value.splitlines()
        ):
            cleaned = _clean_text(
                line
            )

            if (
                "임대조건"
                in cleaned
                and "주택내역"
                in cleaned
            ):
                return cleaned

    return ""


def _build_supply_information(
    matches: list[
        dict[str, Any]
    ],
    *,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid_matches = [
        match
        for match in matches
        if _is_valid_supply_section(
            match["_section"]
        )
    ]

    result = _build_generic_field(
        "supply_information",
        valid_matches,
    )

    total_units = (
        _extract_total_supply_units(
            valid_matches
        )
    )

    details_reference = (
        _extract_supply_details_reference(
            valid_matches
        )
    )

    rental_condition_summary = (
        _extract_supply_rental_condition_summary(
            valid_matches
        )
    )

    summary = (
        _build_supply_summary(
            valid_matches
        )
    )

    housing_items: list[
        dict[str, Any]
    ] = []

    supply_units: int | None = None
    recruitment_units: (
        int | None
    ) = None
    recruitment_waitlist: (
        int | None
    ) = None

    if structure is not None:
        fallback = (
            _extract_supply_from_structure(
                structure
            )
        )

        if total_units is None:
            total_units = (
                fallback.get(
                    "total_units"
                )
            )

        if not details_reference:
            details_reference = (
                fallback.get(
                    "details_reference"
                )
                or ""
            )

        if not rental_condition_summary:
            rental_condition_summary = (
                fallback.get(
                    "rental_condition_summary"
                )
                or ""
            )

        if not summary:
            summary = (
                fallback.get(
                    "total_units_text"
                )
                or ""
            )

        # ----------------------------------------------------
        # 공급 표 구조화
        #
        # 예:
        # 공급호수 58
        # 모집예비자 260
        #
        # 또는 여러 단지/주택형별 행
        # ----------------------------------------------------
        housing_items = (
            _extract_supply_table_rows(
                structure
            )
        )

        table_summary = (
            _summarize_supply_table_rows(
                housing_items
            )
        )

        supply_units = (
            table_summary.get(
                "supply_units"
            )
        )
        recruitment_units = (
            table_summary.get(
                "recruitment_units"
            )
        )
        recruitment_waitlist = (
            table_summary.get(
                "recruitment_waitlist"
            )
        )

        # 본문에 '총 N호'가 없고 표에만 공급호수가 있는 경우
        # 표의 공급호수 합계를 total_units fallback으로 사용한다.
        if (
            total_units is None
            and isinstance(
                supply_units,
                int,
            )
        ):
            total_units = (
                supply_units
            )

        # 공급 카드에는 임대조건 문장 대신 공급대상 주택 요약을 보여준다.
        # 총 공급호수를 확보한 경우에는 기존 후보가 무엇이든 일관된 형식으로
        # 정규화한다. 임대조건은 rental_condition_summary에 별도로 유지된다.
        if isinstance(
            total_units,
            int,
        ):
            summary = (
                "공급대상 주택 : "
                f"총 {total_units}호"
            )
        elif (
            housing_items
            and (
                not summary
                or any(
                    keyword in _normalized_match_text(summary)
                    for keyword in (
                        _normalized_match_text("임대보증금"),
                        _normalized_match_text("월임대료"),
                        _normalized_match_text("전환이율"),
                        _normalized_match_text("상호전환"),
                    )
                )
            )
        ):
            # 표에서 주택행은 찾았지만 총 호수 계산이 불가능한 공고는
            # 잘못된 임대조건 문장을 공급 요약으로 노출하지 않는다.
            summary = "공급대상 주택은 공고문 주택내역 참조"

    result.update(
        {
            "summary": summary,
            "total_units": (
                total_units
            ),
            "supply_units": (
                supply_units
            ),
            "recruitment_units": (
                recruitment_units
            ),
            "recruitment_waitlist": (
                recruitment_waitlist
            ),
            "housing_items": (
                housing_items
            ),
            "details_reference": (
                details_reference
            ),
            "rental_condition_summary": (
                rental_condition_summary
            ),
        }
    )

    if (
        total_units is not None
        or supply_units is not None
        or recruitment_units is not None
        or recruitment_waitlist is not None
        or bool(
            housing_items
        )
        or details_reference
        or rental_condition_summary
    ):
        result["status"] = (
            "extracted"
        )

    return result


def _build_income_asset_criteria(
    matches: list[
        dict[str, Any]
    ],
    *,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _build_generic_field(
        "income_asset_criteria",
        matches,
    )

    # 입주자격 완화 공고는 일반적인 소득/자산 설명이나
    # 갱신계약 할증 문장보다 실제 적용되는 완화 기준을
    # 카드 요약에 우선 표시한다.
    key_criteria: dict[str, Any] = {}
    if structure is not None:
        key_criteria = (
            _extract_eligibility_key_criteria(
                structure
            )
        )

    summary_parts: list[str] = []

    income_criteria = key_criteria.get(
        "income_criteria"
    )
    if income_criteria:
        summary_parts.append(
            f"소득요건 {income_criteria}"
        )

    total_asset_criteria = (
        key_criteria.get(
            "total_asset_criteria"
        )
    )
    if total_asset_criteria:
        summary_parts.append(
            f"총자산요건 {total_asset_criteria}"
        )

    car_value_limit = key_criteria.get(
        "car_value_limit"
    )
    if car_value_limit:
        summary_parts.append(
            f"자동차가액 {car_value_limit}"
        )

    if summary_parts:
        result["summary"] = " · ".join(
            summary_parts
        )
        result["key_criteria"] = (
            key_criteria
        )
        result["status"] = "extracted"
    else:
        result["summary"] = (
            _build_income_asset_summary(
                matches
            )
        )

    return result


def _build_required_documents(
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    result = _build_generic_field(
        "required_documents",
        matches,
    )

    items = _extract_document_items(
        matches
    )

    result["items"] = items
    result["summary"] = (
        " · ".join(items)
        if items
        else ""
    )

    return result


def _build_winner_announcement(
    matches: list[
        dict[str, Any]
    ],
    *,
    structure: dict[str, Any] | None = None,
    reference_year: int | None = None,
) -> dict[str, Any]:
    result = _build_generic_field(
        "winner_announcement",
        matches,
    )

    table_raw_value: str | None = None
    table_announcement_date: (
        str | None
    ) = None

    if structure is not None:
        table_raw_value = (
            _extract_schedule_table_value(
                structure,
                target_keywords=(
                    WINNER_PRIORITY_KEYWORDS
                ),
                exclusion_keywords=(
                    WINNER_EXCLUSION_KEYWORDS
                ),
            )
        )

        if table_raw_value:
            explicit_match = (
                _DATE_WITH_TIME_PATTERN.search(
                    table_raw_value
                )
            )

            if explicit_match:
                try:
                    table_announcement_date = (
                        _normalize_date_match(
                            explicit_match
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    table_announcement_date = (
                        None
                    )

            if (
                table_announcement_date
                is None
            ):
                table_announcement_date = (
                    _normalize_yearless_single_date(
                        table_raw_value,
                        reference_year=reference_year,
                    )
                )

    winner_dates: list[
        dict[str, Any]
    ] = []

    for match_item in matches:
        text_value = (
            match_item["text"]
        )

        keyword_positions = (
            _keyword_positions(
                text_value,
                WINNER_PRIORITY_KEYWORDS,
            )
        )

        if not keyword_positions:
            continue

        for date_match in (
            _DATE_WITH_TIME_PATTERN.finditer(
                text_value
            )
        ):
            distance = (
                _distance_to_nearest_keyword(
                    date_match.start(),
                    keyword_positions,
                )
            )

            if distance > 180:
                continue

            left = max(
                0,
                date_match.start()
                - 100,
            )
            right = min(
                len(text_value),
                date_match.end()
                + 100,
            )

            date_context = _clean_text(
                text_value[
                    left:right
                ]
            )

            if _contains_keyword(
                date_context,
                WINNER_EXCLUSION_KEYWORDS,
            ):
                continue

            try:
                normalized = (
                    _normalize_date_match(
                        date_match
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            winner_dates.append(
                {
                    "raw": _clean_text(
                        date_match.group(
                            0
                        )
                    ),
                    "normalized_value": (
                        normalized
                    ),
                    "context": (
                        date_context
                    ),
                    "distance": (
                        distance
                    ),
                }
            )

    winner_dates.sort(
        key=lambda item: (
            item["distance"],
            item[
                "normalized_value"
            ],
        )
    )

    deduped: list[
        dict[str, Any]
    ] = []
    seen: set[str] = set()

    for item in winner_dates:
        value = item[
            "normalized_value"
        ]

        if value in seen:
            continue

        seen.add(value)
        deduped.append(item)

    public_dates = [
        {
            "raw": item["raw"],
            "normalized_value": (
                item[
                    "normalized_value"
                ]
            ),
            "context": (
                item["context"]
            ),
        }
        for item in deduped
    ]

    if table_announcement_date:
        result["dates"] = [
            {
                "raw": (
                    table_raw_value
                    or ""
                ),
                "normalized_value": (
                    table_announcement_date
                ),
                "context": (
                    "structured_schedule_table"
                ),
            }
        ]
        result[
            "announcement_date"
        ] = (
            table_announcement_date
        )
        result["summary"] = (
            table_announcement_date
        )
        result["status"] = (
            "extracted"
        )
    else:
        result["dates"] = (
            public_dates
        )
        result[
            "announcement_date"
        ] = (
            deduped[0][
                "normalized_value"
            ]
            if deduped
            else None
        )
        result["summary"] = (
            result.get(
                "announcement_date"
            )
            or ""
        )

    if (
        not table_announcement_date
        and not deduped
        and not result.get(
            "key_values"
        )
        and not result.get(
            "text"
        )
    ):
        result["status"] = (
            "not_found"
        )

    return result


def _build_contact_information(
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    result = _build_generic_field(
        "contact_information",
        matches,
    )

    phones = _collect_phone_numbers(
        matches
    )

    result["phone_numbers"] = (
        phones
    )

    if (
        not phones
        and not result.get(
            "key_values"
        )
        and not result.get(
            "text"
        )
    ):
        result["status"] = (
            "not_found"
        )

    return result


# ============================================================
# Verification
# ============================================================
def _validate_verification(
    verification: dict[
        str,
        Any,
    ],
) -> None:
    status = _clean_text(
        verification.get("status")
    ).lower()

    if status != "pass":
        raise RuntimeError(
            "Structure Verification이 pass가 아닙니다. "
            f"status={status or 'missing'}"
        )


# ============================================================
# 공식 Extractor
# ============================================================
def extract_key_information(
    *,
    structure_path: Path,
    verification_path: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Structure 최종 결과에서 Backend key_information 7개 필드를 추출한다.

    원칙:
    - Structure의 domain 분류를 최우선 근거로 사용
    - 규칙 분류가 부족한 경우에만 제목/본문 keyword fallback
    - 원문에 없는 값을 추측하지 않음
    - 찾지 못한 필드는 status=not_found
    - source section을 함께 남겨 후속 검수 가능
    """

    structure_path = Path(
        structure_path
    )
    verification_path = Path(
        verification_path
    )

    structure = _load_json(
        structure_path
    )
    verification = _load_json(
        verification_path
    )

    _validate_verification(
        verification
    )

    sections = structure.get(
        "sections"
    )

    if not isinstance(
        sections,
        list,
    ):
        raise RuntimeError(
            "Structure JSON에 sections 배열이 없습니다."
        )

    reference_year = (
        _extract_reference_year(
            structure,
            context,
        )
    )

    matches = {
        field: (
            _collect_field_matches(
                structure,
                field,
            )
        )
        for field
        in REQUIRED_FIELDS
    }

    result: dict[
        str,
        Any,
    ] = {
        "application_period": (
            _build_application_period(
                matches[
                    "application_period"
                ],
                structure=structure,
                reference_year=(
                    reference_year
                ),
            )
        ),
        "eligibility": (
            _build_eligibility(
                matches[
                    "eligibility"
                ],
                structure=structure,
            )
        ),
        "supply_information": (
            _build_supply_information(
                matches[
                    "supply_information"
                ],
                structure=structure,
            )
        ),
        "income_asset_criteria": (
            _build_income_asset_criteria(
                matches[
                    "income_asset_criteria"
                ],
                structure=structure,
            )
        ),
        "required_documents": (
            _build_required_documents(
                matches[
                    "required_documents"
                ]
            )
        ),
        "winner_announcement": (
            _build_winner_announcement(
                matches[
                    "winner_announcement"
                ],
                structure=structure,
                reference_year=(
                    reference_year
                ),
            )
        ),
        "contact_information": (
            _build_contact_information(
                matches[
                    "contact_information"
                ]
            )
        ),
    }

    missing = [
        field
        for field
        in REQUIRED_FIELDS
        if (
            field not in result
            or not isinstance(
                result[field],
                dict,
            )
        )
    ]

    if missing:
        raise RuntimeError(
            "핵심정보 추출 결과 계약 위반: "
            f"{missing}"
        )

    return result
