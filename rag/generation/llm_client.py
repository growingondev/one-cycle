from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from .models import PromptPayload


class LLMClientError(RuntimeError):
    """llama.cpp 서버 호출 또는 응답 처리 실패 시 발생."""


def _decode_error_body(exc: error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

    return body[:2000]


def _extract_assistant_content(
    response_data: dict[str, Any],
) -> str:
    choices = response_data.get("choices")

    if not isinstance(choices, list) or not choices:
        raise LLMClientError(
            "LLM 응답에 choices 배열이 없습니다."
        )

    first_choice = choices[0]

    if not isinstance(first_choice, dict):
        raise LLMClientError(
            "LLM 응답의 choices[0] 형식이 올바르지 않습니다."
        )

    message = first_choice.get("message")

    if not isinstance(message, dict):
        raise LLMClientError(
            "LLM 응답에 assistant message가 없습니다."
        )

    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        raise LLMClientError(
            "LLM이 비어 있는 답변을 반환했습니다."
        )

    return content.strip()


def call_llama_cpp_chat(
    prompt: PromptPayload,
    *,
    config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
) -> tuple[str, dict[str, Any]]:
    """
    llama.cpp의 OpenAI 호환 /v1/chat/completions endpoint 호출.
    """
    config.validate()

    payload = {
        "model": config.model_name,
        "messages": prompt.to_messages(),
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "stream": False,
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    http_request = request.Request(
        config.chat_completions_url,
        data=encoded,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(
            http_request,
            timeout=config.timeout_seconds,
        ) as response:
            body = response.read().decode(
                "utf-8",
                errors="replace",
            )
    except error.HTTPError as exc:
        body = _decode_error_body(exc)
        raise LLMClientError(
            "llama.cpp 서버가 HTTP 오류를 반환했습니다.\n"
            f"status={exc.code}\n"
            f"url={config.chat_completions_url}\n"
            f"response={body}"
        ) from exc
    except error.URLError as exc:
        raise LLMClientError(
            "llama.cpp 서버에 연결할 수 없습니다.\n"
            f"url={config.chat_completions_url}\n"
            f"원인={exc.reason}\n"
            "Qwen 모델을 로드한 llama-server가 실행 중인지 확인하세요."
        ) from exc
    except TimeoutError as exc:
        raise LLMClientError(
            "llama.cpp 응답 시간이 초과되었습니다.\n"
            f"timeout={config.timeout_seconds}초"
        ) from exc
    except OSError as exc:
        raise LLMClientError(
            f"llama.cpp 요청 중 운영체제 오류가 발생했습니다: {exc}"
        ) from exc

    try:
        response_data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMClientError(
            "llama.cpp 응답이 올바른 JSON이 아닙니다.\n"
            f"response={body[:2000]}"
        ) from exc

    if not isinstance(response_data, dict):
        raise LLMClientError(
            "llama.cpp 응답 최상위 값은 객체여야 합니다."
        )

    answer = _extract_assistant_content(response_data)

    return answer, response_data
