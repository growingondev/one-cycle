from __future__ import annotations

from kiwipiepy import Kiwi


kiwi = Kiwi()


# 형태소 기준으로 잡기 좋은 핵심 단어 규칙
INTENT_TOKEN_RULES: dict[str, list[set[str]]] = {
    "eligibility": [
        {"신청", "자격"},
        {"입주", "자격"},
        {"자격", "조건"},
        {"소득"},
        {"자산"},
        {"무주택"},
        {"세대주"},
        {"세대원"},
    ],

    "schedule": [
        {"신청", "기간"},
        {"접수", "기간"},
        {"서류", "제출", "기간"},
        {"계약", "기간"},
        {"발표"},
        {"발표일"},
        {"마감"},
        {"일정"},
    ],

    "rental_condition": [
        {"임대", "조건"},
        {"임대", "보증금"},
        {"월", "임대료"},
        {"전환", "보증금"},
        {"보증금"},
        {"임대료"},
        {"월세"},
    ],

    "documents": [
        {"필요", "서류"},
        {"준비", "서류"},
        {"증빙", "서류"},
        {"신청", "서류"},
        {"계약", "서류"},
        {"서류", "발급"},
        {"원본"},
        {"사본"},
    ],

    "application_method": [
        {"신청", "방법"},
        {"접수", "방법"},
        {"온라인", "신청"},
        {"온라인", "접수"},
        {"현장", "접수"},
        {"방문", "접수"},
        {"우편", "접수"},
    ],

    "supply_info": [
        {"공급", "세대수"},
        {"모집", "세대수"},
        {"모집", "호수"},
        {"주택형"},
        {"주택", "유형"},
        {"전용", "면적"},
        {"공급", "면적"},
        {"평형"},
    ],

    "location": [
        {"공급", "지역"},
        {"단지", "위치"},
        {"소재지"},
        {"주소"},
        {"지역"},
        {"위치"},
    ],
}


# 형태소만으로 잡기 어려운 자연어 표현
INTENT_EXPRESSION_RULES: dict[str, tuple[str, ...]] = {
    "eligibility": (
    "신청 가능",
    "지원 가능",
    "입주 가능",
    "내가 신청",
    "나도 신청",
    "신청 가능한가",
    "지원 가능한가",
    "입주 가능한가",
    ),

    "schedule": (
        "언제부터",
        "언제까지",
        "며칠까지",
        "몇 일까지",
    ),

    "rental_condition": (
        "얼마야",
        "얼마인가",
    ),

    "documents": (
        "뭐 준비",
        "무슨 서류",
        "어떤 서류",
    ),

    "application_method": (
        "어디서 신청",
        "어디에서 신청",
        "어디로 신청",
        "어떻게 신청",
        "온라인으로 신청",
        "현장으로 신청",
    ),

    "supply_info": (
        "몇 세대",
        "몇세대",
        "몇 호",
        "몇호",
    ),

    "location": (
        "어디에 있어",
        "어디야",
        "어느 지역",
    ),
}


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _extract_tokens(query: str) -> set[str]:
    """
    Kiwi로 질문을 형태소 분석하고
    intent 판별에 사용할 표면형(form)만 set으로 반환한다.
    """
    tokens = kiwi.tokenize(query)

    return {
        token.form
        for token in tokens
        if token.tag.startswith(("N", "V", "VA", "XR", "MAG"))
    }


def _match_token_rules(
    token_set: set[str],
    rules: list[set[str]],
) -> bool:
    """
    하나의 rule에 포함된 모든 토큰이 질문에 존재하면 매칭한다.
    """
    return any(rule <= token_set for rule in rules)


def _match_expression_rules(
    query: str,
    expressions: tuple[str, ...],
) -> bool:
    return any(expression in query for expression in expressions)


def classify_intents(query: str) -> list[str]:
    """
    사용자 질문을 Kiwi 형태소 분석 + 표현 규칙으로 분류한다.

    - 복수 Intent를 허용한다.
    - 형태소 규칙과 자연어 표현 규칙을 함께 사용한다.
    - 아무 Intent도 매칭되지 않으면 general을 반환한다.
    """
    normalized_query = _normalize_query(query)

    if not normalized_query:
        return ["general"]

    token_set = _extract_tokens(normalized_query)

    matched_intents: list[str] = []

    for intent in INTENT_TOKEN_RULES:
        token_matched = _match_token_rules(
            token_set,
            INTENT_TOKEN_RULES[intent],
        )

        expression_matched = _match_expression_rules(
            normalized_query,
            INTENT_EXPRESSION_RULES.get(intent, ()),
        )

        if token_matched or expression_matched:
            matched_intents.append(intent)

    if not matched_intents:
        return ["general"]

    return matched_intents