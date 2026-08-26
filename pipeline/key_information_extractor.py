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
#
# 1순위: Structure가 이미 만든 domain.category / topic
# 2순위: Section 제목·classification_text의 keyword
#
# Structure 단계의 의미 분류 결과를 재사용하는 것이 목적이므로
# 키워드는 분류 실패/낮은 신뢰도 Section을 위한 보조 수단이다.
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


# eligibility로 분류된 Section이라도 소득/자산 정보라면
# income_asset_criteria 쪽으로도 별도 수집한다.
INCOME_ASSET_KEYWORDS = FIELD_RULES[
    "income_asset_criteria"
]["keywords"]


# ============================================================
# supply_information 검증 규칙
# ============================================================
SUPPLY_TITLE_KEYWORDS = (
    "공급정보", "공급 정보", "공급대상", "공급 대상",
    "공급계획", "공급 계획", "공급내역", "공급 내역",
    "공급현황", "공급 현황", "주택공급", "주택 공급",
    "주택형별", "임대조건", "임대 조건",
)

SUPPLY_DATA_KEYWORDS = (
    "주택형", "전용면적",
    "공급호수", "공급 호수", "모집호수", "모집 호수",
    "공급세대", "공급 세대", "공급세대수", "공급 세대수",
    "모집세대", "모집 세대", "모집세대수", "모집 세대수",
    "임대보증금", "임대 보증금", "월임대료", "월 임대료",
    "임대조건", "임대 조건",
    "공급위치", "공급 위치", "건설위치", "건설 위치",
)

