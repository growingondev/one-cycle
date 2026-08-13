from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np

from .models import EmbeddingItem
from .model_loader import LoadedEmbeddingModel
from .validator import validate_embeddings


class EmbeddingGenerationError(RuntimeError):
    """임베딩 벡터 생성에 실패했을 때 발생하는 오류."""


@dataclass(frozen=True)
class GeneratedEmbeddings:
    """
    한 문서의 임베딩 생성 결과.

    vectors:
        shape = (청크 수, 임베딩 차원)

    elapsed_seconds:
        모델 추론에 걸린 시간.

    normalized:
        L2 정규화 여부.
    """

    vectors: np.ndarray
    elapsed_seconds: float
    normalized: bool

    @property
    def count(self) -> int:
        return int(self.vectors.shape[0])

    @property
    def dimension(self) -> int:
        return int(self.vectors.shape[1])


def _normalize_l2(vectors: np.ndarray) -> np.ndarray:
    """
    각 임베딩 벡터를 L2 norm 1로 정규화한다.

    0 벡터는 검증 단계에서 오류 처리한다.
    """

    norms = np.linalg.norm(
        vectors,
        axis=1,
        keepdims=True,
    )

    # 0으로 나누는 상황은 임시로 방지하고,
    # 이후 validate_embeddings에서 0 벡터를 오류 처리한다.
    safe_norms = np.where(norms == 0, 1.0, norms)

    return vectors / safe_norms


def _extract_dense_vectors(
    encode_output: Any,
) -> np.ndarray:
    """
    BGEM3FlagModel.encode() 결과에서 dense_vecs를 꺼낸다.
    """

    if not isinstance(encode_output, dict):
        raise EmbeddingGenerationError(
            "BGE-M3 encode 결과가 dict가 아닙니다. "
            f"actual_type={type(encode_output).__name__}"
        )

    if "dense_vecs" not in encode_output:
        raise EmbeddingGenerationError(
            "BGE-M3 encode 결과에 dense_vecs가 없습니다. "
            f"keys={list(encode_output.keys())}"
        )

    try:
        vectors = np.asarray(
            encode_output["dense_vecs"],
            dtype=np.float32,
        )
    except (TypeError, ValueError) as exc:
        raise EmbeddingGenerationError(
            "dense_vecs를 float32 NumPy 배열로 변환하지 못했습니다."
        ) from exc

    if vectors.ndim != 2:
        raise EmbeddingGenerationError(
            "dense_vecs는 2차원 배열이어야 합니다. "
            f"actual_shape={vectors.shape}"
        )

    return vectors


def generate_embeddings(
    loaded_model: LoadedEmbeddingModel,
    items: list[EmbeddingItem],
    *,
    batch_size: int,
    max_length: int,
    normalize_embeddings: bool = True,
) -> GeneratedEmbeddings:
    """
    청크 목록의 embedding_text를 BGE-M3로 벡터화한다.

    Args:
        loaded_model:
            model_loader.py에서 생성한 BGE-M3 모델.

        items:
            input_loader.py에서 생성한 임베딩 대상 목록.

        batch_size:
            BGE-M3 encode 배치 크기.

        max_length:
            모델에 전달할 최대 토큰 길이.

        normalize_embeddings:
            True이면 생성된 벡터를 L2 정규화한다.

    Returns:
        GeneratedEmbeddings

    Raises:
        EmbeddingGenerationError:
            설정 또는 모델 결과에 문제가 있는 경우.
    """

    if not items:
        raise EmbeddingGenerationError(
            "임베딩할 청크가 없습니다."
        )

    if batch_size <= 0:
        raise EmbeddingGenerationError(
            f"batch_size는 1 이상이어야 합니다: {batch_size}"
        )

    if max_length <= 0:
        raise EmbeddingGenerationError(
            f"max_length는 1 이상이어야 합니다: {max_length}"
        )

    texts = [
        item.embedding_text.strip()
        for item in items
    ]

    empty_indexes = [
        index
        for index, text in enumerate(texts)
        if not text
    ]

    if empty_indexes:
        raise EmbeddingGenerationError(
            "비어 있는 embedding_text가 있습니다. "
            f"indexes={empty_indexes[:20]}"
        )

    print()
    print("=" * 70)
    print("청크 임베딩 생성")
    print("=" * 70)
    print(f"청크 수       : {len(items)}")
    print(f"배치 크기     : {batch_size}")
    print(f"최대 길이     : {max_length}")
    print(f"L2 정규화     : {normalize_embeddings}")
    print(f"모델          : {loaded_model.runtime.model_name}")
    print(f"장치          : {loaded_model.runtime.device}")

    started_at = perf_counter()

    try:
        encode_output = loaded_model.model.encode(
            texts,
            batch_size=batch_size,
            max_length=max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
    except RuntimeError as exc:
        message = str(exc)

        if "out of memory" in message.lower():
            raise EmbeddingGenerationError(
                "GPU 메모리가 부족합니다. "
                "config.py의 BATCH_SIZE를 더 작게 설정하세요. "
                f"현재 batch_size={batch_size}"
            ) from exc

        raise EmbeddingGenerationError(
            f"BGE-M3 추론 중 오류가 발생했습니다: {exc}"
        ) from exc
    except Exception as exc:
        raise EmbeddingGenerationError(
            f"BGE-M3 임베딩 생성에 실패했습니다: {exc}"
        ) from exc

    vectors = _extract_dense_vectors(encode_output)

    if normalize_embeddings:
        vectors = _normalize_l2(vectors).astype(
            np.float32,
            copy=False,
        )

    elapsed_seconds = perf_counter() - started_at

    validation = validate_embeddings(
        vectors,
        items,
    )
    validation.raise_for_errors()

    print()
    print("[임베딩 생성 완료]")
    print(f"벡터 shape    : {vectors.shape}")
    print(f"벡터 차원     : {vectors.shape[1]}")
    print(f"소요 시간     : {elapsed_seconds:.2f}초")
    print(
        f"청크당 평균   : "
        f"{elapsed_seconds / len(items):.4f}초"
    )

    return GeneratedEmbeddings(
        vectors=vectors,
        elapsed_seconds=elapsed_seconds,
        normalized=normalize_embeddings,
    )