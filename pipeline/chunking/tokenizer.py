from __future__ import annotations

import re
from typing import Protocol


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...

    def tail_by_tokens(self, text: str, token_count: int) -> str: ...


class RegexTokenCounter:
    """Dependency-free approximation used until the embedding tokenizer is fixed.

    Korean syllables, latin words, numbers, and punctuation are counted as units.
    It is deterministic and safe for chunking tests, but final token statistics
    should be regenerated with the exact embedding-model tokenizer.
    """

    name = "regex-approx-v1"
    _pattern = re.compile(r"[가-힣]|[A-Za-z]+|\d+(?:[.,:/-]\d+)*|[^\s]", re.UNICODE)

    def encode_units(self, text: str) -> list[str]:
        return self._pattern.findall(text or "")

    def count(self, text: str) -> int:
        return len(self.encode_units(text))

    def tail_by_tokens(self, text: str, token_count: int) -> str:
        if token_count <= 0:
            return ""
        # Sentence/line-aware approximation: keep adding lines from the end.
        units = self.encode_units(text)
        if len(units) <= token_count:
            return text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        selected: list[str] = []
        total = 0
        for line in reversed(lines):
            n = self.count(line)
            if selected and total + n > token_count:
                break
            selected.append(line)
            total += n
            if total >= token_count:
                break
        return "\n".join(reversed(selected)).strip()


class HuggingFaceTokenCounter:
    def __init__(self, name_or_path: str, *, local_files_only: bool = True) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required for HuggingFaceTokenCounter"
            ) from exc
        self.tokenizer = AutoTokenizer.from_pretrained(
            name_or_path,
            local_files_only=local_files_only,
            trust_remote_code=True,
        )
        self.name = f"hf:{name_or_path}"

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text or "", add_special_tokens=False))

    def tail_by_tokens(self, text: str, token_count: int) -> str:
        ids = self.tokenizer.encode(text or "", add_special_tokens=False)
        if token_count <= 0:
            return ""
        return self.tokenizer.decode(ids[-token_count:], skip_special_tokens=True).strip()


def build_token_counter(
    name_or_path: str | None,
    *,
    local_files_only: bool = True,
) -> TokenCounter:
    if not name_or_path:
        return RegexTokenCounter()
    return HuggingFaceTokenCounter(
        name_or_path,
        local_files_only=local_files_only,
    )
