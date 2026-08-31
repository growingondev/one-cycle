from __future__ import annotations

import re


DOCUMENT_ROLE_PRIMARY = "primary"
DOCUMENT_ROLE_SUPPORTING = "supporting"
DOCUMENT_ROLE_UNKNOWN = "unknown"

VALID_DOCUMENT_ROLES = {
    DOCUMENT_ROLE_PRIMARY,
    DOCUMENT_ROLE_SUPPORTING,
    DOCUMENT_ROLE_UNKNOWN,
}


SUPPORTING_KEYWORDS = (
    "개인정보",
    "동의서",
    "위임장",
    "qna",
    "q&a",
    "금융정보",
    "자산보유",
    "각서",
    "공동신청",
    "세대구성",
    "중복선정",
    "필수제출서류",
    "추가서류",
    "신청안내",
    "확약서",
    "확인서",
    "작성서류",
    "제출서류",
    "required_documents",
    "supplement",
)

PRIMARY_KEYWORDS = (
    "공고",
    "모집",
    "main_notice",
)


def classify_document_role(
    filename: str,
) -> str:
    """
    파일명을 기준으로 문서 역할을 분류한다.

    primary:
        실제 모집공고 분석 대상

    supporting:
        동의서, 위임장, Q&A, 확인서 등 부속 문서

    unknown:
        현재 규칙으로 판별할 수 없는 문서
    """

    text = str(filename or "").strip().lower()

    if not text:
        return DOCUMENT_ROLE_UNKNOWN

    # 부속 문서를 먼저 판별해야
    # '모집공고문_QA' 같은 파일을 primary로 잘못 잡지 않는다.
    if any(
        keyword in text
        for keyword in SUPPORTING_KEYWORDS
    ):
        return DOCUMENT_ROLE_SUPPORTING

    # QA / qa가 독립 토큰으로 존재하는 경우
    if re.search(
        r"(^|[^a-z0-9])qa([^a-z0-9]|$)",
        text,
    ):
        return DOCUMENT_ROLE_SUPPORTING

    if any(
        keyword in text
        for keyword in PRIMARY_KEYWORDS
    ):
        return DOCUMENT_ROLE_PRIMARY

    return DOCUMENT_ROLE_UNKNOWN