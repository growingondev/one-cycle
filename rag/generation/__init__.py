"""LH 공고문 근거 기반 답변 생성 패키지."""

from .config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from .models import GeneratedAnswer, PromptPayload, SourceContext


__all__ = [
    "DEFAULT_GENERATION_CONFIG",
    "GeneratedAnswer",
    "GenerationConfig",
    "GenerationError",
    "PromptPayload",
    "SourceContext",
    "generate_answer",
]


def __getattr__(name: str):
    if name in {
        "GenerationError",
        "generate_answer",
    }:
        from .generator import (
            GenerationError,
            generate_answer,
        )

        globals()["GenerationError"] = GenerationError
        globals()["generate_answer"] = generate_answer

        return globals()[name]

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
