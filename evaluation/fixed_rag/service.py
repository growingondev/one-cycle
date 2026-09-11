from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .pipeline import FixedRAGPipeline


# ============================================================
# Path
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVALUATION_DIR = PROJECT_ROOT / "evaluation"

FIXED_OUTPUT_ROOT = (
    EVALUATION_DIR
    / "outputs"
)


# ============================================================
# Dataset Mapping
# ============================================================

#
# 평가 Dataset 코드
#     ↓
# 고정 평가 문서 ID
#
FIXED_DATASETS = {
    "GC": "DOC_GC_001",
    "BD": "DOC_BD_001",
}


class FixedRAGServiceError(RuntimeError):
    """고정 평가 RAG Service 오류."""


# ============================================================
# Dataset Path
# ============================================================

def _dataset_root(
    dataset: str,
) -> Path:
    """
    Dataset 코드에 해당하는 고정 평가 Output 경로를 반환한다.

    예:
        GC
        -> evaluation/outputs/DOC_GC_001

        BD
        -> evaluation/outputs/DOC_BD_001
    """

    dataset = (
        dataset
        .strip()
        .upper()
    )

    if not dataset:
        raise FixedRAGServiceError(
            "dataset이 비어 있습니다."
        )

    document_id = FIXED_DATASETS.get(
        dataset
    )

    if document_id is None:
        raise FixedRAGServiceError(
            "지원하지 않는 고정 평가 dataset입니다: "
            f"{dataset}\n"
            "사용 가능: "
            + ", ".join(
                sorted(FIXED_DATASETS)
            )
        )

    return (
        FIXED_OUTPUT_ROOT
        / document_id
    ).resolve()


# ============================================================
# Artifact 탐색
# ============================================================

def _find_single_file(
    root: Path,
    *,
    filename: str,
    preferred_directory: str,
) -> Path:
    """
    Output 폴더에서 필요한 산출물 하나를 찾는다.

    우선:
        preferred_directory 내부 검색

    예:
        04_chunks/**/chunks.json
        05_embeddings/**/embeddings.npy
    """

    preferred_root = (
        root
        / preferred_directory
    )

    if preferred_root.exists():
        preferred_candidates = sorted(
            preferred_root.rglob(
                filename
            )
        )

        if len(
            preferred_candidates
        ) == 1:
            return preferred_candidates[0]

        if len(
            preferred_candidates
        ) > 1:
            raise FixedRAGServiceError(
                f"{filename}이 여러 개 발견되었습니다.\n"
                + "\n".join(
                    str(path)
                    for path
                    in preferred_candidates
                )
            )

    #
    # 혹시 Pipeline 출력 구조가 약간 다른 경우를 위해
    # 문서 Output 전체에서도 한 번 검색한다.
    #
    candidates = sorted(
        root.rglob(
            filename
        )
    )

    if not candidates:
        raise FileNotFoundError(
            f"{filename}을 찾을 수 없습니다: "
            f"{root}"
        )

    if len(candidates) > 1:
        raise FixedRAGServiceError(
            f"{filename}이 여러 개 발견되었습니다.\n"
            "어떤 파일을 사용할지 결정할 수 없습니다.\n"
            + "\n".join(
                str(path)
                for path
                in candidates
            )
        )

    return candidates[0]


def _resolve_artifacts(
    dataset: str,
) -> dict[str, Any]:
    """
    고정 평가 Pipeline 결과에서

    - chunks.json
    - embeddings.npy

    를 찾는다.

    예:

    evaluation/
      outputs/
        DOC_GC_001/
          04_chunks/
            hwpx/
              chunks.json

          05_embeddings/
            hwpx/
              embeddings.npy
    """

    dataset = (
        dataset
        .strip()
        .upper()
    )

    root = _dataset_root(
        dataset
    )

    if not root.is_dir():
        raise FileNotFoundError(
            "고정 평가 문서의 Output 폴더가 없습니다: "
            f"{root}\n"
            "먼저 해당 문서를 기존 Pipeline으로 "
            "처리해야 합니다."
        )

    chunks_path = _find_single_file(
        root,
        filename="chunks.json",
        preferred_directory="04_chunks",
    )

    embeddings_path = _find_single_file(
        root,
        filename="embeddings.npy",
        preferred_directory="05_embeddings",
    )

    #
    # chunks.json 안의 document metadata 읽기
    #
    with chunks_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(
            file
        )

    document = payload.get(
        "document",
        {},
    )

    document_format = str(
        document.get(
            "source_format"
        )
        or "hwpx"
    ).strip().lower()

    announcement_id = str(
        document.get(
            "announcement_id"
        )
        or FIXED_DATASETS[
            dataset
        ]
    )

    return {
        "chunks_path": (
            chunks_path
        ),
        "embeddings_path": (
            embeddings_path
        ),
        "document_format": (
            document_format
        ),
        "announcement_directory": (
            f"fixed_"
            f"{dataset}_"
            f"{announcement_id}"
        ),
    }


