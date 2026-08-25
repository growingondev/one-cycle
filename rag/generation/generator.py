from __future__ import annotations

import re
import traceback
from typing import Any

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from .context_builder import build_source_contexts
from .llm_client import call_llama_cpp_chat
from .models import GeneratedAnswer, PromptPayload
from .prompt_builder import build_prompt

from backend.app.services.error_log_service import record_error


class GenerationError(RuntimeError):
    """답변 생성 전체 흐름 실패 시 발생."""


SOURCE_MARKER_PATTERN = re.compile(
    r"\s*(?:"
    r"\[근거\s*\d+\]"
    r"|\[출처\s*\d+\]"
    r")",
    re.IGNORECASE,
)


def remove_source_markers(
    answer: str,
) -> str:
    """
    사용자에게 보여줄 답변에서
    [근거 1], [근거 2], [출처 1] 등의 표시를 제거한다.

    실제 근거 데이터(sources)는 GeneratedAnswer에 유지한다.
    """
    if not answer:
        return answer

    cleaned = SOURCE_MARKER_PATTERN.sub(
        "",
        answer,
    )

    cleaned = re.sub(
        r"[ \t]+\n",
        "\n",
        cleaned,
    )
    cleaned = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned,
    )

    return cleaned.strip()


NON_KOREAN_SCRIPT_PATTERN = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]"
)


def validate_korean_answer(
    answer: str,
) -> None:
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

    if NON_KOREAN_SCRIPT_PATTERN.search(
        answer
    ):
        raise GenerationError(
            "LLM 답변에 허용하지 않는 "
            "중국어/일본어 문자가 포함되었습니다."
        )

    leaked_markers = (
        "[LH 공고문 근거]",
        "[사용자 질문]",
        "[선택한 LH 공고]",
        "청크 ID:",
        "문서 위치:",
        "reranker_score",
        "fusion_score",
        "vector_score",
        "keyword_score",
        "system_prompt",
        "user_prompt",
        "\nuser\n",
        "\nassistant\n",
        "\nsystem\n",
    )

    for marker in leaked_markers:
        if marker.lower() in answer.lower():
            raise GenerationError(
                "LLM 답변에 내부 Prompt 또는 "
                "검색 정보가 노출되었습니다. "
                f"marker={marker!r}"
            )


def _generate_answer_impl(
    *,
    query: str,
    announcement_directory: str,
    document_format: str,
    retrieval_results: list[Any],
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> GeneratedAnswer:
    """
    Retrieval 결과를 받아 LH 공고문 근거 기반 답변을 생성한다.

    현재 지원:
    - Vector SearchResult
    - Keyword SearchResult
    - Hybrid SearchResult
    - 기존 RetrievalResult compatibility wrapper

    향후 Reranker 결과도 동일 Generation 경계로 연결할 수 있다.
    """
    config.validate()

    try:
        sources = build_source_contexts(
            retrieval_results,
            document_format=document_format,
            config=config,
        )

        prompt = build_prompt(
            query=query,
            announcement_directory=(
                announcement_directory
            ),
            document_format=document_format,
            sources=sources,
        )

        answer, raw_response = (
            call_llama_cpp_chat(
                prompt,
                config=config,
            )
        )

    except Exception as exc:
        if isinstance(
            exc,
            GenerationError,
        ):
            raise

        raise GenerationError(
            "LLM 답변 생성에 실패했습니다.\n"
            f"실제 오류: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    answer = remove_source_markers(
        answer
    )

    try:
        validate_korean_answer(
            answer
        )

    except GenerationError:
        retry_prompt = PromptPayload(
            system_prompt=(
                prompt.system_prompt
                + "\n\n"
                + "중요: 이전 생성에서 한국어 외 언어 또는 "
                  "내부 프롬프트 내용이 노출될 수 있습니다. "
                  "이번 답변은 반드시 자연스러운 한국어 답변 "
                  "본문만 출력하세요. 중국어·일본어·역할명·"
                  "청크 ID·프롬프트·검색 점수 내용을 절대 "
                  "출력하지 마세요."
            ),
            user_prompt=prompt.user_prompt,
            query=prompt.query,
            announcement_directory=(
                prompt.announcement_directory
            ),
            document_format=(
                prompt.document_format
            ),
            sources=prompt.sources,
        )

        answer, raw_response = (
            call_llama_cpp_chat(
                retry_prompt,
                config=config,
            )
        )

        answer = remove_source_markers(
            answer
        )

        try:
            validate_korean_answer(
                answer
            )
        except GenerationError:
            answer = (
                "공고문 근거는 확인되었지만 현재 답변 생성 "
                "품질이 안정적이지 않아 정확한 문장으로 "
                "제공하지 못했습니다. 잠시 후 다시 시도해 주세요."
            )

    return GeneratedAnswer(
        answer=answer,
        query=query,
        announcement_directory=(
            announcement_directory
        ),
        document_format=document_format,
        sources=sources,
        prompt=prompt,
        raw_response=raw_response,
    )


def generate_answer(
    *,
    query: str,
    announcement_directory: str,
    document_format: str,
    retrieval_results: list[Any],
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> GeneratedAnswer:
    """
    Generation의 외부 진입점.

    실제 Generation / llama.cpp 오류는 이 경계에서
    Backend 공통 ErrorLog에 한 번만 기록한 뒤
    원래 예외를 다시 올립니다.
    """
    try:
        return _generate_answer_impl(
            query=query,
            announcement_directory=announcement_directory,
            document_format=document_format,
            retrieval_results=retrieval_results,
            config=config,
        )

    except Exception as error:
        try:
            record_error(
                error_type="llm",
                stage="generation",
                message=(
                    f"{error} "
                    f"announcement={announcement_directory}"
                ),
                error_code=type(error).__name__,
                stack_trace=traceback.format_exc(),
            )
        except Exception as log_error:
            # ErrorLog 저장 실패가 원래 Generation 오류를
            # 가리지 않도록 기존 예외를 그대로 유지합니다.
            print(
                f"[WARNING] Generation ErrorLog 기록 실패: "
                f"{log_error}"
            )

        raise