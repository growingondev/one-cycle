from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from pipeline.embedding.model_loader import LoadedEmbeddingModel


class QueryEmbeddingError(RuntimeError):
    """RAG 질문 임베딩 생성 중 발생하는 오류."""


def _extract_query_vector(output: Any) -> np.ndarray:
    if not isinstance(output, dict) or "dense_vecs" not in output:
        raise QueryEmbeddingError(
            "BGE-M3 encode 결과에 dense_vecs가 없습니다."
        )

    vectors = np.asarray(
        output["dense_vecs"],
        dtype=np.float32,
    )

    if vectors.ndim != 2 or vectors.shape[0] != 1:
        raise QueryEmbeddingError(
            f"질문 임베딩 shape 오류: {vectors.shape}"
        )

    vector = vectors[0]

    if not np.isfinite(vector).all():
        raise QueryEmbeddingError(
            "질문 임베딩에 NaN/Infinity가 있습니다."
        )

    return vector


def embed_query(
    loaded_model: "LoadedEmbeddingModel",
    query: str,
    *,
    max_length: int,
    normalize: bool = True,
) -> np.ndarray:
    """
    사용자 질문을 BGE-M3 dense vector로 변환한다.
    """

    query = query.strip()

    if not query:
        raise QueryEmbeddingError(
            "검색 질문이 비어 있습니다."
        )

    try:
        output = loaded_model.model.encode(
            [query],
            batch_size=1,
            max_length=max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
    except Exception as exc:
        raise QueryEmbeddingError(
            f"질문 임베딩 생성 실패: {exc}"
        ) from exc

    vector = _extract_query_vector(output)

    if normalize:
        norm = float(np.linalg.norm(vector))

        if norm == 0:
            raise QueryEmbeddingError(
                "질문 임베딩이 0 벡터입니다."
            )

        vector = vector / norm

    return vector.astype(
        np.float32,
        copy=False,
    )
