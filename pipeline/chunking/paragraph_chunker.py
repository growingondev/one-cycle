from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import ChunkingConfig
from .text_builder import clean_text
from .tokenizer import TokenCounter

_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=니다\.)\s+|\n(?=[■※●◆◇○▶▷▪•★-]|\d+[.)]|[가-힣][.)])"
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

    def chunk(self, paragraphs, *, target_tokens=None, max_tokens=None) -> list[ParagraphPart]:
        if not paragraphs:
            return []
        target = min(target_tokens or self.config.target_tokens, max_tokens or self.config.max_tokens)
        maximum = max_tokens or self.config.max_tokens
        atomic: list[ParagraphPart] = []
        for p in paragraphs:
            atomic.extend(self._split_single_paragraph(p, maximum))
        grouped: list[ParagraphPart] = []
        buffer: list[ParagraphPart] = []
        for part in atomic:
            candidate = self._merge(buffer + [part])
            if buffer and self.tokens.count(candidate.body_text) > maximum:
                grouped.append(self._merge(buffer))
                buffer = [part]
            else:
                buffer.append(part)
                if self.tokens.count(candidate.body_text) >= target:
                    grouped.append(candidate)
                    buffer = []
        if buffer:
            tail = self._merge(buffer)
            if (grouped and self.tokens.count(tail.body_text) < self.config.min_tokens
                    and self.tokens.count(grouped[-1].body_text + "\n" + tail.body_text) <= maximum):
                grouped[-1] = self._merge([grouped[-1], tail])
            else:
                grouped.append(tail)
        total = len(grouped)
        for i, part in enumerate(grouped, 1):
            part.part_index, part.part_count = i, total
        return grouped

    def _split_single_paragraph(self, paragraph, maximum) -> list[ParagraphPart]:
        text = clean_text(paragraph.get("text"))
        search = clean_text(paragraph.get("search_text") or text)
        if self.tokens.count(text) <= maximum:
            return [ParagraphPart([paragraph], text, search)]
        sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s.strip()]
        if len(sentences) <= 1:
            return self._hard_split(paragraph, text, maximum)
        parts, current = [], []
        for sentence in sentences:
            if self.tokens.count(sentence) > maximum:
                if current:
                    parts.append(" ".join(current).strip())
                    current = []
                parts.extend(self._split_words(sentence, maximum))
                continue
            candidate = " ".join([*current, sentence]).strip()
            if current and self.tokens.count(candidate) > maximum:
                parts.append(" ".join(current).strip())
                overlap = self.tokens.tail_by_tokens(
                    parts[-1], min(self.config.overlap_tokens, max(0, maximum - 1))
                ) if self.config.use_paragraph_overlap else ""
                current = [overlap, sentence] if overlap else [sentence]
            else:
                current.append(sentence)
        if current:
            parts.append(" ".join(current).strip())
        return [
            ParagraphPart(
                [paragraph], body, body, i, len(parts),
                i > 1 and self.config.use_paragraph_overlap
            )
            for i, body in enumerate(parts, 1)
        ]

    def _hard_split(self, paragraph, text, maximum) -> list[ParagraphPart]:
        parts = self._split_words(text, maximum)
        return [
            ParagraphPart(
                [paragraph], body, body, i, len(parts),
                i > 1 and self.config.use_paragraph_overlap
            )
            for i, body in enumerate(parts, 1)
        ]

    def _split_words(self, text, maximum) -> list[str]:
        words, parts, current = text.split(), [], []
        for word in words:
            if self.tokens.count(word) > maximum:
                if current:
                    parts.append(" ".join(current).strip())
                    current = []
                parts.extend(self._split_chars(word, maximum))
                continue
            candidate = " ".join([*current, word]).strip()
            if current and self.tokens.count(candidate) > maximum:
                parts.append(" ".join(current).strip())
                overlap = self.tokens.tail_by_tokens(
                    parts[-1], min(self.config.overlap_tokens, max(0, maximum - 1))
                ) if self.config.use_paragraph_overlap else ""
                current = [overlap, word] if overlap else [word]
            else:
                current.append(word)
        if current:
            parts.append(" ".join(current).strip())
        return [p for p in parts if p] or [text]

    def _split_chars(self, token, maximum) -> list[str]:
        parts, current = [], ""
        for char in token:
            candidate = current + char
            if current and self.tokens.count(candidate) > maximum:
                parts.append(current)
                current = char
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    @staticmethod
    def _merge(parts) -> ParagraphPart:
        paragraphs, body, search = [], [], []
        overlap = False
        for part in parts:
            paragraphs.extend(part.paragraphs)
            if part.body_text:
                body.append(part.body_text)
            if part.body_search_text:
                search.append(part.body_search_text)
            overlap = overlap or part.overlap_applied
        return ParagraphPart(paragraphs, "\n".join(body), "\n".join(search), overlap_applied=overlap)
