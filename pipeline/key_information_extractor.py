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



def _extract_happyhouse_common_eligibility_summary(
    structure: dict[str, Any],
) -> str:
    """
    행복주택의 ``■ 입주자 신청자격`` 블록에서 사용자가 바로 볼
    공통 신청자격만 추출한다.

    화면 상단 summary에는 다음 영역만 사용한다.
    - 입주자 선정에 필요한 자격 판단 기준
    - 주택공급신청자의 성년/무주택세대구성원 기본 조건

    뒤의 ``무주택세대구성원이란?`` 정의, 자격검증 대상, 재청약/유의사항은
    summary에 포함하지 않는다.
    """
    candidates = _collect_content_text_candidates(structure)

    # 가장 많은 문맥을 가진 원문부터 확인한다.
    relevant = [
        text_value
        for text_value in candidates
        if _contains_keyword(text_value, ("입주자 신청자격",))
    ]

    # heading과 본문이 서로 다른 structure node로 분리된 문서 보완.
    combined_candidates = "\n".join(_deduplicate_texts(candidates))
    if (
        combined_candidates
        and _contains_keyword(combined_candidates, ("입주자 신청자격",))
    ):
        relevant.append(combined_candidates)

    relevant = _deduplicate_texts(relevant)
    relevant.sort(key=len, reverse=True)

    for text_value in relevant:
        cleaned = _clean_text(text_value)
        match = re.search(
            r"(?:■\s*)?입주자\s*신청자격(?P<body>.*)",
            cleaned,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue

        body = match.group("body")

        # 공통 신청자격 영역의 끝.
        stop_patterns = (
            r"(?:•\s*)?무주택\s*세대구성원(?:이란|\?)",
            r"■\s*공급계층\s*재청약",
            r"■\s*입주자격\s*조사결과",
            r"\b3-1\.",
        )
        stop_positions: list[int] = []
        for pattern in stop_patterns:
            stop = re.search(pattern, body, re.IGNORECASE)
            if stop:
                stop_positions.append(stop.start())
        if stop_positions:
            body = body[:min(stop_positions)]

        # 원문의 bullet 단위를 그대로 사용한다.
        bullet_parts = [
            re.sub(r"\s+", " ", _clean_text(part)).strip()
            for part in re.split(r"\s*•\s*", body)
            if _clean_text(part)
        ]

        selected: list[str] = []
        for part in bullet_parts:
            normalized = _normalized_match_text(part)
            if not normalized:
                continue
            if (
                "입주자선정에필요한자격" in normalized
                or "주택공급신청자는" in normalized
            ):
                selected.append(part)
            if len(selected) >= 2:
                break

        if selected:
            return " ".join(selected).strip()

    return ""


def _extract_explicit_eligibility_summary_from_structure(
    structure: dict[str, Any],
) -> str:
    """
    신청자격 카드의 대표 문장을 실제 자격 영역에서 선택한다.

    행복주택의 ``입주자 신청자격`` 공통 블록을 가장 먼저 사용하고,
    그 형태가 없는 다른 임대주택 공고는 기존의 명시적
    ``입주자격/신청자격`` 문장 탐색으로 fallback한다.
    """
    happyhouse_summary = _extract_happyhouse_common_eligibility_summary(
        structure
    )
    if happyhouse_summary:
        return happyhouse_summary

    search_texts = _collect_content_text_candidates(structure)
    candidates: list[tuple[int, int, str]] = []

    negative_keywords = (
        "조회결과",
        "부적격",
        "탈락",
        "재계약",
        "갱신계약",
        "계약종료",
        "유의사항",
        "작성요령",
        "주택도시기금",
    )

    for text_index, text_value in enumerate(_deduplicate_texts(search_texts)):
        raw_parts = [
            part
            for part in text_value.splitlines()
            if _clean_text(part)
        ]
        if not raw_parts:
            raw_parts = [text_value]

        for raw in raw_parts:
            cleaned = re.sub(r"\s+", " ", _clean_text(raw)).strip()
            if not cleaned:
                continue

            explicit = re.search(
                r"(?:^|\s)[■◆●▪□]?\s*(?:입주|신청)\s*자격\s*[:：]\s*(?P<body>.+)",
                cleaned,
                re.IGNORECASE,
            )
            body = _clean_text(explicit.group("body")) if explicit else cleaned
            normalized = _normalized_match_text(body)

            if any(
                _normalized_match_text(keyword) in normalized
                for keyword in negative_keywords
            ):
                continue

            has_announcement_date = any(
                token in normalized
                for token in (
                    "입주자모집공고일",
                    "모집공고일현재",
                    "모집공고일",
                )
            )
            has_no_home = (
                "무주택세대구성원" in normalized
                or "무주택자" in normalized
            )
            has_qualification = any(
                token in normalized
                for token in (
                    "세부자격요건",
                    "자격요건",
                    "소득기준",
                    "소득및자산",
                    "소득자산",
                )
            )

            evidence_count = sum(
                (has_announcement_date, has_no_home, has_qualification)
            )
            if evidence_count < 2:
                continue

            score = evidence_count * 40
            if explicit:
                score += 80
            if has_announcement_date and has_no_home:
                score += 50

            stop_patterns = (
                r'\s+[“"]?무주택세대구성원[”"]?\s*이란',
                r"\s*※\s*무주택세대구성원\s*[:：]",
                r"\s+세대구성원\s*비고",
                r"\s+■\s*세부\s*자격요건",
            )
            for stop_pattern in stop_patterns:
                stop = re.search(stop_pattern, body, re.IGNORECASE)
                if stop and stop.start() > 0:
                    body = body[:stop.start()].strip()

            body = re.sub(r"^\s*[■◆●▪□•*-]+\s*", "", body).strip()
            body = _compact_summary(body, 180)

            if body:
                candidates.append((score, -text_index, body))

    if not candidates:
        return ""

    candidates.sort(reverse=True)
    return candidates[0][2]


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
        "■ 무주택세대구성원",
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

        candidate = (score, _compact_summary(compact, 180))
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


HAPPYHOUSE_ELIGIBILITY_GROUP_SPECS: tuple[
    tuple[str, str, tuple[str, ...]],
    ...
] = (
    ("college_student", "대학생", ("대학생 계층",)),
    ("youth", "청년", ("청년 계층",)),
    (
        "industrial_worker",
        "산업단지 근로자",
        ("산업단지 근로자 계층", "산업단지근로자 계층"),
    ),
    (
        "newlywed_single_parent",
        "신혼부부 · 한부모가족",
        (
            "신혼부부 · 한부모가족 계층",
            "신혼부부·한부모가족 계층",
        ),
    ),
    ("senior", "고령자", ("고령자", "고령자 계층")),
)


def _happyhouse_group_spec_from_title(
    title: str,
) -> tuple[str, str] | None:
    normalized = _normalized_match_text(title)
    if not normalized:
        return None

    # 반드시 3-x 자격 Section이거나 제목 자체가 계층명인 경우만 인정한다.
    for code, label, aliases in HAPPYHOUSE_ELIGIBILITY_GROUP_SPECS:
        for alias in aliases:
            alias_normalized = _normalized_match_text(alias)
            if alias_normalized not in normalized:
                continue

            if (
                re.search(r"(?:^|\D)3-\d+(?:\.|$)", title)
                or normalized == alias_normalized
            ):
                return code, label

    return None


def _section_subtree_text(
    section: dict[str, Any],
) -> str:
    values: list[str] = []

    direct = _section_direct_text(section)
    if direct:
        values.append(direct)

    children = section.get("children")
    if isinstance(children, list):
        for child, _ in _iter_sections(children):
            child_text = _section_direct_text(child)
            if child_text:
                values.append(child_text)

    return "\n".join(_deduplicate_texts(values))


def _find_explicit_supply_target_marker(
    text_value: str,
) -> re.Match[str] | None:
    """
    계층별 자격 Section의 실제 ``■ 공급대상자`` 제목만 찾는다.

    기존의 ``■? 공급대상자`` 패턴은 ``추가 공급대상자``,
    ``일반공급대상자`` 같은 본문 표현까지 시작점으로 오인할 수 있었다.
    따라서 먼저 검은 사각형(■)이 붙은 명시적 제목을 찾고,
    기호가 유실된 구조화 결과에 대해서만 '줄 시작의 공급대상자'를
    보수적으로 fallback으로 허용한다.
    """
    text_value = _clean_text(text_value)
    if not text_value:
        return None

    # HWP/HWPX 구조화 과정에서 제목과 본문이 같은 줄로 합쳐지는 경우가 있다.
    # 검은 사각형(■)이 보존되어 있다면 줄 시작 여부와 무관하게 정확한
    # ``■ 공급대상자`` 제목으로 취급한다. ``추가 공급대상자`` /
    # ``일반공급대상자``에는 ■가 직접 붙지 않으므로 오탐하지 않는다.
    explicit = re.search(
        r"■\s*공급\s*대상자"
        r"(?:\s*\([^\n)]{0,100}\))?\s*[:：]?",
        text_value,
        re.IGNORECASE,
    )
    if explicit:
        return explicit

    # 일부 structure 생성 과정에서 '■'만 빠진 경우를 위한 fallback.
    # 반드시 줄 시작이어야 하며 '추가 공급대상자', '일반공급대상자'는
    # 이 패턴에 걸리지 않는다.
    return re.search(
        r"(?:^|\n)\s*공급\s*대상자"
        r"(?:\s*\([^\n)]{0,100}\))?\s*[:：]?"
        r"(?=\s*(?:\n|입주자|신청자|무주택))",
        text_value,
        re.IGNORECASE,
    )


def _is_standalone_condition_number(value: str) -> bool:
    """소득요건 앞에서 잘려 남은 ``3``/``③`` 같은 번호 조각을 제거한다."""
    cleaned = re.sub(r"\s+", "", _clean_text(value))
    if not cleaned:
        return True

    return bool(
        re.fullmatch(
            r"(?:[0-9]{1,2}[.)]?|"
            r"[①②③④⑤⑥⑦⑧⑨⑩➀➁➂➃➄➅➆➇➈➉])",
            cleaned,
        )
    )


def _extract_supply_target_sentence(
    text_value: str,
    *,
    code: str,
) -> str:
    """
    계층별 Section의 ``■ 공급대상자`` 바로 아래 대표 설명만 추출한다.

    소득표/자산표/일반공급 순위 전체를 카드에 올리지 않고,
    사용자가 어떤 계층에 해당하는지 이해할 수 있는 공급대상자 대표문장을
    원문 그대로 반환한다.
    """
    text_value = _clean_text(text_value)
    if not text_value:
        return ""

    # 공급대상자 marker 이후부터 현재 계층의 경쟁/순위 Section 전까지만 본다.
    marker = _find_explicit_supply_target_marker(text_value)
    if not marker:
        return ""

    body = text_value[marker.end():]
    stop_patterns = (
        r"■\s*경쟁\s*시",
        r"■\s*일반공급\s*순위",
        r"■\s*산업단지형\s*예비입주자\s*선정기준",
        r"■\s*기타\s*참고사항",
        r"\n\s*3-\d+\.",
    )
    positions: list[int] = []
    for pattern in stop_patterns:
        stop = re.search(pattern, body, re.IGNORECASE)
        if stop:
            positions.append(stop.start())
    if positions:
        body = body[:min(positions)]

    lines = [
        re.sub(r"\s+", " ", _clean_text(line)).strip()
        for line in body.splitlines()
        if _clean_text(line)
    ]

    # 구조화 과정에서 첫 문단과 표 전체가 한 줄로 합쳐지는 경우가 있으므로
    # 원문의 강한 대표문장 패턴을 먼저 찾는다.
    joined = re.sub(r"\s+", " ", _clean_text(body)).strip()

    if code == "senior":
        senior_match = re.search(
            r"입\s*주자\s*모집공고일\s*\([^)]*\)\s*현재,?\s*"
            r"무주택세대구성원.*?65세\s*이상인\s*자",
            joined,
            re.IGNORECASE,
        )
        if senior_match:
            return senior_match.group(0).strip()

    for line in lines:
        normalized = _normalized_match_text(line)
        if (
            "입주자모집공고일" in normalized
            and (
                "무주택자" in normalized
                or "무주택세대구성원" in normalized
            )
        ):
            # 정상적으로 문단이 분리된 경우에는 공급대상자 대표문장을
            # 원문 그대로 보존한다.
            if len(line) <= 600:
                return line

            # 표/조건 전체가 한 줄로 붙은 경우에만 대표문장 끝을 탐색한다.
            compact_match = re.search(
                r"입\s*주자\s*모집공고일\s*\([^)]*\)\s*현재,?\s*"
                r".+?(?:모두\s*갖춘\s*자|요건을\s*갖춘\s*자|65세\s*이상인\s*자)(?:\s*\(\s*단,?.*?\))?",
                line,
                re.IGNORECASE,
            )
            if compact_match:
                return compact_match.group(0).strip()

    # line 분리가 약한 structure fallback.
    fallback = re.search(
        r"입\s*주자\s*모집공고일\s*\([^)]*\)\s*현재,?\s*"
        r".+?(?:모두\s*갖춘\s*자|요건을\s*갖춘\s*자|65세\s*이상인\s*자)(?:\s*\(\s*단,?.*?\))?",
        joined,
        re.IGNORECASE,
    )
    if fallback:
        return fallback.group(0).strip()

    return ""


def _extract_supply_target_details(
    text_value: str,
    *,
    code: str,
) -> list[str]:
    """
    행복주택 계층별 ``■ 공급대상자``의 실제 신청자격만 상세 카드용으로 추출한다.

    핵심 원칙
    ---------
    1. ``추가 공급대상자`` / ``일반공급대상자`` 같은 본문 표현이 아니라
       반드시 실제 ``■ 공급대상자`` 제목부터 시작한다.
    2. 대학생/청년은 실제 번호 조건(①-㉮, ①-㉯, ② ...)부터 보여준다.
    3. 산업단지 근로자는 계층 정의 문장 + ① 재직/지역 조건까지 유지한다.
    4. ``소득요건(배제)``가 시작되면 즉시 중단한다. 소득/자산은 별도 카드가 담당한다.
    5. ``■ 일반공급 순위`` / ``■ 경쟁 시 입주자 선정기준``은 절대 섞지 않는다.
    """
    text_value = _clean_text(text_value)
    if not text_value:
        return []

    marker = _find_explicit_supply_target_marker(text_value)
    if not marker:
        sentence = _extract_supply_target_sentence(text_value, code=code)
        return [sentence] if sentence else []

    body = text_value[marker.end():]

    # 현재 계층의 '공급대상자' 범위를 벗어나는 강한 Section 경계.
    section_stop_patterns = (
        r"■\s*경쟁\s*시",
        r"■\s*일반공급\s*순위",
        r"■\s*산업단지형\s*예비입주자\s*선정기준",
        r"■\s*기타\s*참고사항",
        r"\n\s*3-\d+\.",
    )
    stop_positions: list[int] = []
    for pattern in section_stop_patterns:
        stop = re.search(pattern, body, re.IGNORECASE)
        if stop:
            stop_positions.append(stop.start())

    # 번호가 circled digit이든 일반 숫자든, '소득요건/소득기준' 제목이
    # 시작되는 지점에서 상세 자격을 끝낸다.
    ordinal_prefix = (
        r"(?:"
        r"[①②③④⑤⑥⑦⑧⑨⑩➀➁➂➃➄➅➆➇➈➉]"
        r"|[0-9]{1,2}[.)]?"
        r")?\s*"
    )
    criteria_stop_patterns = (
        ordinal_prefix
        + r"소득\s*(?:요건|기준)(?:\s*적용)?(?:\s*배제)?",
        ordinal_prefix
        + r"소득\s*및\s*(?:총)?자산\s*(?:요건|기준)",
        ordinal_prefix
        + r"총?자산\s*(?:요건|기준)(?:\s*적용)?(?:\s*배제)?",
    )
    for pattern in criteria_stop_patterns:
        stop = re.search(pattern, body, re.IGNORECASE)
        if stop:
            stop_positions.append(stop.start())

    if stop_positions:
        body = body[:min(stop_positions)]

    # HWP/HWPX text-run 단위 개행을 하나의 읽을 수 있는 문장으로 합친다.
    compact = re.sub(r"\s+", " ", _clean_text(body)).strip()
    if not compact:
        sentence = _extract_supply_target_sentence(text_value, code=code)
        return [sentence] if sentence else []

    # text-run 경계 때문에 한 단어가 갈라지는 대표적인 경우만 복원한다.
    compact = re.sub(
        r"\b입\s+주자모집공고일\b",
        "입주자모집공고일",
        compact,
    )
    compact = re.sub(r"\b또\s+는\b", "또는", compact)
    compact = re.sub(r"‘\s+", "‘", compact)
    compact = re.sub(r"\s+’", "’", compact)
    compact = re.sub(r"\(\s+", "(", compact)
    compact = re.sub(r"\s+\)", ")", compact)

    # 상위 자격 번호만 의미 단위의 시작으로 본다.
    # intro 안의 '①-㉮와', '②～⑤'는 뒤에 조사/범위기호가 붙으므로 매치되지 않고,
    # 실제 조건 제목인 '①-㉮ (대학생)', '② 혼인...'만 매치된다.
    condition_marker = re.compile(
        r"(?<!\S)"
        r"[①②③④⑤⑥⑦⑧⑨⑩➀➁➂➃➄➅➆➇➈➉]"
        r"(?:\s*-\s*[㉮㉯㉰㉱㉲㉳㉴㉵㉶㉷])?"
        r"(?=\s|\()"
    )
    markers = list(condition_marker.finditer(compact))

    details: list[str] = []
    seen: set[str] = set()

    def _append(value: str, *, max_length: int = 1200) -> None:
        cleaned = re.sub(r"\s+", " ", _clean_text(value)).strip(" ,;·")
        if not cleaned or _is_standalone_condition_number(cleaned):
            return

        normalized = _normalized_match_text(cleaned)
        if not normalized:
            return

        # 상세 신청자격에 들어오면 안 되는 선정/순위/소득·자산 블록 방어.
        if any(
            token in normalized
            for token in (
                "소득요건",
                "소득기준",
                "총자산요건",
                "총자산기준",
                "자산요건",
                "자산기준",
                "월평균소득금액",
                "완화요건금회적용",
                "일반공급순위",
                "경쟁시입주자선정기준",
                "우선추첨후추가공급대상자",
                "계층구분없이통합추첨",
            )
        ):
            return

        if normalized in seen:
            return
        seen.add(normalized)

        if len(cleaned) > max_length:
            shortened = cleaned[:max_length].rstrip(" ,;/")
            last_space = shortened.rfind(" ")
            if last_space >= max_length - 160:
                shortened = shortened[:last_space].rstrip(" ,;/")
            cleaned = shortened + "…"

        details.append(cleaned)

    if markers:
        intro = compact[:markers[0].start()].strip(" ,;")

        # 대학생/청년은 상단 summary에서 공통 문장을 이미 보여주므로
        # 사용자가 요청한 실제 계층 조건부터 시작한다.
        # 산업단지 근로자/신혼부부/고령자는 첫 번호 앞의 계층 정의 자체가
        # 자격 판단에 중요하므로 intro도 유지한다.
        if code in {
            "industrial_worker",
            "newlywed_single_parent",
            "senior",
        }:
            _append(intro, max_length=1600)

        for index, condition in enumerate(markers):
            end_index = (
                markers[index + 1].start()
                if index + 1 < len(markers)
                else len(compact)
            )
            _append(
                compact[condition.start():end_index],
                max_length=1600,
            )
    else:
        # 번호 체계가 없는 고령자 등은 소득요건 전까지의 전체 공급대상자
        # 문장을 하나의 상세조건으로 보존한다.
        _append(compact, max_length=1600)

    if details:
        return details[:8]

    sentence = _extract_supply_target_sentence(text_value, code=code)
    return [sentence] if sentence else []

def _happyhouse_group_details_quality(
    code: str,
    details: list[str],
) -> int:
    """행복주택 계층 상세조건 후보의 품질을 비교한다.

    Section 트리가 일부만 잡힌 경우에는 ``3-x`` 본문보다 뒤의
    일반공급 순위/경쟁기준이 같은 subtree에 섞일 수 있다. 반대로
    문서 전체 text/search_text에는 실제 ``■ 공급대상자`` 블록이 온전히
    남아 있는 경우가 많다. 이 함수는 두 후보 중 실제 공급대상자 조건이
    더 충실한 쪽을 선택하기 위한 점수만 계산한다.
    """
    if not details:
        return -1

    cleaned_details = [
        re.sub(r"\s+", " ", _clean_text(detail)).strip()
        for detail in details
        if _clean_text(detail)
    ]
    if not cleaned_details:
        return -1

    joined = " ".join(cleaned_details)
    normalized = _normalized_match_text(joined)
    if not normalized:
        return -1

    forbidden = (
        "일반공급순위",
        "경쟁시입주자선정기준",
        "우선추첨후추가공급대상자",
        "계층구분없이통합추첨",
        "선정순서",
        "선정방법",
    )
    if any(token in normalized for token in forbidden):
        return -1

    # 소득/자산 블록은 상세 자격 카드의 종료 경계다.
    # 실제 추출값 안에 남아 있으면 낮은 품질로 본다.
    if any(
        token in normalized
        for token in (
            "소득요건배제",
            "소득요건적용",
            "총자산요건",
            "월평균소득금액",
        )
    ):
        return -1

    score = min(len(joined), 3000) + len(cleaned_details) * 250

    required_tokens: dict[str, tuple[str, ...]] = {
        "college_student": (
            "대학생",
            "취업준비생",
            "혼인중이아닐것",
        ),
        "youth": (
            "19세이상39세이하",
            "사회초년생",
            "혼인중이아닐것",
        ),
        "industrial_worker": (
            "산업단지",
            "재직중",
        ),
        "newlywed_single_parent": (
            "신혼부부",
            "예비신혼부부",
            "한부모가족",
        ),
        "senior": (
            "65세이상",
        ),
    }

    for token in required_tokens.get(code, ()):
        if token in normalized:
            score += 1200

    return score


def _extract_happyhouse_groups_from_text_value(
    text_value: str,
) -> list[dict[str, Any]]:
    """하나의 연속 텍스트에서 행복주택 3-1~3-5 자격 블록을 직접 추출한다.

    Structure의 Section 계층이 HWP/HWPX 제목/표 경계 때문에 끊겨도,
    원문 text/search_text에 ``3-1. 대학생 계층`` ~ ``3-5. 고령자``가
    남아 있으면 각 heading 사이를 독립 범위로 잘라 오염을 방지한다.
    """
    text_value = _clean_text(text_value)
    if not text_value:
        return []

    heading_pattern = re.compile(
        r"(?P<num>3\s*-\s*[1-5])\s*[.]?\s*"
        r"(?P<label>"
        r"대학생\s*계층|"
        r"청년\s*계층|"
        r"산업단지\s*근로자\s*계층|"
        r"신혼부부\s*[·ㆍ]?\s*한부모가족\s*계층|"
        r"고령자(?:\s*계층)?"
        r")",
        re.IGNORECASE,
    )
    headings = list(heading_pattern.finditer(text_value))
    if not headings:
        return []

    candidates: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        number = re.sub(r"\s+", "", heading.group("num"))
        label_text = _clean_text(heading.group("label"))
        spec = _happyhouse_group_spec_from_title(
            f"{number}. {label_text}"
        )
        if spec is None:
            continue

        code, label = spec
        start_index = heading.end()
        end_index = (
            headings[index + 1].start()
            if index + 1 < len(headings)
            else len(text_value)
        )
        section_text = text_value[start_index:end_index]

        details = _extract_supply_target_details(
            section_text,
            code=code,
        )
        if not details:
            continue

        candidates.append(
            {
                "code": code,
                "label": label,
                "details": details,
            }
        )

    return candidates


def _extract_happyhouse_eligibility_target_groups_from_structure(
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    행복주택 3-1~3-5 계층 Section의 ``■ 공급대상자`` 자격조건을
    다음 소득/자산 조건 직전까지 추출해 프론트 ``target_groups`` 형식으로 반환한다.

    중요:
    - Section 트리에서 3개 이상 찾았다고 조기 반환하지 않는다.
      실제 문서에는 3-4 신혼부부·한부모가족처럼 별도 Section이 뒤에 더 있을 수 있다.
    - Section subtree 후보와 문서 전체 연속 텍스트 후보를 모두 비교해서
      실제 ``■ 공급대상자`` 조건이 더 충실한 후보를 계층별로 선택한다.
    """
    best_by_code: dict[str, dict[str, Any]] = {}
    best_score_by_code: dict[str, int] = {}

    def _consider(group: dict[str, Any]) -> None:
        code = str(group.get("code") or "")
        label = _clean_text(group.get("label"))
        details = group.get("details")
        if not code or not label or not isinstance(details, list):
            return

        cleaned_details = [
            re.sub(r"\s+", " ", _clean_text(value)).strip()
            for value in details
            if _clean_text(value)
        ]
        score = _happyhouse_group_details_quality(
            code,
            cleaned_details,
        )
        if score < 0:
            return

        if score <= best_score_by_code.get(code, -1):
            return

        best_score_by_code[code] = score
        best_by_code[code] = {
            "code": code,
            "label": label,
            "details": cleaned_details,
        }

    # 1) Structure가 정확히 계층 Section을 만든 경우 가장 먼저 후보로 사용한다.
    for section, _ in _iter_sections(structure.get("sections")):
        title = _clean_text(
            section.get("title")
            or section.get("normalized_title")
        )
        spec = _happyhouse_group_spec_from_title(title)
        if spec is None:
            continue

        code, label = spec
        details = _extract_supply_target_details(
            _section_subtree_text(section),
            code=code,
        )
        if details:
            _consider(
                {
                    "code": code,
                    "label": label,
                    "details": details,
                }
            )

    # 2) Section 경계가 불완전한 HWP/HWPX를 위해 실제 문서 콘텐츠를
    #    연속 텍스트로 다시 검사한다. 기존 코드처럼 3개만 찾고 반환하지 않고
    #    3-1~3-5를 끝까지 보면서 누락 계층을 채우고 잘못된 후보도 교체한다.
    content_candidates = _deduplicate_texts(
        [
            *_collect_structure_texts(structure),
            *_collect_content_text_candidates(structure),
        ]
    )

    # 긴 text/search_text가 먼저 오도록 하되, 개별 후보도 모두 확인한다.
    # 전체 join은 문단이 여러 node에 나뉜 구조에서 최후의 fallback 역할을 한다.
    combined_all = "\n".join(content_candidates)
    text_candidates = list(content_candidates)
    if combined_all:
        text_candidates.append(combined_all)
    text_candidates = _deduplicate_texts(text_candidates)
    text_candidates.sort(key=len, reverse=True)

    for text_value in text_candidates:
        normalized = _normalized_match_text(text_value)
        if not any(
            token in normalized
            for token in (
                "3-1.대학생계층",
                "3-1대학생계층",
                "3-2.청년계층",
                "3-2청년계층",
                "3-3.산업단지근로자계층",
                "3-3산업단지근로자계층",
                "3-4.신혼부부·한부모가족계층",
                "3-4신혼부부·한부모가족계층",
                "3-5.고령자",
                "3-5고령자",
            )
        ):
            continue

        for group in _extract_happyhouse_groups_from_text_value(text_value):
            _consider(group)

    order = {
        code: index
        for index, (code, _, _) in enumerate(
            HAPPYHOUSE_ELIGIBILITY_GROUP_SPECS
        )
    }
    groups = list(best_by_code.values())
    groups.sort(
        key=lambda group: order.get(str(group.get("code") or ""), 999)
    )
    return groups

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

    # 해당 자격 Section과 가까운 하위 Section만 범위로 사용한다.
    # 너무 깊은 descendant까지 재귀 탐색하면 뒤쪽 유의사항/재계약
    # Section의 '고령자', '청년' 등이 현재 신청자격 그룹으로 섞일 수 있다.
    scoped_children: list[dict[str, Any]] = []
    direct_children = target_section.get("children")

    if isinstance(direct_children, list):
        for child in direct_children:
            if not isinstance(child, dict):
                continue

            scoped_children.append(child)

            grandchildren = child.get("children")
            if not isinstance(grandchildren, list):
                continue

            for grandchild in grandchildren:
                if isinstance(grandchild, dict):
                    scoped_children.append(grandchild)

    scoped_parts: list[str] = []
    root_text = _section_direct_text(target_section)
    if root_text:
        scoped_parts.append(root_text)

    for child in scoped_children:
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
    #
    # 국민/영구임대 공고는 행복주택처럼 "청년계층" 등만
    # 상세 자격의 제목으로 쓰지 않고, "■ 성년자",
    # "■ 무주택세대구성원"을 실제 신청자격 하위 항목으로
    # 사용하는 경우가 많다. 이 두 항목도 문서에 명시된
    # 경우에만 상세 자격으로 구조화한다.
    label_patterns: tuple[tuple[str, str], ...] = (
        (
            "eligibility_exception",
            r"(?:주요\s*)?(?:신청|입주)?\s*자격\s*"
            r"(?:예외(?:\s*및\s*특례)?|특례)(?:\s*조건)?",
        ),
        ("no_home_household", r"무주택\s*세대구성원"),
        ("adult", r"성년자"),
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

    # ① 신혼부부 / 3-1 한부모가족 / 1. 청년뿐 아니라
    # "■ 성년자", "■ 무주택세대구성원"처럼 LH 공고문에서
    # 실제 하위 자격 제목으로 사용하는 불릿도 시작점으로 인정한다.
    start_pattern = re.compile(
        r"(?P<marker>(?:[■◆●▪□]|[①②③④⑤⑥⑦⑧⑨⑩](?:-\d+)?|\d+(?:-\d+)?[.)]?))\s*"
        + label_regex
        + r"\s*[:：]?\s*",
        re.IGNORECASE,
    )

    matches = list(start_pattern.finditer(section_text))

    groups: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    def _compact_detail_for_ui(
        value: str,
        *,
        code: str,
        max_length: int = 180,
    ) -> str:
        """
        신청자격 자세히 보기용 상세 내용을 UI에 적당한 길이로 정리한다.

        원문에 없는 문장을 새로 만들지 않고, LH 공고에서 자주 사용하는
        문장/불릿/예외 표현 경계에서 우선 분리한 뒤 핵심 앞부분만 유지한다.
        프론트는 이 값을 그대로 표시하는 것을 전제로 한다.
        """
        cleaned = re.sub(
            r"\s+",
            " ",
            _clean_text(value),
        ).strip(" ,;·")

        if not cleaned:
            return ""

        # LH 공고에서 실제로 자주 보이는 의미 경계를 기준으로 분리한다.
        # 단순 글자 수 절단보다 의미 손실을 줄이기 위한 처리다.
        split_pattern = re.compile(
            r"(?<=[.!?。])\s+"
            r"|\s*[;；]\s*"
            r"|(?=※)"
            r"|(?=[①②③④⑤⑥⑦⑧⑨⑩])"
            r"|(?=\d+(?:-\d+)?[.)]\s*)"
            r"|(?=[가-하][.)]\s*)"
            r"|(?=단,\s*)"
            r"|(?=다만,\s*)"
            r"|(?=단\s+[^,]{0,15},)"
        )

        parts = [
            part.strip(" ,;·")
            for part in split_pattern.split(cleaned)
            if part.strip(" ,;·")
        ]

        if not parts:
            return _compact_summary(cleaned, max_length)

        # 불필요하게 부가적인 예외/주의 문구는 후순위로 두고,
        # 첫 핵심 조건을 중심으로 최대 2개 의미 단위만 유지한다.
        preferred: list[str] = []
        deferred: list[str] = []

        for part in parts:
            normalized_part = _normalized_match_text(part)
            if any(
                token in normalized_part
                for token in (
                    "※",
                    "유의",
                    "주의",
                    "자세한내용",
                    "확인하시기바랍니다",
                )
            ):
                deferred.append(part)
            else:
                preferred.append(part)

        ordered_parts = preferred + deferred

        selected: list[str] = []
        current_length = 0

        for part in ordered_parts:
            separator_length = 1 if selected else 0
            next_length = current_length + separator_length + len(part)

            if selected and next_length > max_length:
                break

            # 첫 파트 자체가 너무 길면 문장 중간 강제 절단 대신
            # max_length 내에서 공백 경계를 최대한 활용한다.
            if not selected and len(part) > max_length:
                shortened = part[:max_length].rstrip(" ,;/")
                last_space = shortened.rfind(" ")
                if last_space >= int(max_length * 0.7):
                    shortened = shortened[:last_space].rstrip(" ,;/")
                return shortened + "…"

            selected.append(part)
            current_length = next_length

            if len(selected) >= 2:
                break

        compact = " ".join(selected).strip()

        if not compact:
            compact = cleaned

        return _compact_summary(compact, max_length)

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

        compact_detail = _compact_detail_for_ui(
            detail,
            code=code,
        )

        if not compact_detail:
            return

        seen_codes.add(code)
        groups.append(
            {
                "code": code,
                "label": re.sub(r"\s+", " ", label).strip(),
                "details": [compact_detail],
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
        for child in scoped_children:
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
                        r"^[■◆●▪□①②③④⑤⑥⑦⑧⑨⑩\d\-.)\s]+",
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
        "조회결과",
        "부적격",
        "탈락",
        "재계약",
        "갱신계약",
        "주택도시기금",
        "작성요령",
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



def _build_income_asset_summary_from_structure(
    structure: dict[str, Any],
) -> str:
    """
    실제 입주자격/소득기준 영역의 적용 기준을 우선 요약한다.

    특히 일반 매입임대처럼
      - 1순위 장애인: 월평균소득 70% 이하
      - 2순위: 월평균소득 100% 이하
    가 명시된 경우, 뒤쪽 유의사항의 '소득초과 시 임대료 인상' 문장보다
    실제 신청 시 적용되는 기준을 우선한다.
    """
    texts = _collect_structure_texts(structure)
    combined = re.sub(
        r"\s+",
        " ",
        _clean_text("\n".join(texts)),
    )

    if not combined:
        return ""

    parts: list[str] = []

    # 1순위 장애인 소득 기준
    disability_match = re.search(
        r"장애인.{0,260}?월평균소득.{0,180}?(?P<pct>\d{1,3})\s*%\s*이하",
        combined,
        re.IGNORECASE,
    )
    if disability_match:
        parts.append(
            f"1순위 장애인: 월평균소득 {disability_match.group('pct')}% 이하"
        )

    # 2순위 소득 기준
    second_match = re.search(
        r"2\s*순위.{0,260}?월평균소득.{0,180}?(?P<pct>\d{1,3})\s*%\s*이하",
        combined,
        re.IGNORECASE,
    )
    if second_match:
        parts.append(
            f"2순위: 월평균소득 {second_match.group('pct')}% 이하"
        )

    if parts:
        return " · ".join(_deduplicate_texts(parts))

    # 위처럼 순위별 구조가 아니더라도 '소득보유기준/소득기준' 영역의
    # 실제 기준 문장을 찾는다. 갱신·재계약·초과 할증 문장은 제외한다.
    candidates: list[tuple[int, int, str]] = []
    negative_keywords = (
        "재계약",
        "갱신계약",
        "임대료",
        "임대보증금",
        "할증",
        "퇴거",
        "유의사항",
    )

    for index, text_value in enumerate(texts):
        for raw_line in text_value.splitlines():
            line = re.sub(r"\s+", " ", _clean_text(raw_line)).strip()
            if not line:
                continue

            normalized = _normalized_match_text(line)
            if "소득" not in normalized:
                continue
            if not (
                "이하" in normalized
                or re.search(r"\d{1,3}\s*%", line)
            ):
                continue
            if any(
                _normalized_match_text(keyword) in normalized
                for keyword in negative_keywords
            ):
                continue

            score = 0
            if "소득보유기준" in normalized or "소득기준" in normalized:
                score += 60
            if "월평균소득" in normalized:
                score += 40
            if re.search(r"\d{1,3}\s*%\s*이하", line):
                score += 40
            if "해당세대" in normalized:
                score += 20

            candidates.append(
                (
                    score,
                    -index,
                    _compact_summary(line, 200),
                )
            )

    if not candidates:
        return ""

    candidates.sort(reverse=True)
    return candidates[0][2]


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
            "재계약": 80,
            "갱신계약": 80,
            "임대료": 60,
            "임대보증금": 60,
            "할증": 60,
            "퇴거": 60,
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


def _collect_content_text_candidates(
    structure: dict[str, Any],
) -> list[str]:
    """
    핵심정보 fallback에서 사용할 실제 문서 콘텐츠 문자열을 수집한다.

    기존 _collect_structure_texts()의 text/search_text는 그대로 유지하고,
    일부 HWPX 구조에서 자격/공급 문구가 title, raw_text, value 또는
    table cell에만 남는 경우를 보완한다. 메타데이터 경로/id 등은 수집하지 않는다.
    """
    result: list[str] = []
    seen: set[str] = set()

    content_keys = (
        "text",
        "search_text",
        "title",
        "normalized_title",
        "raw_text",
        "value",
        "content",
    )

    for node in _iter_nested_dicts(structure):
        for key in content_keys:
            value = node.get(key)
            if not isinstance(value, str):
                continue

            cleaned = _clean_text(value)
            if not cleaned:
                continue

            normalized = _normalized_match_text(cleaned)
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            result.append(cleaned)

        cells = node.get("cells")
        if isinstance(cells, list):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                for key in ("text", "value"):
                    value = cell.get(key)
                    if not isinstance(value, str):
                        continue
                    cleaned = _clean_text(value)
                    if not cleaned:
                        continue
                    normalized = _normalized_match_text(cleaned)
                    if not normalized or normalized in seen:
                        continue
                    seen.add(normalized)
                    result.append(cleaned)

    for section, _ in _iter_sections(structure.get("sections")):
        for value in (
            section.get("title"),
            section.get("normalized_title"),
            _section_direct_text(section),
        ):
            if not isinstance(value, str):
                continue
            cleaned = _clean_text(value)
            if not cleaned:
                continue
            normalized = _normalized_match_text(cleaned)
            if not normalized or normalized in seen:
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


def _normalize_eligibility_groups_for_ui(
    groups: list[dict[str, Any]],
    *,
    max_length: int = 180,
) -> list[dict[str, Any]]:
    """모든 target_groups 추출 경로에 동일한 UI 길이 정책을 적용한다."""
    normalized_groups: list[dict[str, Any]] = []

    for group in groups:
        if not isinstance(group, dict):
            continue

        details = group.get("details")
        if not isinstance(details, list):
            continue

        group_code = str(group.get("code") or "")

        # '성년자'는 이미 명시적 제목 범위에서 대표 설명 + 예외 조건을
        # 의미 단위별로 정확히 분리해서 가져온다. 일반 fallback용 숫자/문장
        # 재분리 정규식을 다시 적용하면 '만 19세' 같은 숫자까지 잘릴 수
        # 있으므로 성년자 그룹은 여기서 그대로 보존한다.
        if group_code == "adult":
            adult_details: list[str] = []
            adult_seen: set[str] = set()
            for detail in details:
                cleaned = re.sub(r"\s+", " ", _clean_text(detail)).strip(" ,;·")
                if not cleaned:
                    continue
                key = _normalized_match_text(cleaned)
                if not key or key in adult_seen:
                    continue
                adult_seen.add(key)
                if len(cleaned) > 520:
                    shortened = cleaned[:520].rstrip(" ,;/")
                    last_space = shortened.rfind(" ")
                    if last_space >= 420:
                        shortened = shortened[:last_space].rstrip(" ,;/")
                    cleaned = shortened + "…"
                adult_details.append(cleaned)
                if len(adult_details) >= 4:
                    break

            if adult_details:
                normalized_group = dict(group)
                normalized_group["details"] = adult_details
                normalized_groups.append(normalized_group)
            continue

        max_detail_count = 3
        group_max_length = max_length

        compact_details: list[str] = []
        seen: set[str] = set()

        for detail in details:
            cleaned = re.sub(r"\s+", " ", _clean_text(detail)).strip(" ,;·")
            if not cleaned:
                continue

            # fallback 경로에서도 너무 긴 원문이 그대로 내려가지 않도록
            # 동일한 분리 기준을 사용한다.
            parts = [
                part.strip(" ,;·")
                for part in re.split(
                    r"(?<=[.!?。])\s+"
                    r"|\s*[;；]\s*"
                    r"|(?=※)"
                    r"|(?=[①②③④⑤⑥⑦⑧⑨⑩])"
                    r"|(?=\d+(?:-\d+)?[.)]\s*)"
                    r"|(?=[가-하][.)]\s*)"
                    r"|(?=단,\s*)"
                    r"|(?=다만,\s*)",
                    cleaned,
                )
                if part.strip(" ,;·")
            ]

            compact = ""
            current_length = 0
            selected: list[str] = []

            for part in parts or [cleaned]:
                next_length = current_length + (1 if selected else 0) + len(part)
                if selected and next_length > group_max_length:
                    break
                if not selected and len(part) > group_max_length:
                    shortened = part[:group_max_length].rstrip(" ,;/")
                    last_space = shortened.rfind(" ")
                    if last_space >= int(group_max_length * 0.7):
                        shortened = shortened[:last_space].rstrip(" ,;/")
                    compact = shortened + "…"
                    break
                selected.append(part)
                current_length = next_length
                if len(selected) >= 2:
                    break

            if not compact:
                compact = " ".join(selected).strip()

            if not compact:
                continue

            key = _normalized_match_text(compact)
            if key in seen:
                continue

            seen.add(key)
            compact_details.append(compact)

            # 일반 fallback 그룹은 최대 3개, 성년자 그룹은 예외 3개까지
            # 모두 보여주기 위해 최대 4개를 유지한다.
            if len(compact_details) >= max_detail_count:
                break

        if not compact_details:
            continue

        normalized_group = dict(group)
        normalized_group["details"] = compact_details
        normalized_groups.append(normalized_group)

    return normalized_groups



def _extract_adult_eligibility_group_from_structure(
    structure: dict[str, Any],
) -> dict[str, Any] | None:
    """
    ``■ 성년자``가 독립된 신청자격 하위 제목으로 존재하는 LH 공고에서
    다음 ``■`` 제목 직전까지의 실제 자격 설명을 상세 카드용으로 추출한다.

    행복주택의 ``3-x 계층 -> ■ 공급대상자`` 패턴과 달리,
    50년 공공임대/국민임대 등의 공고는 다음처럼 구성되는 경우가 있다.

        4. 신청자격
        ■ 성년자
        「민법」상 미성년자 ...
        - 예외 1
        - 예외 2
        - 예외 3
        ■ 무주택세대구성원

    이 경우 기존 계층형 추출기만으로는 ``성년자`` 제목만 남고 본문이
    비거나 지나치게 짧아질 수 있으므로, 명시적 제목 범위를 직접 읽는다.
    """
    content_candidates = _deduplicate_texts(
        [
            *_collect_structure_texts(structure),
            *_collect_content_text_candidates(structure),
        ]
    )
    if not content_candidates:
        return None

    # 긴 실제 본문 후보를 우선한다. 동일 내용의 search_text/text가
    # 여러 번 존재해도 최종적으로 가장 충실한 후보 하나만 선택한다.
    content_candidates.sort(key=len, reverse=True)

    best_details: list[str] = []
    best_score = -1

    heading_pattern = re.compile(
        r"■\s*성년자\s*[:：]?",
        re.IGNORECASE,
    )

    def _clean_detail(value: str, *, max_length: int = 520) -> str:
        cleaned = re.sub(r"\s+", " ", _clean_text(value)).strip(" •▪-*\t\n")
        if not cleaned:
            return ""

        # 신청자격 상세는 원문을 보존하되 UI 폭을 무한히 늘리지 않는다.
        # 문장 전체가 긴 경우에만 공백 경계에서 넉넉하게 제한한다.
        if len(cleaned) > max_length:
            shortened = cleaned[:max_length].rstrip(" ,;/")
            last_space = shortened.rfind(" ")
            if last_space >= int(max_length * 0.8):
                shortened = shortened[:last_space].rstrip(" ,;/")
            cleaned = shortened + "…"
        return cleaned

    for text_value in content_candidates:
        if "성년자" not in text_value or "■" not in text_value:
            continue

        heading = heading_pattern.search(text_value)
        if not heading:
            continue

        # 성년자 제목 다음의 '다음 ■ 제목'까지만 현재 상세조건으로 본다.
        # 이 문서에서는 다음 제목이 ■ 무주택세대구성원이다.
        next_heading = re.search(
            r"■\s*(?!성년자\b)",
            text_value[heading.end():],
        )
        if next_heading:
            body = text_value[
                heading.end():heading.end() + next_heading.start()
            ]
        else:
            body = text_value[heading.end():]

        body = _clean_text(body)
        if not body:
            continue

        details: list[str] = []
        seen: set[str] = set()

        def _append(value: str) -> None:
            cleaned = _clean_detail(value)
            if not cleaned:
                return
            normalized = _normalized_match_text(cleaned)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            details.append(cleaned)

        # 첫 설명문: 미성년자는 원칙적으로 신청 불가하되 예외가 있음을
        # 알리는 문장을 통째로 보존한다.
        intro_match = re.search(
            r"「?민법」?\s*상\s*미성년자\s*\([^)]*\)는\s*"
            r"공급\s*신청할\s*수\s*없습니다\.?\s*"
            r"단,?\s*아래의\s*어느\s*하나에\s*해당하는\s*경우\s*"
            r"미성년자도\s*공급\s*신청\s*가능합니다\.?",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if intro_match:
            _append(intro_match.group(0))
            remainder = body[intro_match.end():]
        else:
            remainder = body

        # HWPX 파싱 결과에서는 예외 조건이 보통 '-'로 시작하는 별도 줄이다.
        # 먼저 개행 기반으로 정확히 수집한다.
        lines = [
            _clean_text(line).strip()
            for line in remainder.splitlines()
            if _clean_text(line)
        ]
        bullet_buffer = ""
        for line in lines:
            if re.match(r"^[\-–—•▪]\s*", line):
                if bullet_buffer:
                    _append(bullet_buffer)
                bullet_buffer = re.sub(
                    r"^[\-–—•▪]\s*",
                    "",
                    line,
                ).strip()
            elif bullet_buffer:
                # 줄바꿈으로 하나의 bullet이 나뉜 경우 이어 붙인다.
                bullet_buffer += " " + line
        if bullet_buffer:
            _append(bullet_buffer)

        # search_text처럼 개행이 유실된 후보를 위한 fallback.
        if len(details) < 4:
            compact = re.sub(r"\s+", " ", remainder).strip()
            if compact:
                fallback_bullets = re.findall(
                    r"(?:^|\s)[\-–—]\s*"
                    r"(.+?)"
                    r"(?=(?:\s[\-–—]\s*)|$)",
                    compact,
                    re.DOTALL,
                )
                for bullet in fallback_bullets:
                    _append(bullet)

        # 명시적인 intro를 못 찾은 특이 형식이라도 성년자 바로 아래
        # 첫 문단은 버리지 않는다.
        if not details:
            first_lines = lines[:4]
            for line in first_lines:
                _append(line)

        # 성년자 카드에는 대표 설명 + 예외 3개 정도가 가장 적절하다.
        # 지나친 주변 문구 유입을 막기 위해 최대 4개로 제한한다.
        details = details[:4]
        if not details:
            continue

        joined = " ".join(details)
        normalized_joined = _normalized_match_text(joined)
        score = len(details) * 100 + min(len(joined), 1000)
        if "미성년자" in normalized_joined:
            score += 300
        if "자녀가있는세대주" in normalized_joined:
            score += 120
        if "직계존속" in normalized_joined:
            score += 120
        if "외국인부모" in normalized_joined:
            score += 120

        if score > best_score:
            best_score = score
            best_details = details

    if not best_details:
        return None

    return {
        "code": "adult",
        "label": "성년자",
        "details": best_details,
    }


def _merge_preferred_eligibility_group(
    groups: list[dict[str, Any]],
    preferred: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """같은 code가 있으면 더 정확한 명시적 제목 기반 그룹으로 교체한다."""
    if not preferred:
        return groups

    preferred_code = str(preferred.get("code") or "")
    if not preferred_code:
        return groups

    result: list[dict[str, Any]] = []
    replaced = False

    for group in groups:
        if not isinstance(group, dict):
            continue
        if str(group.get("code") or "") == preferred_code:
            if not replaced:
                result.append(preferred)
                replaced = True
            continue
        result.append(group)

    if not replaced:
        # 성년자 같은 공통 선행 자격은 다른 상세조건보다 먼저 보여준다.
        result.insert(0, preferred)

    return result

def _extract_common_only_eligibility_conditions_from_structure(
    structure: dict[str, Any],
    *,
    summary: str,
) -> list[str]:
    """
    특정 공급계층이 없는 공통 자격형 공고의 상세 신청조건을 추출한다.

    예: 든든전세/일부 매입임대 공고처럼
        ■ 입주자격
        • 공고일 현재 무주택세대구성원 ...
        * 신청자격은 입주 시까지 유지 ...
        ※ 모집권역 ...
        ■ 입주자 선정기준
    구조를 갖는 경우.

    이런 공고의 '신생아 가구 여부', '자녀 수' 등은 신청자격이 아니라
    선정 배점이므로 target_groups로 보내지 않는다.
    """
    normalized_summary = _normalized_match_text(summary)

    # summary 자체가 대학생/청년/신혼부부 등 실제 공급계층을 명시한다면
    # 공통 자격형으로 처리하지 않는다.
    explicit_group_tokens = (
        "대학생",
        "취업준비생",
        "청년",
        "사회초년생",
        "산업단지근로자",
        "신혼부부",
        "예비신혼부부",
        "한부모가족",
        "고령자",
        "주거급여수급자",
        "장애인",
    )
    if any(
        _normalized_match_text(token) in normalized_summary
        for token in explicit_group_tokens
    ):
        return []

    content_candidates = _deduplicate_texts(
        _collect_content_text_candidates(structure)
    )
    if not content_candidates:
        return []

    combined = "\n".join(content_candidates)
    compact_combined = re.sub(r"[ \t]+", " ", combined)

    # 명시적인 '입주자격 -> 입주자 선정기준' 블록이 있는 문서를
    # 공통 자격형의 가장 강한 신호로 사용한다.
    block_match = re.search(
        r"■\s*입주자격\s*(?P<body>.*?)"
        r"(?=■\s*입주자\s*선정기준|■\s*당첨자\s*및\s*예비자\s*선정|$)",
        compact_combined,
        re.IGNORECASE | re.DOTALL,
    )
    if not block_match:
        return []

    block = block_match.group("body")
    normalized_block = _normalized_match_text(block)

    if not any(
        token in normalized_block
        for token in (
            "무주택세대구성원",
            "무주택자",
            "모집권역",
            "거주하고있는모집권역",
        )
    ):
        return []

    result: list[str] = []
    seen: set[str] = set()

    def _append(value: str, *, max_length: int = 520) -> None:
        cleaned = re.sub(r"\s+", " ", _clean_text(value)).strip(" •*※-\t\n")
        if not cleaned:
            return

        # 선정/배점 항목은 신청자격 상세가 아니다.
        normalized = _normalized_match_text(cleaned)

        # 상단 카드 summary와 사실상 같은 문장은 상세보기에서 중복하지 않는다.
        normalized_summary_local = _normalized_match_text(summary)
        if (
            normalized_summary_local
            and (
                normalized == normalized_summary_local
                or normalized in normalized_summary_local
                or normalized_summary_local in normalized
            )
        ):
            return

        if any(
            token in normalized
            for token in (
                "평가항목",
                "평가요소",
                "배점",
                "신생아가구여부",
                "자녀의수",
                "총점이높은순",
                "동일점수",
                "추첨",
            )
        ):
            return

        # 긴 공통조건은 프론트가 그대로 표시하므로 의미가 깨지지 않는
        # 공백 경계에서만 넉넉하게 제한한다. 기존 180자 강제 절단은 하지 않는다.
        if len(cleaned) > max_length:
            shortened = cleaned[:max_length].rstrip(" ,;/")
            last_space = shortened.rfind(" ")
            if last_space >= int(max_length * 0.8):
                shortened = shortened[:last_space].rstrip(" ,;/")
            cleaned = shortened + "…"

        key = _normalized_match_text(cleaned)
        if not key or key in seen:
            return
        seen.add(key)
        result.append(cleaned)

    # 상단 summary에서 이미 보여주는 대표문장 외의 세부 조건을 우선한다.
    units = [
        part
        for part in re.split(
            r"(?=[•※*]\s*)|(?=☞\s*)",
            block,
        )
        if _clean_text(part)
    ]

    for unit in units:
        normalized = _normalized_match_text(unit)
        if any(
            token in normalized
            for token in (
                "신청자격은입주자모집공고일부터입주시까지",
                "모집권역",
                "거주지모집권역이외지역에신청",
            )
        ):
            _append(unit)

    # '무주택세대구성원'의 의미는 공고 하단 설명까지 찾아 상세보기에서
    # 확인할 수 있도록 한다. 단순 '무주택자' 한 단어만 보여주지 않는다.
    no_home_match = re.search(
        r"※\s*무주택세대구성원\s*[:：]\s*"
        r"(?P<body>.+?)(?=\n|세대구성원\s*비고|※\s*아래\s*표|$)",
        compact_combined,
        re.IGNORECASE,
    )
    if no_home_match:
        _append(
            "무주택세대구성원: " + no_home_match.group("body"),
            max_length=420,
        )
    elif "무주택세대구성원" in normalized_summary:
        _append("공고일 현재 무주택세대구성원이어야 합니다.")

    # 미성년자 신청 제한도 실제 입주자격 관련 조건이므로, 공고에 있으면
    # 세부조건에 포함한다. 예외 조건은 같은 문장 범위에서 함께 유지한다.
    minor_match = re.search(
        r"※\s*「?민법」?상\s*미성년자\s*\([^)]*\)는\s*"
        r"공급\s*신청할\s*수\s*없습니다\.\s*"
        r"단,\s*다음\s*중\s*하나에\s*해당하는\s*경우에는\s*"
        r"미성년자도\s*공급\s*신청\s*가능합니다\.?",
        compact_combined,
        re.IGNORECASE,
    )
    if minor_match:
        _append(minor_match.group(0), max_length=420)

    # 최소한 '무주택자' 한 단어보다 충분한 상세정보가 있어야
    # 공통 자격형으로 확정한다.
    return result if len(result) >= 2 else []


def _build_eligibility(
    matches: list[dict[str, Any]],
    *,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _build_generic_field(
        "eligibility",
        matches,
    )

    # 먼저 실제 입주자격/신청자격 Section에서 카드 상단 summary를 결정한다.
    summary = ""
    if structure is not None:
        summary = _extract_explicit_eligibility_summary_from_structure(
            structure
        )
        if not summary:
            summary = _build_eligibility_summary_from_structure(structure)
    if not summary:
        summary = _build_eligibility_summary(matches)

    # 행복주택처럼 명시적인 공급계층이 있는 공고는 기존 계층별 카드 사용.
    target_groups: list[dict[str, Any]] = []
    used_happyhouse_groups = False

    if structure is not None:
        target_groups = (
            _extract_happyhouse_eligibility_target_groups_from_structure(
                structure
            )
        )
        used_happyhouse_groups = bool(target_groups)

    # 든든전세처럼 '■ 입주자격'은 공통 자격이고 뒤의 표는 선정 배점인
    # 공고를 별도로 감지한다. 이 경우 배점항목을 target_groups로 오인하지 않는다.
    common_only_conditions: list[str] = []
    if structure is not None and not used_happyhouse_groups:
        common_only_conditions = (
            _extract_common_only_eligibility_conditions_from_structure(
                structure,
                summary=summary,
            )
        )

    if not target_groups and not common_only_conditions and structure is not None:
        target_groups = _extract_eligibility_type_groups_from_structure(
            structure
        )

    if not target_groups and not common_only_conditions and structure is not None:
        target_groups = _extract_eligibility_verification_groups(
            structure
        )

    if not target_groups and not common_only_conditions:
        target_groups = _extract_eligibility_target_groups(matches)

    # 50년 공공임대/국민임대처럼 '■ 성년자'가 독립된 신청자격 하위
    # 제목인 문서는 행복주택 계층 패턴과 다르다. 구조화 결과에 제목만
    # 잡히더라도 실제 본문과 미성년 신청 예외 3개를 명시적 제목 범위에서
    # 다시 추출해 기존 adult 그룹을 보완/교체한다.
    if structure is not None and not used_happyhouse_groups:
        target_groups = _merge_preferred_eligibility_group(
            target_groups,
            _extract_adult_eligibility_group_from_structure(structure),
        )

    target_groups = _filter_eligibility_target_groups_for_summary(
        target_groups,
        summary,
    )

    # 행복주택 공급대상자 대표문장은 이미 범위를 정확히 좁혀 추출했으므로
    # 다시 180자로 자르지 않는다. 공통 자격형 역시 common_conditions에서
    # 넉넉한 길이로 표시하므로 target_groups 압축이 필요 없다.
    if target_groups and not used_happyhouse_groups:
        target_groups = _normalize_eligibility_groups_for_ui(
            target_groups,
            max_length=260,
        )

    if used_happyhouse_groups:
        common_conditions: list[str] = []
    elif common_only_conditions:
        common_conditions = common_only_conditions
    else:
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
            "단지위치",
            "단지 위치",
            "건설위치",
            "건설 위치",
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
        "construction_units",
        (
            "건설호수",
            "건설 호수",
            "건설세대수",
            "건설 세대수",
            "건설세대수(호)",
            "건설 세대수(호)",
        ),
    ),
    (
        "supply_units",
        (
            "공급호수",
            "공급 호수",
            "주택호수",
            "주택 호수",
        ),
    ),
    (
        "recruitment_units",
        (
            "금회모집호수",
            "금회 모집호수",
            "금회 모집 호수",
            "모집호수",
            "모집 호수",
            "모집세대수",
            "모집 세대수",
            "금회모집세대수",
            "금회 모집세대수",
            "금회 모집 세대수",
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
            "기존예비자수",
            "기존 예비자수",
            "기존예비자",
            "기존 예비자",
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
    "construction_units",
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
    *,
    field: str | None = None,
) -> int | None:
    """
    공급 표의 숫자 값을 정수로 변환한다.

    ``건설호수``는 ``15개동 1,114호``처럼 동 수와 호 수가 한 셀에
    함께 들어오는 경우가 있으므로 반드시 ``호`` 바로 앞 숫자를
    우선 사용한다. 그 외 필드는 기존처럼 첫 번째 숫자를 사용한다.
    """
    text_value = _clean_text(
        value
    )

    if not text_value:
        return None

    found = None

    if field == "construction_units":
        construction_matches = list(
            re.finditer(
                r"(?<!\d)(?P<number>\d[\d,]*)\s*호",
                text_value,
            )
        )

        if construction_matches:
            # 한 셀에 여러 숫자가 있더라도 '호' 단위의 마지막 값을
            # 사용한다. 예: '15개동 1,114호' -> 1114
            found = construction_matches[-1]

    if found is None:
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
    실제 공급/모집 표만 인정한다.

    ``건설위치`` 표의 ``단지명 + 건설호수`` 조합은 공급 상세행이 아니므로
    housing_items에 넣지 않는다. 공급호수/모집호수/예비자수 중 하나 이상이
    있어야 실제 공급표로 인정한다.
    """
    fields = set(header_fields.values())

    identity_fields = {
        "complex_name",
        "housing_group",
        "housing_type",
        "location",
    }

    actual_supply_fields = {
        "supply_units",
        "recruitment_units",
        "recruitment_waitlist",
        "waiting_waitlist",
    }

    identity_count = len(fields & identity_fields)
    actual_supply_count = len(fields & actual_supply_fields)

    if identity_count >= 1 and actual_supply_count >= 1:
        return True

    if actual_supply_count >= 2:
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
        "construction_units",
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

    table_index = 0

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

        # 실제 공급정보 표로 확인된 경우에만 고유한 table_index를 부여한다.
        # 뒤의 공급 수량 요약 로직은 이 값을 기준으로 표별 합계를 분리한다.
        table_index += 1

        # -----------------------------------------------
        # header 아래의 실제 data row를 구조화한다.
        # -----------------------------------------------
        # LH 표의 단지명/주택군은 여러 주택형 행에 걸쳐 세로 병합되는
        # 경우가 많다. 병합된 두 번째 이후 행에서는 셀 텍스트가 비어
        # 있으므로, 같은 표 안에서만 직전 값을 이어받는다.
        # 주택형과 공급/모집 수량은 행별 값이므로 절대 이어받지 않는다.
        carried_identity_values: dict[str, str] = {}
        carry_forward_fields = {
            "complex_name",
            "housing_group",
        }

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
                    if (
                        field in carry_forward_fields
                        and field in carried_identity_values
                    ):
                        item[field] = (
                            carried_identity_values[field]
                        )
                    continue

                if field in carry_forward_fields:
                    carried_identity_values[field] = (
                        raw_value
                    )

                if (
                    field
                    in SUPPLY_TABLE_NUMERIC_FIELDS
                ):
                    numeric_value = (
                        _parse_supply_table_integer(
                            raw_value,
                            field=field,
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
                        "construction_units",
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

            # ------------------------------------------------------
            # '소계/합계/총계/계' 행 표시
            # ------------------------------------------------------
            # 일부 LH 표는 소계 문구가 '모집권역'처럼 우리가 구조화하지
            # 않는 열에 위치한다. 이 경우 기존에는 소계 137호 + 상세 137호를
            # 함께 더해 274호처럼 이중 합산될 수 있었다.
            # 원본 행 전체를 확인해 내부 메타데이터로 표시해 둔다.
            total_row_keywords = {
                "소계",
                "합계",
                "총계",
                "계",
            }
            raw_row_labels = {
                re.sub(r"\s+", "", _clean_text(value))
                for value in row_cells.values()
                if _clean_text(value)
            }
            if raw_row_labels & total_row_keywords:
                item["_is_total_row"] = True

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
                "table_index": (
                    table_index
                ),
            }

            rows_result.append(
                item
            )

    return rows_result


def _sum_unique_construction_units(
    rows: list[dict[str, Any]],
    structure: dict[str, Any] | None = None,
) -> int | None:
    """
    문서의 공급 관련 표에서 ``건설호수`` 계열 열만 합산한다.

    핵심 원칙:
    - 예비자수, 모집호수, 주택형, 면적 등 다른 숫자는 절대 합산하지 않는다.
    - ``15개동 1,114호``는 1,114호로 읽는다.
    - ``건설세대수(호)``도 건설호수로 본다.
    - 한 문서에 ``주택단지 개요`` 표와 ``모집대상 주택`` 표가 함께 있으면
      표별 합계를 계산한 뒤 가장 큰 합계만 사용한다.
      이렇게 해야 동일 단지의 건설호수를 서로 다른 표에서 중복합산하지 않는다.

    가능하면 원본 structure table을 직접 읽는다.
    rows는 이전 형식 호환용 fallback으로만 사용한다.
    """

    candidate_totals: list[int] = []

    if isinstance(structure, dict):
        seen_table_signatures: set[tuple[tuple[int, int, str], ...]] = set()

        for node in _iter_nested_dicts(structure):
            cells = node.get("cells")
            if not isinstance(cells, list):
                continue

            table_cells = [
                cell for cell in cells
                if isinstance(cell, dict)
                and isinstance(cell.get("row"), int)
                and isinstance(cell.get("col"), int)
            ]
            if not table_cells:
                continue

            signature = tuple(sorted(
                (
                    int(cell["row"]),
                    int(cell["col"]),
                    _clean_text(cell.get("text")),
                )
                for cell in table_cells
            ))
            if signature in seen_table_signatures:
                continue
            seen_table_signatures.add(signature)

            table_rows: dict[int, dict[int, str]] = {}
            for cell in table_cells:
                text_value = _clean_text(cell.get("text"))
                if not text_value:
                    continue
                table_rows.setdefault(int(cell["row"]), {})[int(cell["col"])] = text_value

            if not table_rows:
                continue

            row_numbers = sorted(table_rows)
            construction_col: int | None = None
            header_end_row: int | None = None

            # LH 표는 헤더가 2~3행으로 나뉠 수 있으므로 최대 3개 연속 행을 합쳐 판정한다.
            for row_pos, row_number in enumerate(row_numbers):
                combined_by_col: dict[int, list[str]] = {}
                max_window = min(row_pos + 3, len(row_numbers))

                for window_pos in range(row_pos, max_window):
                    current_row = row_numbers[window_pos]
                    if current_row - row_number > 2:
                        break

                    for col, cell_text in table_rows[current_row].items():
                        combined_by_col.setdefault(col, []).append(cell_text)

                    for col, values in combined_by_col.items():
                        combined = _normalized_match_text(" ".join(values))
                        if (
                            "건설호수" in combined
                            or "건설세대수" in combined
                        ):
                            construction_col = col
                            header_end_row = current_row
                            break

                    if construction_col is not None:
                        break

                if construction_col is not None:
                    break

            if construction_col is None or header_end_row is None:
                continue

            values: list[int] = []
            seen_values_by_row: set[tuple[int, int]] = set()

            for row_number in row_numbers:
                if row_number <= header_end_row:
                    continue

                raw_value = _clean_text(
                    table_rows[row_number].get(construction_col)
                )
                if not raw_value:
                    continue

                value = _parse_supply_table_integer(
                    raw_value,
                    field="construction_units",
                )
                if not isinstance(value, int) or value <= 0:
                    continue

                row_value_key = (row_number, value)
                if row_value_key in seen_values_by_row:
                    continue
                seen_values_by_row.add(row_value_key)
                values.append(value)

            if values:
                candidate_totals.append(sum(values))

    # structure에서 못 찾은 경우에만 기존 housing_items 기반 값을 fallback으로 사용한다.
    if not candidate_totals:
        table_values: dict[int, list[int]] = {}
        fallback_values: list[int] = []

        for item in rows:
            value = item.get("construction_units")
            if not isinstance(value, int):
                continue

            source = item.get("source")
            table_index = None
            if isinstance(source, dict):
                raw_table_index = source.get("table_index")
                if isinstance(raw_table_index, int):
                    table_index = raw_table_index

            if table_index is None:
                fallback_values.append(value)
            else:
                table_values.setdefault(table_index, []).append(value)

        for values in table_values.values():
            if values:
                candidate_totals.append(sum(values))
        if fallback_values:
            candidate_totals.append(sum(fallback_values))

    if not candidate_totals:
        return None

    return max(candidate_totals)


def _summarize_supply_table_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    공급 표의 수량 필드를 top-level 값으로 요약한다.

    문서 안에 같은 공급정보가 ``주택단지 개요``와 ``모집대상 주택`` 등
    여러 표로 반복될 수 있으므로, 표별로 먼저 합계를 계산한 뒤 동일 metric의
    최댓값을 선택한다. 이렇게 하면 서로 다른 표의 같은 숫자를 중복 합산하는
    문제를 막을 수 있다.

    각 표 내부에서는 ``소계/합계/총계/계`` 행이 있으면 그 행을 우선하고,
    합계 행이 없을 때만 상세 행의 값을 합산한다.
    """
    metric_fields = (
        "supply_units",
        "recruitment_units",
        "recruitment_waitlist",
        "waiting_waitlist",
    )
    total_row_keywords = {
        "소계",
        "합계",
        "총계",
        "계",
    }

    rows_by_table: dict[int, list[dict[str, Any]]] = {}
    fallback_rows: list[dict[str, Any]] = []

    for item in rows:
        source = item.get("source")
        table_index = None
        if isinstance(source, dict):
            raw_table_index = source.get("table_index")
            if isinstance(raw_table_index, int):
                table_index = raw_table_index

        if table_index is None:
            fallback_rows.append(item)
        else:
            rows_by_table.setdefault(table_index, []).append(item)

    groups = list(rows_by_table.values())
    if fallback_rows:
        groups.append(fallback_rows)

    metric_candidates: dict[str, list[int]] = {
        field: []
        for field in metric_fields
    }

    for group in groups:
        total_rows: list[dict[str, Any]] = []
        for item in group:
            labels = [
                _clean_text(item.get(key))
                for key in (
                    "complex_name",
                    "housing_group",
                    "housing_type",
                    "location",
                )
                if _clean_text(item.get(key))
            ]
            if (
                item.get("_is_total_row") is True
                or any(label in total_row_keywords for label in labels)
            ):
                total_rows.append(item)

        for field in metric_fields:
            candidate: int | None = None

            if total_rows:
                total_values = [
                    item.get(field)
                    for item in total_rows
                    if isinstance(item.get(field), int)
                ]
                if total_values:
                    # 합계행이 여러 개면 가장 큰 값을 대표값으로 사용한다.
                    candidate = max(total_values)

            if candidate is None:
                detail_values = [
                    item.get(field)
                    for item in group
                    if isinstance(item.get(field), int)
                ]
                if detail_values:
                    candidate = sum(detail_values)

            if isinstance(candidate, int):
                metric_candidates[field].append(candidate)

    return {
        field: (max(values) if values else None)
        for field, values in metric_candidates.items()
    }


def _supply_title_hint(
    structure: dict[str, Any],
) -> str:
    """
    공급 카드 대표값의 우선순위를 정할 때 사용할 공고 제목 힌트를 만든다.

    본문에 등장하는 "예비입주자" 안내 문구는 제목으로 취급하지 않는다.
    문서 filename과 최상위 Section의 앞부분 제목만 사용한다.
    """
    values: list[str] = []

    document = structure.get("document")
    if isinstance(document, dict):
        filename = _clean_text(document.get("filename"))
        if filename:
            values.append(filename)

    sections = structure.get("sections")
    if isinstance(sections, list):
        for section in sections[:6]:
            if not isinstance(section, dict):
                continue

            title = _clean_text(
                section.get("title")
                or section.get("normalized_title")
            )
            if title:
                values.append(title)

    return "\n".join(_deduplicate_texts(values))


def _supply_prefers_waitlist(
    structure: dict[str, Any],
) -> bool:
    """
    공고 제목이 '예비입주자/예비자 모집' 성격인지 판별한다.

    제목은 우선순위만 정한다. 실제 모집 예비자 수가 없으면
    공급호수/모집호수/건설호수로 자동 fallback한다.
    """
    title_hint = _normalized_match_text(
        _supply_title_hint(structure)
    )

    return bool(
        re.search(
            r"(?:예비입주자|예비자).*모집",
            title_hint,
        )
    )


def _extract_explicit_supply_units_from_structure(
    structure: dict[str, Any],
) -> int | None:
    """
    표에 공급호수 열이 없는 문서에서 명시적인 공급대상 주택 수를 찾는다.

    다음 두 형태를 모두 지원한다.
    1) 한 text 안에 제목과 수량이 같이 있는 경우
       - '입주대상 주택 ... 381호'
    2) Structure에서 제목과 본문이 서로 다른 node로 분리된 경우
       - 이전 text: '입주대상 주택'
       - 현재 text: '경기남부 소재 다가구 등 주택 381호'

    '건설위치 ... 1,088호'처럼 단지 전체 건설호수를 설명하는 문장은
    공급호수 fallback으로 사용하지 않는다.
    """
    candidates: list[tuple[int, int, int]] = []

    patterns: tuple[tuple[int, re.Pattern[str]], ...] = (
        (
            110,
            re.compile(
                r"(?:입주|공급|모집)\s*대상\s*주택"
                r".{0,180}?"
                r"(?:총\s*)?"
                r"(?P<number>\d[\d,]*)\s*호",
                re.IGNORECASE,
            ),
        ),
        (
            100,
            re.compile(
                r"(?:다가구(?:\s*등)?|다세대|연립|주택)\s*"
                r"(?:주택\s*)?"
                r"(?P<number>\d[\d,]*)\s*호",
                re.IGNORECASE,
            ),
        ),
        (
            95,
            re.compile(
                r"공급\s*대상\s*[:：]"
                r".{0,100}?"
                r"(?P<number>\d[\d,]*)\s*호",
                re.IGNORECASE,
            ),
        ),
    )

    raw_texts = _deduplicate_texts(_collect_structure_texts(structure))

    # Section title과 direct body를 함께 넣는다.
    for section, _ in _iter_sections(structure.get("sections")):
        title = _clean_text(
            section.get("title")
            or section.get("normalized_title")
        )
        direct = _section_direct_text(section)
        if title:
            raw_texts.append(title)
        if direct:
            raw_texts.append(direct)

    search_texts = _deduplicate_texts(raw_texts)

    target_heading_keywords = (
        "입주대상 주택",
        "입주 대상 주택",
        "공급대상 주택",
        "공급 대상 주택",
        "모집대상 주택",
        "모집 대상 주택",
    )

    for index, text_value in enumerate(search_texts):
        # 제목과 다음 본문이 분리된 경우를 위해 인접 3개 text를 한 window로 본다.
        window_parts = search_texts[max(0, index - 1): min(len(search_texts), index + 2)]
        window = re.sub(
            r"\s+",
            " ",
            _clean_text(" ".join(window_parts)),
        )
        current = re.sub(r"\s+", " ", _clean_text(text_value))

        if not current:
            continue

        heading_context = _contains_keyword(
            window,
            target_heading_keywords,
        )

        # 건설위치 설명은 공급대상 heading이 없는 경우 제외.
        if _contains_keyword(
            current,
            ("건설위치", "건설 위치"),
        ) and not heading_context:
            continue

        for score, pattern in patterns:
            # 일반적인 '다가구 등 주택 381호' 패턴은 반드시
            # 인접 문맥에 '입주/공급/모집대상 주택' heading이 있어야 한다.
            if score == 100 and not heading_context:
                continue

            match = pattern.search(window if heading_context else current)
            if not match:
                continue

            try:
                value = int(match.group("number").replace(",", ""))
            except (TypeError, ValueError):
                continue

            if value <= 0:
                continue

            candidates.append((score, -index, value))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][2]


def _select_supply_summary(
    *,
    recruitment_waitlist: int | None,
    recruitment_units: int | None,
    supply_units: int | None,
    construction_units: int | None,
    prefer_waitlist: bool = False,
) -> tuple[str, int | None, str | None]:
    """
    사용자 카드에 표시할 공급 규모를 선택한다.

    - 예비입주자 모집 공고:
      모집 예비자 -> 금회 모집호수 -> 공급호수 -> 건설호수
    - 일반 입주자 모집 공고:
      금회 모집호수 -> 공급호수 -> 건설호수 -> 모집 예비자

    제목은 우선순위를 정하는 데만 사용한다. 예비입주자 모집 제목이어도
    실제 모집 예비자 수가 없으면 주택 공급 수량으로 fallback한다.
    """
    waitlist_candidate = (
        "recruitment_waitlist",
        recruitment_waitlist,
        "금회 모집 예비자",
        "명",
    )
    recruitment_units_candidate = (
        "recruitment_units",
        recruitment_units,
        "금회 모집 호수",
        "호",
    )
    supply_units_candidate = (
        "supply_units",
        supply_units,
        "공급대상 주택",
        "호",
    )
    construction_units_candidate = (
        "construction_units",
        construction_units,
        "공급대상 주택",
        "호",
    )

    if prefer_waitlist:
        candidates = (
            waitlist_candidate,
            recruitment_units_candidate,
            supply_units_candidate,
            construction_units_candidate,
        )
    else:
        candidates = (
            recruitment_units_candidate,
            supply_units_candidate,
            construction_units_candidate,
            waitlist_candidate,
        )

    for metric, value, label, unit in candidates:
        if isinstance(value, int) and value >= 0:
            return (
                f"{label} : 총 {value}{unit}",
                value,
                metric,
            )

    return (
        "공급대상 주택은 공고문 참조",
        None,
        None,
    )


def _complex_name_match_key(
    value: Any,
) -> str:
    text_value = _normalized_match_text(value)
    text_value = re.sub(r"[()\[\]{}<>·ㆍ,._/\-]+", "", text_value)
    text_value = re.sub(r"(?:행복주택|산단형|블록)$", "", text_value)
    text_value = re.sub(r"bl$", "", text_value, flags=re.IGNORECASE)
    return text_value


def _extract_complex_name_catalog(
    structure: dict[str, Any],
) -> list[str]:
    """건설위치 표 등에서 단지명의 표준 표기를 수집한다."""
    result: list[str] = []
    seen: set[str] = set()

    for node in _iter_nested_dicts(structure):
        cells = node.get("cells")
        if not isinstance(cells, list):
            continue

        table_cells = [cell for cell in cells if isinstance(cell, dict)]
        if not table_cells:
            continue

        rows: dict[int, dict[int, str]] = {}
        for cell in table_cells:
            row = cell.get("row")
            col = cell.get("col")
            if not isinstance(row, int) or not isinstance(col, int):
                continue
            cell_text = _clean_text(cell.get("text"))
            if cell_text:
                rows.setdefault(row, {})[col] = cell_text

        if not rows:
            continue

        sorted_rows = sorted(rows)
        header_row: int | None = None
        complex_col: int | None = None
        has_location = False
        has_actual_supply = False

        for row_number in sorted_rows[:4]:
            row_fields: dict[int, str] = {}
            for col, value in rows[row_number].items():
                field = _supply_table_header_field(value)
                if field:
                    row_fields[col] = field
            if "complex_name" not in row_fields.values():
                continue

            header_row = row_number
            for col, field in row_fields.items():
                if field == "complex_name":
                    complex_col = col
                elif field == "location":
                    has_location = True
                elif field in {
                    "supply_units",
                    "recruitment_units",
                    "recruitment_waitlist",
                    "waiting_waitlist",
                }:
                    has_actual_supply = True
            break

        # 공급표 자체가 아니라 건설위치/단지개요 표를 표준명 catalog로 사용한다.
        if (
            header_row is None
            or complex_col is None
            or has_actual_supply
            or not has_location
        ):
            continue

        for row_number in sorted_rows:
            if row_number <= header_row:
                continue
            name = _clean_text(rows[row_number].get(complex_col))
            if not name:
                continue
            key = _complex_name_match_key(name)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(name)

    return result


def _canonical_complex_name(
    value: Any,
    catalog: list[str],
) -> str:
    cleaned = re.sub(r"\s+", " ", _clean_text(value)).strip()
    if not cleaned:
        return ""

    raw_key = _complex_name_match_key(cleaned)
    if not raw_key:
        return cleaned

    best: tuple[int, str] | None = None
    for candidate in catalog:
        candidate_key = _complex_name_match_key(candidate)
        if not candidate_key:
            continue

        matched = (
            candidate_key in raw_key
            or raw_key in candidate_key
        )
        if not matched:
            # A1-3BL / A1-3(산단형)처럼 suffix만 다른 경우를 보완한다.
            candidate_without_bl = re.sub(r"bl$", "", candidate_key)
            if candidate_without_bl and candidate_without_bl in raw_key:
                matched = True

        if not matched:
            continue

        score = len(candidate_key)
        if best is None or score > best[0]:
            best = (score, candidate)

    return best[1] if best is not None else cleaned


def _normalize_supply_housing_items_for_ui(
    housing_items: list[dict[str, Any]],
    structure: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    공급 상세행을 현재 프론트의 grouping 규칙에 맞게 정리한다.

    핵심 규칙:
    - 실제 ``단지명``이 있으면 complex_name으로 사용한다.
    - 단지명이 없고 ``모집단위(주택군)``만 있는 공고는
      housing_group을 complex_name에도 복사한다.
      현재 프론트는 complex_name 기준으로 상세 공급 카드를 묶으므로
      프론트 변경 없이 '26-4 남동구' 같은 모집단위가 카드 제목이 된다.
    - 세로 병합으로 단지명/주택군이 비어 있는 후속 행은 같은 table 안에서만
      직전 값을 이어받는다.
    - 서로 다른 table 사이에서는 절대 carry-forward하지 않는다.
    - 내부 합계행(``_is_total_row``)은 여기서는 유지하고, 수량 요약 후
      ``_filter_supply_housing_items_for_ui``에서 화면용 목록에서 제거한다.
    """
    catalog = _extract_complex_name_catalog(structure)
    result: list[dict[str, Any]] = []

    last_complex_by_table: dict[int, str] = {}
    last_group_by_table: dict[int, str] = {}

    for item in housing_items:
        if not isinstance(item, dict):
            continue

        normalized_item = dict(item)
        source = normalized_item.get("source")
        table_index: int | None = None
        if isinstance(source, dict) and isinstance(source.get("table_index"), int):
            table_index = int(source["table_index"])

        raw_complex_name = _clean_text(normalized_item.get("complex_name"))
        raw_housing_group = _clean_text(normalized_item.get("housing_group"))

        # 명시적인 주택군도 같은 표의 후속 세로병합 행에서 재사용할 수 있게 저장한다.
        if raw_housing_group and table_index is not None:
            last_group_by_table[table_index] = raw_housing_group

        # 1) 단지명이 명시된 경우 최우선
        if raw_complex_name:
            canonical = _canonical_complex_name(raw_complex_name, catalog)
            normalized_item["complex_name"] = canonical
            if table_index is not None:
                last_complex_by_table[table_index] = canonical

        # 2) 단지명 없이 모집단위(주택군)만 있는 표
        elif raw_housing_group:
            normalized_item["complex_name"] = raw_housing_group
            if table_index is not None:
                last_complex_by_table[table_index] = raw_housing_group

        # 3) 세로 병합으로 현재 행의 두 값이 모두 비어 있는 경우
        elif table_index is not None:
            carried_complex = last_complex_by_table.get(table_index)
            carried_group = last_group_by_table.get(table_index)

            if carried_group:
                normalized_item["housing_group"] = carried_group

            if carried_complex:
                normalized_item["complex_name"] = carried_complex
            elif carried_group:
                normalized_item["complex_name"] = carried_group

        result.append(normalized_item)

    return result


def _dedupe_repeated_supply_label(value: Any) -> str:
    """
    표 병합/셀 결합 과정에서 ``16A 16A``처럼 동일한 문자열이
    두 번 이어진 경우 한 번만 남긴다.
    """
    cleaned = re.sub(r"\s+", " ", _clean_text(value)).strip()
    if not cleaned:
        return ""

    parts = cleaned.split(" ")
    if len(parts) >= 2 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            return " ".join(parts[:half]).strip()

    return cleaned


def _filter_supply_housing_items_for_ui(
    housing_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    화면 상세 카드에 표시할 실제 공급 행만 남긴다.

    핵심 규칙:
    - ``소계/합계/총계`` 행은 화면 목록에서 제외한다.
    - 단지명/주택군, 소재지, 면적 같은 보조값만 있고 실제 공급 수량이나
      임대조건이 없는 행은 제거한다. 이런 행은 프론트에서 ``- / - / -``로
      보이므로 UI용 housing_items에 포함하면 안 된다.
    - 실제 공급 수량(건설호수/공급호수/모집호수/예비자수 등)이 하나라도
      있으면 유효한 공급행으로 본다.
    - 수량이 없더라도 주택형과 임대조건(보증금/월임대료/임대조건)이 함께
      존재하는 행은 유효한 공급행으로 유지한다.
    - 주택형이 비어 있고 면적값이 실제 주택형 역할을 하는 문서는 면적을
      주택형 fallback으로 사용한다.
    - 주택형에는 현재 프론트를 수정하지 않고도 의미가 분명하도록
      ``단지명 + 주택형``을 내려준다.
    """
    result: list[dict[str, Any]] = []
    seen_rows: set[tuple[tuple[str, str], ...]] = set()

    quantity_fields = (
        "construction_units",
        "supply_units",
        "recruitment_units",
        "recruitment_waitlist",
        "waiting_waitlist",
    )

    financial_fields = (
        "deposit",
        "monthly_rent",
        "rental_condition",
    )

    def _has_real_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (list, dict, tuple, set)) and not value:
            return False
        cleaned = _clean_text(value)
        return cleaned not in (
            "",
            "-",
            "–",
            "—",
            "·",
            "없음",
            "해당없음",
            "해당 없음",
            "null",
            "None",
        )

    for item in housing_items:
        if not isinstance(item, dict):
            continue

        if item.get("_is_total_row") is True:
            continue

        cleaned_item = {
            key: value
            for key, value in item.items()
            if not str(key).startswith("_")
        }

        housing_type = _dedupe_repeated_supply_label(
            cleaned_item.get("housing_type")
        )
        area = _dedupe_repeated_supply_label(
            cleaned_item.get("area")
        )

        # 일부 매입임대 표는 '주택형' 대신 면적 구간만 제공한다.
        # 예: 60~70㎡ / 80㎡ 이상. 이 경우에만 area를 주택형으로 사용한다.
        if not housing_type and area and re.search(
            r"(?:㎡|m²|m2|평|\d\s*[~～-]\s*\d)",
            area,
            re.IGNORECASE,
        ):
            housing_type = area
            cleaned_item["housing_type"] = area

        has_quantity = any(
            _has_real_value(cleaned_item.get(field))
            for field in quantity_fields
        )
        has_financial = any(
            _has_real_value(cleaned_item.get(field))
            for field in financial_fields
        )

        # 중요: location/area/complex_name 같은 보조값만 있는 행은 제거한다.
        # 이전에는 area/location만 있어도 살아남아 프론트에 '- / - / -'로 보였다.
        if not has_quantity and not (housing_type and has_financial):
            continue

        complex_name = _clean_text(cleaned_item.get("complex_name"))

        if housing_type:
            if complex_name:
                compact_complex = re.sub(r"\s+", "", complex_name)
                compact_type = re.sub(r"\s+", "", housing_type)

                # 이미 단지명이 포함된 문자열이면 중복해서 붙이지 않는다.
                if not compact_type.startswith(compact_complex):
                    cleaned_item["housing_type"] = (
                        f"{complex_name} {housing_type}".strip()
                    )
                else:
                    cleaned_item["housing_type"] = housing_type
            else:
                cleaned_item["housing_type"] = housing_type

        # 의미 없는 placeholder 값 자체도 UI payload에서는 제거한다.
        for key in list(cleaned_item):
            if key in ("source", "complex_name", "housing_group"):
                continue
            value = cleaned_item.get(key)
            if isinstance(value, str) and not _has_real_value(value):
                cleaned_item.pop(key, None)

        # 동일 행이 구조화 과정에서 중복 생성된 경우 마지막 단계에서 제거한다.
        row_key = tuple(
            sorted(
                (str(key), str(value))
                for key, value in cleaned_item.items()
                if key != "source"
            )
        )
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        result.append(cleaned_item)

    return result


def _extract_supply_from_structure(
    structure: dict[str, Any],
) -> dict[str, Any]:
    """
    Structure 전체 텍스트에서 표 수량 이외의 보조 공급정보를 찾는다.

    모집 예비자/모집호수 집계는 구조화된 표를 기준으로 유지한다.
    다만 표에 공급호수 열이 없는 공고의 '공급대상 주택 N호'처럼
    명시적인 주택 수만 제한적으로 supply_units fallback으로 사용한다.
    """
    texts = _collect_structure_texts(structure)
    details_reference = ""
    rental_condition_summary = ""

    for text_value in texts:
        for line in text_value.splitlines():
            cleaned = _clean_text(line)

            if (
                not details_reference
                and "주택내역" in cleaned
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
                details_reference = cleaned

            if (
                not rental_condition_summary
                and "시중 시세" in cleaned
                and (
                    "임대료" in cleaned
                    or "임대보증금" in cleaned
                )
            ):
                rental_condition_summary = cleaned

    return {
        "details_reference": details_reference,
        "rental_condition_summary": rental_condition_summary,
        "explicit_supply_units": (
            _extract_explicit_supply_units_from_structure(structure)
        ),
    }


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
    matches: list[dict[str, Any]],
    *,
    structure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    공급정보를 생성한다.

    카드의 ``summary``는 구조화된 공급표의 실제 모집 규모를 최우선으로 한다.
    본문에서 임의의 ``총 N호``를 다시 추출하지 않아 중복·오탐 집계를 방지한다.
    """
    valid_matches = [
        match
        for match in matches
        if _is_valid_supply_section(match["_section"])
    ]

    result = _build_generic_field(
        "supply_information",
        valid_matches,
    )

    details_reference = _extract_supply_details_reference(valid_matches)
    rental_condition_summary = _extract_supply_rental_condition_summary(
        valid_matches
    )

    housing_items: list[dict[str, Any]] = []
    construction_units: int | None = None
    supply_units: int | None = None
    recruitment_units: int | None = None
    recruitment_waitlist: int | None = None
    waiting_waitlist: int | None = None

    if structure is not None:
        auxiliary = _extract_supply_from_structure(structure)

        if not details_reference:
            details_reference = auxiliary.get("details_reference") or ""
        if not rental_condition_summary:
            rental_condition_summary = (
                auxiliary.get("rental_condition_summary") or ""
            )

        raw_housing_items = _extract_supply_table_rows(structure)
        normalized_housing_items = _normalize_supply_housing_items_for_ui(
            raw_housing_items,
            structure,
        )

        construction_units = _sum_unique_construction_units(
            normalized_housing_items,
            structure,
        )

        # 합계행은 top-level 수량 계산에 사용한 뒤 UI 목록에서는 제거한다.
        table_summary = _summarize_supply_table_rows(normalized_housing_items)
        supply_units = table_summary.get("supply_units")
        recruitment_units = table_summary.get("recruitment_units")
        recruitment_waitlist = table_summary.get("recruitment_waitlist")
        waiting_waitlist = table_summary.get("waiting_waitlist")

        housing_items = _filter_supply_housing_items_for_ui(
            normalized_housing_items
        )

        # 본문에 '■ 공급대상 주택 : 총 137호'처럼 명시적인 총량이 있으면
        # 세부표 합산값보다 이 값을 우선한다.
        # 특히 '소계 137' 행과 상세 137호가 함께 파싱되어 274호로
        # 이중 합산되는 문서를 안전하게 보정한다.
        explicit_supply_units = auxiliary.get("explicit_supply_units")
        if isinstance(explicit_supply_units, int) and explicit_supply_units > 0:
            supply_units = explicit_supply_units

    prefer_waitlist = (
        _supply_prefers_waitlist(structure)
        if structure is not None
        else False
    )

    summary, total_units, summary_metric = _select_supply_summary(
        recruitment_waitlist=recruitment_waitlist,
        recruitment_units=recruitment_units,
        supply_units=supply_units,
        construction_units=construction_units,
        prefer_waitlist=prefer_waitlist,
    )

    # 구조화 표에서 수량을 찾지 못한 문서는 기존 텍스트 요약을 fallback으로 사용한다.
    # 단, 임대보증금/월임대료/전환이율만 설명하는 문장은 _build_supply_summary에서
    # 제외되므로 공급 카드에 임대조건 문장이 들어가는 문제를 막는다.
    if summary_metric is None:
        fallback_summary = _build_supply_summary(valid_matches)
        if fallback_summary:
            summary = fallback_summary

    result.update(
        {
            "summary": summary,
            "summary_metric": summary_metric,
            "total_units": total_units,
            "construction_units": construction_units,
            "supply_units": supply_units,
            "recruitment_units": recruitment_units,
            "recruitment_waitlist": recruitment_waitlist,
            "waiting_waitlist": waiting_waitlist,
            "housing_items": housing_items,
            "details_reference": details_reference,
            "rental_condition_summary": rental_condition_summary,
        }
    )

    if (
        total_units is not None
        or supply_units is not None
        or recruitment_units is not None
        or recruitment_waitlist is not None
        or waiting_waitlist is not None
        or bool(housing_items)
        or details_reference
        or rental_condition_summary
    ):
        result["status"] = "extracted"

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
        structure_summary = ""
        if structure is not None:
            structure_summary = (
                _build_income_asset_summary_from_structure(
                    structure
                )
            )

        result["summary"] = (
            structure_summary
            or _build_income_asset_summary(
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
