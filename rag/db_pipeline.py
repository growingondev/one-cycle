from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text

from backend.app.db.session import SessionLocal
from pipeline.embedding.model_loader import (
    LoadedEmbeddingModel,
    load_bge_m3_model,
)
from rag.generation.config import (
    DEFAULT_GENERATION_CONFIG,
    GenerationConfig,
)
from rag.generation.generator import generate_answer
from rag.generation.models import GeneratedAnswer
from rag.models import RetrievalResult
from rag.retrieval.config import (
    DEFAULT_RETRIEVAL_CONFIG,
    RetrievalConfig,
)
from rag.retrieval.models import CorpusItem, SearchResult
from rag.retrieval.query_embedding import embed_query


class DBRAGPipelineError(RuntimeError):
    """DB 기반 RAG 처리 중 발생하는 오류."""


class DBRAGNoEvidenceError(DBRAGPipelineError):
    """선택한 공고에서 검색 가능한 근거가 없을 때 발생."""


@dataclass
class DBRAGPipeline:
    """
    BGE-M3 Query Embedding
    → PostgreSQL + pgvector
    → 선택 공고 Top-K
    → 기존 Qwen Generation
    """

    embedding_model: LoadedEmbeddingModel
    retrieval_config: RetrievalConfig
    generation_config: GenerationConfig
    top_k: int = 5

    @classmethod
    def from_database(
        cls,
        *,
        retrieval_config: RetrievalConfig = DEFAULT_RETRIEVAL_CONFIG,
        generation_config: GenerationConfig = DEFAULT_GENERATION_CONFIG,
    ) -> "DBRAGPipeline":
        retrieval_config.validate()
        generation_config.validate()

        raw_top_k = os.getenv(
            "RAG_DB_TOP_K",
            "5",
        ).strip()

        try:
            top_k = int(raw_top_k)
        except ValueError as exc:
            raise DBRAGPipelineError(
                "RAG_DB_TOP_K는 정수여야 합니다."
            ) from exc

        if top_k <= 0:
            raise DBRAGPipelineError(
                "RAG_DB_TOP_K는 1 이상이어야 합니다."
            )

        loaded_model = load_bge_m3_model(
            model_name=(
                retrieval_config.embedding_model_name
            ),
            use_fp16=retrieval_config.use_fp16,
            require_cuda=retrieval_config.require_cuda,
            device_index=retrieval_config.device_index,
        )

        return cls(
            embedding_model=loaded_model,
            retrieval_config=retrieval_config,
            generation_config=generation_config,
            top_k=top_k,
        )

    def _embed_query(
        self,
        query: str,
    ):
        return embed_query(
            self.embedding_model,
            query,
            max_length=(
                self.retrieval_config.query_max_length
            ),
            normalize=True,
        )

    @staticmethod
    def _vector_literal(vector) -> str:
        """
        numpy 1차원 벡터를 pgvector가 읽을 수 있는
        '[0.1,0.2,...]' 문자열로 변환한다.
        """

        return (
            "["
            + ",".join(
                format(float(value), ".9g")
                for value in vector
            )
            + "]"
        )

    def retrieve(
        self,
        *,
        announcement_id: int,
        query: str,
    ) -> list[RetrievalResult]:
        """
        현재 활성 Collection 안에서 요청한 announcement_id의
        Chunk만 pgvector cosine distance로 검색한다.

        Reranker는 사용하지 않는다.
        기존 Generation 인터페이스 호환을 위해
        pgvector 점수/순위를 RetrievalResult 형태로 감싼다.
        """

        query = query.strip()

        if not query:
            raise DBRAGPipelineError(
                "검색 질문이 비어 있습니다."
            )

        query_vector = self._embed_query(query)

        if query_vector.shape != (1024,):
            raise DBRAGPipelineError(
                "질문 임베딩 차원이 1024가 아닙니다: "
                f"{query_vector.shape}"
            )

        vector_literal = self._vector_literal(
            query_vector
        )

        sql = text(
            """
            SELECT
                c.id AS db_chunk_id,
                c.external_chunk_key,
                c.document_id,
                c.document_format,
                c.content_type,
                c.section_path,
                c.title,
                c.content,
                c.search_text,
                c.source_reference,
                1 - (
                    e.embedding
                    <=> CAST(:query_vector AS vector)
                ) AS similarity
            FROM system_state ss
            JOIN announcements a
              ON a.collection_run_id
               = ss.active_collection_run_id
            JOIN chunks c
              ON c.announcement_id = a.id
            JOIN chunk_sets cs
              ON cs.id = c.chunk_set_id
             AND cs.is_active = TRUE
            JOIN processing_runs pr
              ON pr.id = cs.processing_run_id
             AND pr.is_active = TRUE
            JOIN embeddings e
              ON e.chunk_id = c.id
            WHERE a.id = :announcement_id
              AND c.status = 'completed'
              AND e.status = 'completed'
              AND e.model_name = :model_name
              AND e.dimension = 1024
              AND e.normalized = TRUE
              AND e.embedding IS NOT NULL
            ORDER BY
                e.embedding
                <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        )

        params = {
            "announcement_id": announcement_id,
            "model_name": (
                self.retrieval_config.embedding_model_name
            ),
            "query_vector": vector_literal,
            "top_k": self.top_k,
        }

        with SessionLocal() as db:
            rows = (
                db.execute(sql, params)
                .mappings()
                .all()
            )

        if not rows:
            return []

        results: list[RetrievalResult] = []

        for rank, row in enumerate(
            rows,
            start=1,
        ):
            score = float(row["similarity"])

            item = CorpusItem(
                vector_index=rank - 1,
                chunk_id=row[
                    "external_chunk_key"
                ],
                document_id=str(
                    row["document_id"]
                ),
                announcement_id=str(
                    announcement_id
                ),
                chunk_order=None,
                chunk_type=row[
                    "content_type"
                ],
                section_path=list(
                    row["section_path"] or []
                ),
                title=row["title"],
                content=row["content"],
                search_text=(
                    row["search_text"]
                    or row["content"]
                ),
                source=(
                    row["source_reference"]
                    or {}
                ),
                raw_metadata={
                    "db_chunk_id": (
                        row["db_chunk_id"]
                    ),
                    "retrieval": "pgvector",
                },
            )

            search_result = SearchResult(
                vector_index=rank - 1,
                chunk_id=row[
                    "external_chunk_key"
                ],
                item=item,
                vector_score=score,
                vector_rank=rank,
                fusion_score=score,
                fusion_rank=rank,
                matched_by={"pgvector"},
            )

            # Reranker를 실행하는 것이 아니다.
            # 기존 Generation 계약을 재사용하기 위한
            # compatibility wrapper이다.
            results.append(
                RetrievalResult(
                    search_result=search_result,
                    score=score,
                    rank=rank,
                )
            )

        return results

    def ask(
        self,
        *,
        announcement_id: int,
        query: str,
    ) -> GeneratedAnswer:
        # hybrid_search.py가 DBRAGPipeline을 참조하므로
        # 순환 import를 피하기 위해 지연 import한다.
        from rag.retrieval.hybrid_search import (
            HybridSearchConfig,
            hybrid_search,
        )

        retrieved = hybrid_search(
            pipeline=self,
            announcement_id=announcement_id,
            query=query,
            config=HybridSearchConfig(
                vector_top_k=self.retrieval_config.vector_top_k,
                keyword_top_k=self.retrieval_config.bm25_top_k,
                hybrid_top_k=self.retrieval_config.hybrid_top_k,
                rrf_k=self.retrieval_config.rrf_k,
            ),
        )

        if not retrieved:
            raise DBRAGNoEvidenceError(
                "선택한 공고에서 검색 가능한 근거가 없습니다. "
                f"announcement_id={announcement_id}"
            )

        # MVP 대표 문서 형식은 환경변수에서 사용한다.
        document_format = os.getenv(
            "MVP_DOCUMENT_FORMAT",
            "hwpx",
        ).strip().lower()

        return generate_answer(
            query=query,
            announcement_directory=(
                f"announcement_{announcement_id:03d}"
            ),
            document_format=document_format,
            retrieval_results=retrieved,
            config=self.generation_config,
        )
