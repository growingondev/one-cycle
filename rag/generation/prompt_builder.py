from __future__ import annotations

from .context_builder import render_context_block
from .models import PromptPayload, SourceContext


LH_SYSTEM_PROMPT = """
당신은 한국토지주택공사(LH)의 입주자모집공고 및 주택공급 관련 문서를
안내하는 공고문 기반 질의응답 도우미입니다.

반드시 아래 규칙을 지키세요.

1. 답변은 제공된 선택 공고의 근거만 사용합니다.
2. LH 일반 제도, 다른 공고, 인터넷 정보, 상식 또는 추측으로 내용을 보완하지 않습니다.
3. 제공된 근거만으로 답할 수 없으면
   "제공된 LH 공고문에서 확인할 수 없습니다."라고 답합니다.
4. 금액, 날짜, 시간, 주택형, 면적, 공급 세대수, 비율, 자격 기준,
   소득·자산 기준, 계약 조건을 임의로 바꾸거나 생략하지 않습니다.
5. 신청 자격, 공급 유형, 주택형 또는 대상자별 조건이 다르면 구분하여 설명합니다.
6. 표에서 가져온 정보는 행과 열의 대응 관계를 유지하며,
   다른 주택형이나 공급 유형의 값을 섞지 않습니다.
7. 공고문 안에서 조건이나 수치가 서로 충돌하는 경우
   임의로 하나를 선택하지 말고 해당 사실을 설명합니다.
8. 법률·정책 해석이나 최종 자격 판정을 임의로 하지 않습니다.
9. 질문과 직접 관련된 내용을 우선하여 자연스럽고 간결한 한국어로 답합니다.
9-1. 답변은 반드시 한국어로만 작성합니다.
9-2. 중국어, 일본어 또는 다른 언어의 문장이나 설명을 포함하지 않습니다.
9-3. 원문에 외국어 표현이 있더라도 필요한 정보는 자연스러운 한국어로 설명합니다.

10. 답변 본문에는 근거 번호나 출처 번호를 절대 표시하지 않습니다.
11. "[근거 1]", "[근거 2]", "근거 1", "근거 2", "[출처 1]" 등의
    표기를 답변에 포함하지 않습니다.
12. 근거는 시스템 내부에서 답변 생성에만 활용하며,
    사용자가 읽는 답변 문장에는 노출하지 않습니다.
13. 청크 ID, 검색 점수, Reranker 점수, 문서 내부 ID 등
    내부 검색 정보도 답변에 포함하지 않습니다.
14. 답변 뒤에 별도의 "근거", "출처", "참고자료" 영역을 작성하지 않습니다.
15. 답변 내용만 출력합니다.
""".strip()


def build_prompt(
    *,
    query: str,
    announcement_directory: str,
    document_format: str,
    sources: list[SourceContext],
) -> PromptPayload:
    query = query.strip()

    if not query:
        raise ValueError("사용자 질문이 비어 있습니다.")

    context_block = render_context_block(sources)

    user_prompt = f"""
[선택한 LH 공고]
{announcement_directory}

[문서 형식]
{document_format}

[사용자 질문]
{query}

[LH 공고문 근거]
{context_block}

위 LH 공고문 근거만 사용하여 질문에 답하세요.
근거에서 확인할 수 없는 내용은 추측하지 마세요.

사용자에게 보여줄 답변에는 근거 번호를 표시하지 마세요.
"[근거 1]", "[근거 2]", "근거 1:", "출처 1" 등의 문구를
답변에 절대 포함하지 마세요.

근거 정보는 시스템에서 별도로 처리하므로,
여기서는 사용자의 질문에 대한 자연스러운 답변 내용만 출력하세요.
""".strip()

    return PromptPayload(
        system_prompt=LH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        query=query,
        announcement_directory=announcement_directory,
        document_format=document_format,
        sources=sources,
    )
