from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.rag.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"

SUPPORTED_FORMATS = ("hwp", "hwpx")
DEFAULT_FORMAT_PRIORITY = ("hwpx", "hwp")


@dataclass(frozen=True)
class RetrievalConfig:
    vector_top_k: int = 20
    bm25_top_k: int = 20
    hybrid_top_k: int = 20
    rrf_k: int = 60

    outputs_root: Path = OUTPUT_ROOT
    format_priority: tuple[str, ...] = DEFAULT_FORMAT_PRIORITY

    embedding_model_name: str = (
        settings.embedding_model_name
    )

    embedding_model_path: str = (
        settings.embedding_model_path
    )

    query_batch_size: int = 1
    query_max_length: int = 8192

    use_fp16: bool = True
    require_cuda: bool = True
    device_index: int = 0

    def validate(self) -> None:
        values = {
            "vector_top_k": self.vector_top_k,
            "bm25_top_k": self.bm25_top_k,
            "hybrid_top_k": self.hybrid_top_k,
            "rrf_k": self.rrf_k,
            "query_batch_size": self.query_batch_size,
            "query_max_length": self.query_max_length,
        }

        for name, value in values.items():
            if value <= 0:
                raise ValueError(
                    f"{name}는 1 이상이어야 합니다."
                )

        invalid = [
            item
            for item in self.format_priority
            if item not in SUPPORTED_FORMATS
        ]

        if invalid:
            raise ValueError(
                "지원하지 않는 문서 형식이 있습니다: "
                f"{invalid}"
            )


DEFAULT_RETRIEVAL_CONFIG = RetrievalConfig()
