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


def _score_section_for_field(
    section: dict[str, Any],
    field: str,
) -> int:
    rule = FIELD_RULES[field]

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
            "sources": [],
        }

    texts = _deduplicate_texts(
        match["text"]
        for match in matches[
            :5
        ]
    )

    return {
        "status": "extracted",
        "text": "\n\n".join(
            texts
        ),
        "sources": _public_sources(
            matches
        ),
    }


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
        _extract_date_bounds(
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

    _, _, dates = (
        _extract_date_bounds(
            matches
        )
    )

    result["dates"] = dates

    if dates:
        result[
            "announcement_date"
        ] = dates[0][
            "normalized_value"
        ]
    else:
        result[
            "announcement_date"
        ] = None

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

    result["phone_numbers"] = (
        _collect_phone_numbers(
            matches
        )
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
