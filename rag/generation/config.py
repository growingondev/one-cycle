from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return int(value)


@dataclass(frozen=True)
class GenerationConfig:
    """llama.cpp 기반 Qwen 답변 생성 설정."""

    base_url: str = os.getenv(
        "LLAMA_BASE_URL",
        "http://127.0.0.1:8080",
    ).strip()

    chat_completions_path: str = "/v1/chat/completions"

    model_name: str = os.getenv(
        "LLAMA_MODEL",
        "qwen",
    ).strip()

    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512

    timeout_seconds: int = _env_int(
        "LLAMA_TIMEOUT_SECONDS",
        180,
    )

    context_top_k: int = 5

    max_chars_per_context: int = 6000

    require_source_markers: bool = True

    def validate(self) -> None:
        if not self.base_url:
            raise ValueError(
                "LLAMA_BASE_URL이 비어 있습니다."
            )

        if not self.chat_completions_path.startswith("/"):
            raise ValueError(
                "chat_completions_path는 '/'로 시작해야 합니다."
            )

        if not self.model_name:
            raise ValueError(
                "LLAMA_MODEL이 비어 있습니다."
            )

        if self.temperature < 0:
            raise ValueError(
                "temperature는 0 이상이어야 합니다."
            )

        if not 0 < self.top_p <= 1:
            raise ValueError(
                "top_p는 0 초과 1 이하여야 합니다."
            )

        if self.max_tokens <= 0:
            raise ValueError(
                "max_tokens는 1 이상이어야 합니다."
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "LLAMA_TIMEOUT_SECONDS는 1 이상이어야 합니다."
            )

        if self.context_top_k <= 0:
            raise ValueError(
                "context_top_k는 1 이상이어야 합니다."
            )

        if self.max_chars_per_context <= 0:
            raise ValueError(
                "max_chars_per_context는 1 이상이어야 합니다."
            )

    @property
    def chat_completions_url(self) -> str:
        return (
            self.base_url.rstrip("/")
            + self.chat_completions_path
        )


DEFAULT_GENERATION_CONFIG = GenerationConfig()
