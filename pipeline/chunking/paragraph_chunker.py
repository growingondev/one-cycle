from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import ChunkingConfig
from .text_builder import clean_text
from .tokenizer import TokenCounter


_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=니다\.)\s+|\n(?=[■※●◆◇○▶▷-]|\d+[.)]|[가-힣][.)])"
)


@dataclass(slots=True)
class ParagraphPart:
    paragraphs: list[dict[str, Any]]
    body_text: str
    body_search_text: str
    part_index: int = 1
    part_count: int = 1
    overlap_applied: bool = False


class ParagraphChunker:
    def __init__(self, config: ChunkingConfig, token_counter: TokenCounter) -> None:
        self.config = config
        self.tokens = token_counter

    def chunk(self, paragraphs: list[dict[str, Any]]) -> list[ParagraphPart]:
        if not paragraphs:
            return []

        atomic_parts: list[ParagraphPart] = []
        for paragraph in paragraphs:
            atomic_parts.extend(self._split_single_paragraph(paragraph))

        grouped: list[ParagraphPart] = []
        buffer: list[ParagraphPart] = []
        for part in atomic_parts:
            candidate = self._merge(buffer + [part])
            if buffer and self.tokens.count(candidate.body_text) > self.config.max_tokens:
                grouped.append(self._merge(buffer))
                buffer = [part]
            else:
                buffer.append(part)
                if self.tokens.count(candidate.body_text) >= self.config.target_tokens:
                    grouped.append(candidate)
                    buffer = []
        if buffer:
            tail = self._merge(buffer)
            # Merge a tiny trailing chunk into the previous one if safe.
            if (
                grouped
                and self.tokens.count(tail.body_text) < self.config.min_tokens
                and self.tokens.count(grouped[-1].body_text + "\n" + tail.body_text)
                <= self.config.max_tokens
            ):
                grouped[-1] = self._merge([grouped[-1], tail])
            else:
                grouped.append(tail)

        total = len(grouped)
        for index, part in enumerate(grouped, start=1):
            part.part_index = index
            part.part_count = total
        return grouped

    def _split_single_paragraph(self, paragraph: dict[str, Any]) -> list[ParagraphPart]:
        text = clean_text(paragraph.get("text"))
        search_text = clean_text(paragraph.get("search_text") or text)
        if self.tokens.count(text) <= self.config.max_tokens:
            return [ParagraphPart([paragraph], text, search_text)]

        sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s.strip()]
        if len(sentences) <= 1:
            return self._hard_split(paragraph, text, search_text)

        parts: list[str] = []
        current: list[str] = []
        for sentence in sentences:
            candidate = " ".join([*current, sentence]).strip()
            if current and self.tokens.count(candidate) > self.config.max_tokens:
                parts.append(" ".join(current).strip())
                overlap = ""
                if self.config.use_paragraph_overlap:
                    overlap = self.tokens.tail_by_tokens(
                        parts[-1], self.config.overlap_tokens
                    )
                current = [overlap, sentence] if overlap else [sentence]
            else:
                current.append(sentence)
        if current:
            parts.append(" ".join(current).strip())

        result: list[ParagraphPart] = []
        total = len(parts)
        for index, body in enumerate(parts, start=1):
            result.append(
                ParagraphPart(
                    paragraphs=[paragraph],
                    body_text=body,
                    body_search_text=body,
                    part_index=index,
                    part_count=total,
                    overlap_applied=index > 1 and self.config.use_paragraph_overlap,
                )
            )
        return result

    def _hard_split(
        self,
        paragraph: dict[str, Any],
        text: str,
        search_text: str,
    ) -> list[ParagraphPart]:
        # Character-window fallback calibrated by token counts.
        words = text.split()
        parts: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join([*current, word])
            if current and self.tokens.count(candidate) > self.config.max_tokens:
                parts.append(" ".join(current))
                overlap = self.tokens.tail_by_tokens(parts[-1], self.config.overlap_tokens)
                current = [overlap, word] if overlap else [word]
            else:
                current.append(word)
        if current:
            parts.append(" ".join(current))
        if not parts:
            parts = [text]

        return [
            ParagraphPart(
                paragraphs=[paragraph],
                body_text=body,
                body_search_text=body,
                part_index=index,
                part_count=len(parts),
                overlap_applied=index > 1 and self.config.use_paragraph_overlap,
            )
            for index, body in enumerate(parts, start=1)
        ]

    @staticmethod
    def _merge(parts: list[ParagraphPart]) -> ParagraphPart:
        paragraphs: list[dict[str, Any]] = []
        body: list[str] = []
        search_body: list[str] = []
        overlap = False
        for part in parts:
            paragraphs.extend(part.paragraphs)
            if part.body_text:
                body.append(part.body_text)
            if part.body_search_text:
                search_body.append(part.body_search_text)
            overlap = overlap or part.overlap_applied
        return ParagraphPart(
            paragraphs=paragraphs,
            body_text="\n".join(body),
            body_search_text="\n".join(search_body),
            overlap_applied=overlap,
        )
