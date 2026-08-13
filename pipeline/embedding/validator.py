from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .models import EmbeddingItem, LoadedChunkDocument


class EmbeddingValidationError(ValueError):
    """임베딩 입력 또는 출력 검증 실패 오류."""


@dataclass
class ValidationResult:
    """
    검증 결과.

    errors가 존재하면 임베딩을 진행하면 안 된다.
    warnings는 실행은 가능하지만 확인이 필요한 항목이다.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            message = "\n".join(
                f"- {error}" for error in self.errors
            )
            raise EmbeddingValidationError(
                f"임베딩 데이터 검증에 실패했습니다.\n{message}"
            )


def validate_loaded_document(
    document: LoadedChunkDocument,
) -> ValidationResult:
    """
    chunks.json을 읽은 직후 수행하는 입력 검증.
    """

    result = ValidationResult()

    if not document.items:
        result.errors.append(
            f"임베딩 대상 청크가 없습니다: {document.source_path}"
        )
        return result

    seen_chunk_ids: set[str] = set()

    for index, item in enumerate(document.items):
        _validate_item(
            item=item,
            expected_index=index,
            seen_chunk_ids=seen_chunk_ids,
            result=result,
        )

    return result


def _validate_item(
    *,
    item: EmbeddingItem,
    expected_index: int,
    seen_chunk_ids: set[str],
    result: ValidationResult,
) -> None:
    chunk_id = item.chunk_id.strip()
    text = item.embedding_text.strip()
    metadata = item.metadata

    if not chunk_id:
        result.errors.append(
            f"items[{expected_index}].chunk_id가 비어 있습니다."
        )

    if chunk_id in seen_chunk_ids:
        result.errors.append(
            f"중복 chunk_id가 발견되었습니다: {chunk_id}"
        )
    else:
        seen_chunk_ids.add(chunk_id)

    if not text:
        result.errors.append(
            f"embedding_text가 비어 있습니다: {chunk_id}"
        )

    vector_index = metadata.get("vector_index")

    if vector_index != expected_index:
        result.errors.append(
            f"vector_index가 순서와 일치하지 않습니다: "
            f"chunk_id={chunk_id}, "
            f"expected={expected_index}, actual={vector_index}"
        )

    if metadata.get("chunk_id") != item.chunk_id:
        result.errors.append(
            f"item과 metadata의 chunk_id가 다릅니다: {chunk_id}"
        )

    if metadata.get("announcement_id") in (None, ""):
        result.warnings.append(
            f"announcement_id가 없습니다: {chunk_id}"
        )

    if metadata.get("document_id") in (None, ""):
        result.warnings.append(
            f"document_id가 없습니다: {chunk_id}"
        )

    if metadata.get("content") in (None, ""):
        result.warnings.append(
            f"content가 없습니다: {chunk_id}"
        )

    if metadata.get("search_text") in (None, ""):
        result.warnings.append(
            f"search_text가 없습니다: {chunk_id}"
        )

    section_path = metadata.get("section_path")

    if section_path is not None and not isinstance(
        section_path,
        list,
    ):
        result.warnings.append(
            f"section_path가 배열이 아닙니다: {chunk_id}"
        )


def validate_multiple_documents(
    documents: Iterable[LoadedChunkDocument],
) -> ValidationResult:
    """
    여러 chunks.json 파일을 검증한다.

    한 파일 내부의 중복 chunk_id는 오류다.

    서로 다른 입력 파일의 동일 chunk_id는 허용한다.
    동일한 공고의 HWP와 HWPX 청킹 결과에서는 같은 chunk_id가
    나올 수 있으며 결과도 형식별 폴더에 따로 저장되기 때문이다.
    """

    result = ValidationResult()
    source_paths: set[str] = set()

    for document in documents:
        source_path = str(document.source_path)

        if source_path in source_paths:
            result.errors.append(
                f"동일 입력 파일이 중복 지정되었습니다: {source_path}"
            )
            continue

        source_paths.add(source_path)

        document_result = validate_loaded_document(document)

        result.errors.extend(document_result.errors)
        result.warnings.extend(document_result.warnings)

    return result


def validate_embeddings(
    embeddings: np.ndarray,
    items: list[EmbeddingItem],
) -> ValidationResult:
    """
    BGE-M3 임베딩 생성 후 벡터 배열을 검증한다.

    이 함수는 다음 단계의 embedding_generator.py에서 사용한다.
    """

    result = ValidationResult()

    if not isinstance(embeddings, np.ndarray):
        result.errors.append(
            "임베딩 결과는 numpy.ndarray여야 합니다."
        )
        return result

    if embeddings.ndim != 2:
        result.errors.append(
            f"임베딩 배열은 2차원이어야 합니다: "
            f"actual_shape={embeddings.shape}"
        )
        return result

    expected_count = len(items)
    actual_count = embeddings.shape[0]

    if actual_count != expected_count:
        result.errors.append(
            "청크 개수와 임베딩 벡터 개수가 다릅니다: "
            f"chunks={expected_count}, embeddings={actual_count}"
        )

    if embeddings.shape[1] <= 0:
        result.errors.append(
            "임베딩 벡터 차원이 올바르지 않습니다."
        )

    nan_count = int(np.isnan(embeddings).sum())
    inf_count = int(np.isinf(embeddings).sum())

    if nan_count > 0:
        result.errors.append(
            f"임베딩에 NaN 값이 포함되어 있습니다: {nan_count}"
        )

    if inf_count > 0:
        result.errors.append(
            f"임베딩에 Infinity 값이 포함되어 있습니다: {inf_count}"
        )

    if actual_count > 0:
        norms = np.linalg.norm(embeddings, axis=1)
        zero_vector_count = int(np.sum(norms == 0))

        if zero_vector_count > 0:
            result.errors.append(
                "0 벡터가 포함되어 있습니다: "
                f"{zero_vector_count}"
            )

    return result