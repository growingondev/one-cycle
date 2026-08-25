from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline.embedding.model_loader import LoadedEmbeddingModel, load_bge_m3_model
from rag.models import RetrievalResult
from rag.retrieval.config import DEFAULT_RETRIEVAL_CONFIG, RetrievalConfig
from rag.retrieval.models import CorpusItem, SearchResult
from rag.retrieval.query_embedding import embed_query


class FixedFileRetrievalError(RuntimeError):
    """고정 평가 파일 기반 Retrieval 중 발생하는 오류."""


@dataclass
class FixedFileRetriever:
    chunks_path: Path
    embeddings_path: Path
    embedding_model: LoadedEmbeddingModel
    retrieval_config: RetrievalConfig
    top_k: int = 5

    @classmethod
    def from_files(
        cls,
        *,
        chunks_path: str | Path,
        embeddings_path: str | Path,
        retrieval_config: RetrievalConfig = DEFAULT_RETRIEVAL_CONFIG,
        top_k: int = 5,
    ) -> "FixedFileRetriever":
        retrieval_config.validate()

        if top_k <= 0:
            raise FixedFileRetrievalError("top_k는 1 이상이어야 합니다.")

        chunks_path = Path(chunks_path).resolve()
        embeddings_path = Path(embeddings_path).resolve()

        if not chunks_path.is_file():
            raise FileNotFoundError(f"chunks.json을 찾을 수 없습니다: {chunks_path}")
        if not embeddings_path.is_file():
            raise FileNotFoundError(f"embeddings.npy를 찾을 수 없습니다: {embeddings_path}")

        loaded_model = load_bge_m3_model(
            model_name=retrieval_config.embedding_model_name,
            use_fp16=retrieval_config.use_fp16,
            require_cuda=retrieval_config.require_cuda,
            device_index=retrieval_config.device_index,
        )

        return cls(
            chunks_path=chunks_path,
            embeddings_path=embeddings_path,
            embedding_model=loaded_model,
            retrieval_config=retrieval_config,
            top_k=top_k,
        )

    def _load_chunks(self) -> tuple[dict, list[dict]]:
        with self.chunks_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        chunks = payload.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise FixedFileRetrievalError(
                "chunks.json의 'chunks'가 비어 있거나 올바르지 않습니다."
            )
        return payload, chunks

    def _load_embeddings(self) -> np.ndarray:
        embeddings = np.load(self.embeddings_path, allow_pickle=False)

        if embeddings.ndim != 2:
            raise FixedFileRetrievalError(
                f"embeddings.npy는 2차원 배열이어야 합니다. shape={embeddings.shape}"
            )
        if embeddings.shape[1] != 1024:
            raise FixedFileRetrievalError(
                f"Embedding 차원이 1024가 아닙니다. shape={embeddings.shape}"
            )

        return embeddings.astype(np.float32, copy=False)

    def _embed_query(self, query: str) -> np.ndarray:
        vector = embed_query(
            self.embedding_model,
            query,
            max_length=self.retrieval_config.query_max_length,
            normalize=True,
        )
        vector = np.asarray(vector, dtype=np.float32)

        if vector.shape != (1024,):
            raise FixedFileRetrievalError(
                f"질문 임베딩 차원이 1024가 아닙니다. shape={vector.shape}"
            )
        return vector

    def retrieve(self, *, query: str) -> list[RetrievalResult]:
        query = query.strip()
        if not query:
            raise FixedFileRetrievalError("검색 질문이 비어 있습니다.")

        payload, chunks = self._load_chunks()
        embeddings = self._load_embeddings()

        if len(chunks) != embeddings.shape[0]:
            raise FixedFileRetrievalError(
                "Chunk 수와 Embedding 행 수가 일치하지 않습니다. "
                f"chunks={len(chunks)}, embeddings={embeddings.shape[0]}"
            )

        query_vector = self._embed_query(query)

        # 기존 Pipeline embedding은 L2 normalize=True지만,
        # 오래된 산출물에도 안전하도록 다시 정규화한다.
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized_embeddings = embeddings / np.where(norms == 0.0, 1.0, norms)
        scores = normalized_embeddings @ query_vector

        top_indices = np.argsort(scores)[::-1][: min(self.top_k, len(chunks))]
        document_meta = payload.get("document", {})
        results: list[RetrievalResult] = []

        for rank, raw_index in enumerate(top_indices, start=1):
            index = int(raw_index)
            chunk = chunks[index]
            score = float(scores[index])

            chunk_id = str(chunk.get("chunk_id", "")).strip()
            if not chunk_id:
                raise FixedFileRetrievalError(f"chunk_id가 없습니다: index={index}")

            document_id = str(
                chunk.get("document_id")
                or document_meta.get("document_id")
                or ""
            )
            announcement_id = str(
                chunk.get("announcement_id")
                or document_meta.get("announcement_id")
                or ""
            )

            source = chunk.get("source")
            if not isinstance(source, dict):
                source = {}

            item = CorpusItem(
                vector_index=index,
                chunk_id=chunk_id,
                document_id=document_id,
                announcement_id=announcement_id,
                chunk_order=chunk.get("chunk_order"),
                chunk_type=chunk.get("chunk_type"),
                section_path=list(chunk.get("section_path") or []),
                title=chunk.get("title"),
                content=str(chunk.get("content") or ""),
                search_text=str(
                    chunk.get("search_text")
                    or chunk.get("content")
                    or ""
                ),
                source=source,
                raw_metadata={
                    "retrieval": "fixed_file_vector",
                    "source_format": (
                        chunk.get("source_format")
                        or document_meta.get("source_format")
                    ),
                    "embedding_text": chunk.get("embedding_text"),
                    "fixed_vector_index": index,
                },
            )

            search_result = SearchResult(
                vector_index=index,
                chunk_id=chunk_id,
                item=item,
                vector_score=score,
                vector_rank=rank,
                fusion_score=score,
                fusion_rank=rank,
                matched_by={"fixed_file_vector"},
            )

            results.append(
                RetrievalResult(
                    search_result=search_result,
                    score=score,
                    rank=rank,
                )
            )

        return results