SUPPLY_EXCLUSION_KEYWORDS = (
    "개인정보 수집", "개인정보 이용", "개인정보 제공", "개인정보 처리",
    "민감정보 수집", "민감정보 이용", "민감정보 활용",
    "동의 거부", "동의여부", "동의 여부",
    "제3자 제공", "개인정보의 제3자",
    "보유·이용 기간", "보유 이용 기간",
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

    # 구조화 표 record의 value도 포함한다.
    structured_table = content.get(
        "structured_table"
    )

    if isinstance(structured_table, dict):
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

            # key-value 구조가 있으면 key도 포함
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

    # cells가 있는 fallback 표도 원문 보존
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
        or section.get("normalized_title")
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
            domain.get("confidence") or 0.0
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
    normalized_text = _normalized_match_text(text)
    matched: set[str] = set()

    for keyword in keywords:
        normalized_keyword = _normalized_match_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            matched.add(normalized_keyword)

    return len(matched)


def _is_valid_supply_section(
    section: dict[str, Any],
) -> bool:
    """실제 공급정보 특징과 제외 문맥을 함께 사용해 supply Section을 검증한다."""

    title_text = " ".join(
        _deduplicate_texts(
            (
                _clean_text(section.get("title")),
                _clean_text(section.get("normalized_title")),
                _clean_text(section.get("search_title")),
            )
        )
    )

    body_text = _section_direct_text(section)
    full_text = f"{title_text} {body_text}"

    category, topic, _ = _domain_info(section)

    supply_topics = {
        "supply_information",
        "supply_plan",
        "housing_supply",
        "supply_price",
        "rental_condition",
        "housing_information",
    }
    supply_categories = {"supply", "housing", "price"}

    strong_topic = topic in supply_topics
    title_match = _contains_keyword(
        title_text,
        SUPPLY_TITLE_KEYWORDS,
    )
    data_evidence_count = _count_keyword_matches(
        full_text,
        SUPPLY_DATA_KEYWORDS,
    )
    excluded_context = _contains_keyword(
        full_text,
        SUPPLY_EXCLUSION_KEYWORDS,
    )

    # 개인정보/민감정보/동의 문맥은 공급이라는 표현이 우연히 들어갈 수 있다.
    # 실제 공급 데이터 특징이 충분하지 않으면 공급정보에서 제외한다.
    if excluded_context and data_evidence_count < 2:
        return False

    # Structure의 구체적인 supply topic은 강한 근거로 사용한다.
    if strong_topic:
        return True

    # 제목 자체가 명확한 공급정보 제목이면 인정한다.
    if title_match:
        return True

    # 넓은 category만 있는 경우 실제 공급 데이터 특징을 함께 요구한다.
    if category in supply_categories:
        return data_evidence_count >= 1

    # domain 분류가 없는 fallback은 실제 공급 데이터 특징이 2개 이상일 때만 인정한다.
    return data_evidence_count >= 2


def _score_section_for_field(
    section: dict[str, Any],
    field: str,
) -> int:
    rule = FIELD_RULES[field]

    if (
        field == "supply_information"
        and not _is_valid_supply_section(section)
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

    # domain topic은 가장 강한 근거
    if topic and topic in set(
        rule["topics"]
    ):
        score += 100

    # category는 넓은 범위라 두 번째 근거
    if category and category in set(
        rule["categories"]
    ):
        score += 50

    # 높은 신뢰도 domain이면 약간 가산
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

    # 제목/본문 fallback
    matched_keyword_count = sum(
        1
        for keyword in rule["keywords"]
        if _contains_keyword(
            classification_text,
            (keyword,),
        )
    )

    score += min(
        matched_keyword_count,
        5,
    ) * 10

    # eligibility와 income/asset 분리
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

    # winner는 schedule 전체를 다 먹지 않도록
    # 당첨/발표 관련 키워드가 없으면 schedule category만으로는 제외한다.
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

    # application period 역시 일반 일정 전체를 모두 가져오지 않는다.
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
    result: list[dict[str, Any]] = []
    seen: set[
        tuple[str, str]
    ] = set()

    for node in _iter_nested_dicts(
        value
    ):
        entities = node.get("entities")

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
    dates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in matches:
        section = match[
            "_section"
        ]

        for entity in _collect_entities(
            section,
            entity_type="date",
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

    # ISO-like YYYY-MM-DD / YYYY-MM 값은 문자열 정렬이 가능하다.
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

        for entity in _collect_entities(
            section,
            entity_type="phone",
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

    # Entity가 없는 경우 텍스트에서 보수적으로 fallback
    phone_pattern = re.compile(
        r"(?<!\d)"
        r"(?:0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}|"
        r"1\d{3}[-\s]?\d{4})"
        r"(?!\d)"
    )

    for match in matches:
        for value in phone_pattern.findall(
            match["text"]
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
    """structured_table 안의 key/value를 가능한 형태에서 수집한다."""
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for node in _iter_nested_dicts(section):
        key_values = node.get("key_values")

        if isinstance(key_values, list):
            for item in key_values:
                if not isinstance(item, dict):
                    continue

                key = _clean_text(
                    item.get("key")
                    or item.get("label")
                    or item.get("header")
                )
                value = _clean_text(
                    item.get("value")
                    or item.get("text")
                )

                if not key and not value:
                    continue

                pair = (key, value)

                if pair in seen:
                    continue

                seen.add(pair)
                result.append(
                    {
                        "key": key,
                        "value": value,
                    }
                )

        key = _clean_text(node.get("key"))
        value = node.get("value")

        if key and isinstance(
            value,
            (str, int, float),
        ):
            value_text = _clean_text(value)
            pair = (key, value_text)

            if pair not in seen:
                seen.add(pair)
                result.append(
                    {
                        "key": key,
                        "value": value_text,
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
    """Section 전체가 아니라 핵심 키워드가 있는 짧은 문장/항목만 추출한다."""
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

        if len(cleaned) > max_length:
            sentences = re.split(
                r"(?<=[.!?。])\s+|(?<=다\.)\s*",
                cleaned,
            )

            selected = [
                _clean_text(sentence)
                for sentence in sentences
                if _clean_text(sentence)
                and _contains_keyword(
                    sentence,
                    keywords,
                )
            ]

            result.extend(selected)
        else:
            result.append(cleaned)

    return _deduplicate_texts(
        result
    )[:max_items]


def _key_value_matches_for_field(
    matches: list[dict[str, Any]],
    field: str,
) -> list[dict[str, str]]:
    keywords = FIELD_RULES[field]["keywords"]
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for match in matches:
        section = match["_section"]

        for item in _extract_structured_key_values(
            section
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

            pair = (key, value)

            if pair in seen:
                continue

            seen.add(pair)
            result.append(item)

    return result


_DATE_WITH_TIME_PATTERN = re.compile(
    r"[‘’']?"
    r"(?P<year>\d{2,4})[.\-/년]\s*"
    r"(?P<month>\d{1,2})[.\-/월]\s*"
    r"(?P<day>\d{1,2})(?:일)?"
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
    r"(?P<start_year>\d{2,4})[.\-/]\s*"
    r"(?P<start_month>\d{1,2})[.\-/]\s*"
    r"(?P<start_day>\d{1,2})"
    r"(?:\s*\([^)]*\))?"
    r"\s*"
    r"(?:(?P<start_ampm>오전|오후)\s*)?"
    r"(?P<start_hour>\d{1,2})?"
    r"(?::|시)?\s*"
    r"(?P<start_minute>\d{1,2})?"
    r"(?:분)?"
    r"\s*(?:~|∼|～|부터)\s*"
    r"[‘’']?"
    r"(?:(?P<end_year>\d{2,4})[.\-/]\s*)?"
    r"(?P<end_month>\d{1,2})[.\-/]\s*"
    r"(?P<end_day>\d{1,2})"
    r"(?:\s*\([^)]*\))?"
    r"\s*"
    r"(?:(?P<end_ampm>오전|오후)\s*)?"
    r"(?P<end_hour>\d{1,2})?"
    r"(?::|시)?\s*"
    r"(?P<end_minute>\d{1,2})?"
    r"(?:분)?"
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
    minute = int(minute_raw or 0)

    if ampm == "오후" and hour < 12:
        hour += 12
    elif ampm == "오전" and hour == 12:
        hour = 0

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return None

    return f"{hour:02d}:{minute:02d}"


def _format_date_time(
    *,
    year: int,
    month: int,
    day: int,
    time_value: str | None,
) -> str:
    date_value = (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )

    if time_value:
        return f"{date_value}T{time_value}"

    return date_value


def _normalize_date_match(
    match: re.Match[str],
) -> str:
    year = _normalize_year_value(
        match.group("year")
    )
    month = int(match.group("month"))
    day = int(match.group("day"))

    time_value = _normalize_time_parts(
        match.group("ampm"),
        match.group("hour"),
        match.group("minute"),
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
    """'26.8.31 ~ 9.2처럼 종료 연도가 생략된 범위를 복원한다."""

    start_year = _normalize_year_value(
        match.group("start_year")
    )
    start_month = int(
        match.group("start_month")
    )
    start_day = int(
        match.group("start_day")
    )

    end_year_raw = match.group(
        "end_year"
    )

    if end_year_raw:
        end_year = _normalize_year_value(
            end_year_raw
        )
    else:
        # 종료 연도가 생략되면 시작 연도를 상속한다.
        end_year = start_year

    end_month = int(
        match.group("end_month")
    )
    end_day = int(
        match.group("end_day")
    )

    # 12월 → 1월처럼 연말을 넘는 범위도 방어적으로 처리한다.
    if (
        not end_year_raw
        and (end_month, end_day)
        < (start_month, start_day)
    ):
        end_year += 1

    start_time = _normalize_time_parts(
        match.group("start_ampm"),
        match.group("start_hour"),
        match.group("start_minute"),
    )
    end_time = _normalize_time_parts(
        match.group("end_ampm"),
        match.group("end_hour"),
        match.group("end_minute"),
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


def _keyword_positions(
    text: str,
    keywords: Iterable[str],
) -> list[int]:
    normalized = text.lower()
    result: list[int] = []

    for keyword in keywords:
        needle = _clean_text(keyword).lower()

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
            start = index + len(needle)

    return sorted(set(result))


def _distance_to_nearest_keyword(
    position: int,
    keyword_positions: list[int],
) -> int:
    if not keyword_positions:
        return 10**9

    return min(
        abs(position - keyword_position)
        for keyword_position
        in keyword_positions
    )


def _extract_application_period_values(
    matches: list[dict[str, Any]],
) -> tuple[
    str | None,
    str | None,
    list[dict[str, Any]],
]:
    """신청/접수 문맥에서 실제 기간 범위를 우선 추출한다."""

    positive_keywords = (
        "신청기간",
        "신청 기간",
        "접수기간",
        "접수 기간",
        "접수시작",
        "접수 시작",
        "접수마감",
        "접수 마감",
        "신청시작",
        "신청 시작",
        "신청마감",
        "신청 마감",
        "청약 접수",
        "청약접수",
        "신청접수",
        "신청 접수",
    )

    # 1순위: "~"로 연결된 실제 신청 기간을 하나의 range로 인식한다.
    range_candidates: list[
        dict[str, Any]
    ] = []

    for match_item in matches:
        text_value = match_item["text"]
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
            start, end = (
                _normalize_date_range_match(
                    range_match
                )
            )

            distance = (
                _distance_to_nearest_keyword(
                    range_match.start(),
                    keyword_positions,
                )
            )

            left = max(
                0,
                range_match.start() - 120,
            )
            right = min(
                len(text_value),
                range_match.end() + 120,
            )

            context = _clean_text(
                text_value[left:right]
            )

            # 신청/접수 문맥이 없는 날짜범위는 제외한다.
            if (
                distance > 250
                and not _contains_keyword(
                    context,
                    positive_keywords,
                )
            ):
                continue

            range_candidates.append(
                {
                    "start": start,
                    "end": end,
                    "raw": _clean_text(
                        range_match.group(0)
                    ),
                    "context": context,
                    "distance": distance,
                }
            )

    if range_candidates:
        # 신청/접수 키워드와 가장 가까운 범위를 선택한다.
        range_candidates.sort(
            key=lambda item: (
                item["distance"],
                item["start"],
            )
        )

        selected = range_candidates[0]

        return (
            selected["start"],
            selected["end"],
            [
                {
                    "raw": selected["raw"],
                    "normalized_value": (
                        f"{selected['start']} ~ "
                        f"{selected['end']}"
                    ),
                    "context": (
                        selected["context"]
                    ),
                }
            ],
        )

    # 2순위 fallback:
    # 완전한 날짜만 존재하는 문서에서는 신청/접수 키워드와 가까운 날짜를 사용한다.
    date_candidates: list[
        dict[str, Any]
    ] = []

    for match_item in matches:
        text_value = match_item["text"]
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
            distance = (
                _distance_to_nearest_keyword(
                    date_match.start(),
                    keyword_positions,
                )
            )

            if distance > 250:
                continue

            normalized = (
                _normalize_date_match(
                    date_match
                )
            )

            date_candidates.append(
                {
                    "raw": _clean_text(
                        date_match.group(0)
                    ),
                    "normalized_value": (
                        normalized
                    ),
                    "distance": distance,
                }
            )

    # 가까운 날짜 우선 → 동일 문맥 내에서 시간순
    date_candidates.sort(
        key=lambda item: (
            item["distance"],
            item["normalized_value"],
        )
    )

    unique: list[dict[str, Any]] = []
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

    # fallback에서는 가까운 후보 최대 2개만 기간으로 사용한다.
    selected = unique[:2]
    selected.sort(
        key=lambda item: item[
            "normalized_value"
        ]
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

    return start, end, selected



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
        score = _score_section_for_field(
            section,
            field,
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
                    for value in section_path
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

    # 점수가 높은 Section 우선.
    # 원래 문서 순서는 같은 점수일 때 Python stable sort로 보존된다.
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

    for match in matches[
        :limit
    ]:
        result.append(
            {
                "section_id": (
                    match[
                        "section_id"
                    ]
                ),
                "title": (
                    match[
                        "title"
                    ]
                ),
                "section_path": (
                    match[
                        "section_path"
                    ]
                ),
                "domain": (
                    match[
                        "domain"
                    ]
                ),
                "score": (
                    match[
                        "score"
                    ]
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
                FIELD_RULES[field][
                    "keywords"
                ],
            )
        )

    snippets = _deduplicate_texts(
        snippets
    )

    text_value = "\n".join(
        snippets[:10]
    )

    if not key_values and not text_value:
        return {
            "status": "not_found",
            "text": "",
            "key_values": [],
            "sources": _public_sources(
                matches
            ),
        }

    return {
        "status": "extracted",
        "text": text_value,
        "key_values": key_values[:20],
        "sources": _public_sources(
            matches
        ),
    }


def _build_supply_information(
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    """최종 공급정보 생성 전에 후보 Section을 한 번 더 검증한다."""

    valid_matches = [
        match
        for match in matches
        if _is_valid_supply_section(
            match["_section"]
        )
    ]

    return _build_generic_field(
        "supply_information",
        valid_matches,
    )


def _build_application_period(
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    result = _build_generic_field(
        "application_period",
        matches,
    )

    start, end, dates = (
        _extract_application_period_values(
            matches
        )
    )

    result.update(
        {
            "start": start,
            "end": end,
            "dates": dates,
        }
    )

    if (
        start is None
        and end is None
        and not result.get(
            "key_values"
        )
    ):
        result["status"] = "not_found"

    return result


def _build_winner_announcement(
    matches: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    result = _build_generic_field(
        "winner_announcement",
        matches,
    )

    keywords = FIELD_RULES[
        "winner_announcement"
    ]["keywords"]

    winner_dates: list[
        dict[str, Any]
    ] = []

    for match_item in matches:
        text_value = match_item["text"]

        keyword_positions = (
            _keyword_positions(
                text_value,
                keywords,
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

            # Section 안의 "가장 이른 날짜"가 아니라
            # "당첨자/예비입주자 발표" 표현과 가까운 날짜만 후보로 사용한다.
            if distance > 180:
                continue

            normalized = (
                _normalize_date_match(
                    date_match
                )
            )

            left = max(
                0,
                date_match.start() - 100,
            )
            right = min(
                len(text_value),
                date_match.end() + 100,
            )

            winner_dates.append(
                {
                    "raw": _clean_text(
                        date_match.group(0)
                    ),
                    "normalized_value": (
                        normalized
                    ),
                    "context": _clean_text(
                        text_value[left:right]
                    ),
                    "distance": distance,
                }
            )

    # keyword와 가까운 날짜를 우선한다.
    winner_dates.sort(
        key=lambda item: (
            item["distance"],
            item["normalized_value"],
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
                item["normalized_value"]
            ),
            "context": item["context"],
        }
        for item in deduped
    ]

    result["dates"] = public_dates
    result["announcement_date"] = (
        deduped[0][
            "normalized_value"
        ]
        if deduped
        else None
    )

    if (
        not deduped
        and not result.get(
            "key_values"
        )
        and not result.get("text")
    ):
        result["status"] = "not_found"

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

    result["phone_numbers"] = phones

    if (
        not phones
        and not result.get(
            "key_values"
        )
        and not result.get("text")
    ):
        result["status"] = "not_found"

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

    입력:
        structure_path
            step4-1_value_normalized.json

        verification_path
            step4-3_verification.json

        context
            document_processor가 넘긴 DB/Pipeline context.
            현재 추출 판단에 DB 값을 섞지 않고 metadata 확인용으로만 사용한다.

    반환:
        {
            "application_period": {...},
            "eligibility": {...},
            "supply_information": {...},
            "income_asset_criteria": {...},
            "required_documents": {...},
            "winner_announcement": {...},
            "contact_information": {...},
        }

    원칙:
    - Structure의 domain 분류를 최우선 근거로 사용
    - 규칙 분류가 부족한 경우에만 제목/본문 keyword fallback
    - 원문에 없는 값을 추측하지 않음
    - 찾지 못한 필드는 빈 dict가 아니라 status=not_found로 명시
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

    matches = {
        field: _collect_field_matches(
            structure,
            field,
        )
        for field in REQUIRED_FIELDS
    }

    result: dict[
        str,
        Any,
    ] = {
        "application_period": (
            _build_application_period(
                matches[
                    "application_period"
                ]
            )
        ),
        "eligibility": (
            _build_generic_field(
                "eligibility",
                matches[
                    "eligibility"
                ],
            )
        ),
        "supply_information": (
            _build_generic_field(
                "supply_information",
                matches[
                    "supply_information"
                ],
            )
        ),
        "income_asset_criteria": (
            _build_generic_field(
                "income_asset_criteria",
                matches[
                    "income_asset_criteria"
                ],
            )
        ),
        "required_documents": (
            _build_generic_field(
                "required_documents",
                matches[
                    "required_documents"
                ],
            )
        ),
        "winner_announcement": (
            _build_winner_announcement(
                matches[
                    "winner_announcement"
                ]
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

    # 최종 계약 보장
    missing = [
        field
        for field in REQUIRED_FIELDS
        if field not in result
        or not isinstance(
            result[field],
            dict,
        )
    ]

    if missing:
        raise RuntimeError(
            "핵심정보 추출 결과 계약 위반: "
            f"{missing}"
        )

    return result