# ============================================================
# Pipeline Cache
# ============================================================

@lru_cache(
    maxsize=16
)
def _get_pipeline(
    dataset: str,
    top_k: int,
) -> FixedRAGPipeline:

    artifacts = (
        _resolve_artifacts(
            dataset
        )
    )

    return (
        FixedRAGPipeline
        .from_files(
            chunks_path=artifacts[
                "chunks_path"
            ],
            embeddings_path=artifacts[
                "embeddings_path"
            ],
            announcement_directory=artifacts[
                "announcement_directory"
            ],
            document_format=artifacts[
                "document_format"
            ],
            top_k=top_k,
        )
    )


# ============================================================
# GeneratedAnswer -> text
# ============================================================

def _generated_answer_text(
    generated: Any,
) -> str:
    """
    기존 generate_answer()의 반환 형태가
    GeneratedAnswer 객체이므로 실제 답변 문자열을 꺼낸다.

    혹시 향후 필드명이 변경되더라도
    answer / response / text 순으로 확인한다.
    """

    for name in (
        "answer",
        "response",
        "text",
    ):
        value = getattr(
            generated,
            name,
            None,
        )

        if value is not None:
            return str(
                value
            )

    if isinstance(
        generated,
        dict,
    ):
        for name in (
            "answer",
            "response",
            "text",
        ):
            if name in generated:
                return str(
                    generated[
                        name
                    ]
                )

    return str(
        generated
    )


# ============================================================
# Public Service
# ============================================================

def answer_question(
    *,
    dataset: str,
    question: str,
    top_k: int | None = None,
) -> dict:
    """
    고정 평가 전용 RAG 진입점.

    검색:
        evaluation/outputs/DOC_XXX
        chunks.json + embeddings.npy

    질문 Embedding:
        기존 BGE-M3

    답변 생성:
        기존 rag.generation.generator.generate_answer()

    따라서 DB를 사용하지 않지만
    Generation 로직은 기존 서비스와 동일하다.
    """

    question = (
        question
        .strip()
    )

    if not question:
        raise FixedRAGServiceError(
            "질문이 비어 있습니다."
        )

    dataset = (
        dataset
        .strip()
        .upper()
    )

    #
    # 일반 서비스와 Top-K 기본값을 맞춘다.
    #
    if top_k is None:
        raw_top_k = os.getenv(
            "RAG_DB_TOP_K",
            "5",
        ).strip()

        try:
            top_k = int(
                raw_top_k
            )
        except ValueError as exc:
            raise FixedRAGServiceError(
                "RAG_DB_TOP_K는 정수여야 합니다."
            ) from exc

    if top_k <= 0:
        raise FixedRAGServiceError(
            "top_k는 1 이상이어야 합니다."
        )

    pipeline = _get_pipeline(
        dataset,
        int(top_k),
    )

    run = pipeline.ask(
        query=question,
    )

    #
    # evaluate_rag_fixed.py에서 저장할 Evidence
    #
    evidence: list[dict] = []

    for result in (
        run.retrieval_results
    ):
        item = (
            result
            .search_result
            .item
        )

        evidence.append(
            {
                "chunkId": str(
                    result
                    .search_result
                    .chunk_id
                ),
                "sectionTitle": (
                    item.title
                    or " > ".join(
                        item.section_path
                        or []
                    )
                ),
                "content": (
                    item.content
                ),
                "score": float(
                    result.score
                ),
            }
        )

    answer = (
        _generated_answer_text(
            run.generated
        )
    )

    return {
        "answer": answer,
        "grounded": bool(
            evidence
        ),
        "evidence": evidence,
    }