from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkingConfig:
    """Chunking parameters.

    Values are intentionally conservative for Korean public-notice documents.
    Tune them after retrieval evaluation, not before.
    """

    schema_version: str = "chunk-v1"
    strategy: str = "hierarchical-structure-aware"

    target_tokens: int = 500
    max_tokens: int = 800
    min_tokens: int = 80
    overlap_tokens: int = 80

    small_key_value_table_tokens: int = 400
    include_section_path_in_content: bool = True
    include_section_path_in_search_text: bool = True
    include_domain_in_search_text: bool = True
    use_paragraph_overlap: bool = True
    use_table_overlap: bool = False

    # A local Hugging Face tokenizer path/name may be supplied later.
    tokenizer_name_or_path: str | None = None
    tokenizer_local_files_only: bool = True

    def validate(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be >= target_tokens")
        if not 0 <= self.overlap_tokens < self.max_tokens:
            raise ValueError("overlap_tokens must be >= 0 and < max_tokens")
        if self.min_tokens < 0:
            raise ValueError("min_tokens must be >= 0")
