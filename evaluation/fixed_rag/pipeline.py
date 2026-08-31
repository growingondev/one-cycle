from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rag.generation.config import DEFAULT_GENERATION_CONFIG, GenerationConfig
from rag.generation.generator import generate_answer
from rag.generation.models import GeneratedAnswer
from rag.retrieval.config import DEFAULT_RETRIEVAL_CONFIG, RetrievalConfig

from .retriever import FixedFileRetriever


class FixedRAGPipelineError(RuntimeError):
    """고정 문서 파일 기반 RAG 처리 중 발생하는 오류."""


@dataclass
class FixedRAGRun:
    generated: GeneratedAnswer
    retrieval_results: list


@dataclass
class FixedRAGPipeline:
    retriever: FixedFileRetriever
    generation_config: GenerationConfig
    announcement_directory: str
    document_format: str

    @classmethod
    def from_files(
        cls,
        *,
        chunks_path: str | Path,
        embeddings_path: str | Path,
        announcement_directory: str,
        document_format: str,
        top_k: int = 5,
        retrieval_config: RetrievalConfig = DEFAULT_RETRIEVAL_CONFIG,
        generation_config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
    ) -> "FixedRAGPipeline":
        generation_config.validate()

        document_format = document_format.strip().lower()
        if document_format not in {"hwp", "hwpx"}:
            raise FixedRAGPipelineError(
                "document_format은 hwp 또는 hwpx여야 합니다."
            )

        retriever = FixedFileRetriever.from_files(
            chunks_path=chunks_path,
            embeddings_path=embeddings_path,
            retrieval_config=retrieval_config,
            top_k=top_k,
        )

        return cls(
            retriever=retriever,
            generation_config=generation_config,
            announcement_directory=announcement_directory,
            document_format=document_format,
        )

    def ask(self, *, query: str) -> FixedRAGRun:
        retrieved = self.retriever.retrieve(query=query)

        if not retrieved:
            raise FixedRAGPipelineError("고정 평가 검색 결과가 없습니다.")

        generated = generate_answer(
            query=query,
            announcement_directory=self.announcement_directory,
            document_format=self.document_format,
            retrieval_results=retrieved,
            config=self.generation_config,
        )

        return FixedRAGRun(
            generated=generated,
            retrieval_results=retrieved,
        )
