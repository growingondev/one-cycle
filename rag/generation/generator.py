from __future__ import annotations

import re

from rag.models import RetrievalResult

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from .context_builder import build_source_contexts
from .llm_client import call_llama_cpp_chat
from .models import GeneratedAnswer, PromptPayload
from .prompt_builder import build_prompt


class GenerationError(RuntimeError):
    """답변 생성 전체 흐름 실패 시 발생."""


# 모델이 실수로 답변에 출력한 근거 번호 제거
SOURCE_MARKER_PATTERN = re.compile(
    r"\s*(?:"
    r"\[근거\s*\d+\]"
    r"|\[출처\s*\d+\]"
    r")",
    re.IGNORECASE,
)


def remove_source_markers(answer: str) -> str:
    """
    사용자에게 보여줄 답변에서
    [근거 1], [근거 2], [출처 1] 등의 표시를 제거한다.

    실제 근거 데이터(sources)는 삭제하지 않고
    GeneratedAnswer에 그대로 유지한다.
    """

    if not answer:
        return answer

    cleaned = SOURCE_MARKER_PATTERN.sub("", answer)

    # 근거 표시 제거 후 생길 수 있는 불필요한 공백 정리
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()



# 한국어 답변에 중국어 한자 영역 또는 일본어 가나가
# 비정상적으로 섞이는 현상을 감지한다.
NON_KOREAN_SCRIPT_PATTERN = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]"
)


def validate_korean_answer(answer: str) -> None:
    """
    사용자에게 반환할 최종 답변 품질을 검증한다.

    - 빈 답변 금지
    - 중국어/일본어 혼입 금지
    - 내부 Prompt / Retrieval 정보 노출 금지
    """

    if not answer or not answer.strip():
        raise GenerationError(
            "LLM이 비어 있는 답변을 생성했습니다."
        )

    if NON_KOREAN_SCRIPT_PATTERN.search(answer):
        raise GenerationError(
            "LLM 답변에 허용하지 않는 중국어/일본어 문자가 포함되었습니다."
        )

    leaked_markers = (
        "[LH 공고문 근거]",
        "[사용자 질문]",
        "[선택한 LH 공고]",
        "청크 ID:",
        "문서 위치:",
        "reranker_score",
        "system_prompt",
        "user_prompt",
        "\nuser\n",
        "\nassistant\n",
        "\nsystem\n",
    )

    for marker in leaked_markers:
        if marker.lower() in answer.lower():
            raise GenerationError(
                "LLM 답변에 내부 Prompt 또는 검색 정보가 노출되었습니다. "
                f"marker={marker!r}"
            )


def generate_answer(
    *,
    query: str,
    announcement_directory: str,
    document_format: str,
    retrieval_results: list[RetrievalResult],
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> GeneratedAnswer:
    config.validate()

    try:
        sources = build_source_contexts(
            retrieval_results,
            document_format=document_format,
            config=config,
        )

        prompt = build_prompt(
            query=query,
            announcement_directory=announcement_directory,
            document_format=document_format,
            sources=sources,
        )

        answer, raw_response = call_llama_cpp_chat(
            prompt,
            config=config,
        )

    except Exception as exc:
        if isinstance(exc, GenerationError):
            raise

        raise GenerationError(
            "Qwen 답변 생성에 실패했습니다.\n"
            f"실제 오류: {type(exc).__name__}: {exc}"
        ) from exc

    # LLM이 근거 번호 등을 생성하더라도
    # 사용자에게 반환하기 전에 제거한다.
    answer = remove_source_markers(answer)

    try:
        validate_korean_answer(answer)

    except GenerationError:
        # 첫 응답이 외국어 혼입 또는 Prompt 노출로
        # 부적절한 경우 한 번만 교정 재생성한다.
        retry_prompt = PromptPayload(
            system_prompt=(
                prompt.system_prompt
                + "\n\n"
                + "중요: 이전 생성에서 한국어 외 언어 또는 "
                  "내부 프롬프트 내용이 노출될 수 있습니다. "
                  "이번 답변은 반드시 자연스러운 한국어 답변 본문만 "
                  "출력하세요. 중국어·일본어·역할명·청크 ID·프롬프트 "
                  "내용을 절대 출력하지 마세요."
            ),
            user_prompt=prompt.user_prompt,
            query=prompt.query,
            announcement_directory=prompt.announcement_directory,
            document_format=prompt.document_format,
            sources=prompt.sources,
        )

        answer, raw_response = call_llama_cpp_chat(
            retry_prompt,
            config=config,
        )

        answer = remove_source_markers(answer)

        try:
            validate_korean_answer(answer)
        except GenerationError:
            answer = (
                "공고문 근거는 확인되었지만 현재 답변 생성 품질이 "
                "안정적이지 않아 정확한 문장으로 제공하지 못했습니다. "
                "잠시 후 다시 시도해 주세요."
            )

    return GeneratedAnswer(
        answer=answer,
        query=query,
        announcement_directory=announcement_directory,
        document_format=document_format,
        sources=sources,
        prompt=prompt,
        raw_response=raw_response,
    )