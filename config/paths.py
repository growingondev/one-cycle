from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# ============================================================
# 프로젝트 기본 경로
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TEST_DOCUMENT_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "documents"
OUTPUT_ROOT = PROJECT_ROOT / "outputs"


# ============================================================
# 문서별 출력 경로
# ============================================================

@dataclass(frozen=True)
class DocumentOutputPaths:
    root: Path
    parsed: Path
    normalized: Path
    structured: Path
    chunks: Path
    embeddings: Path


def get_document_output_paths(
    document_id: str,
) -> DocumentOutputPaths:
    """
    document_id 기준으로 Pipeline 출력 경로를 반환합니다.
    """

    document_id = document_id.strip()

    if not document_id:
        raise ValueError(
            "document_id가 비어 있습니다."
        )

    if (
        "/" in document_id
        or "\\" in document_id
        or ".." in document_id
    ):
        raise ValueError(
            f"잘못된 document_id입니다: {document_id}"
        )

    root = (
        OUTPUT_ROOT
        / document_id
    )

    return DocumentOutputPaths(
        root=root,
        parsed=root / "01_parsed",
        normalized=root / "02_normalized",
        structured=root / "03_structured",
        chunks=root / "04_chunks",
        embeddings=root / "05_embeddings",
    )


def ensure_document_output_paths(
    document_id: str,
) -> DocumentOutputPaths:
    """
    문서별 Pipeline 출력 폴더를 생성합니다.
    """

    paths = (
        get_document_output_paths(
            document_id
        )
    )

    for path in (
        paths.root,
        paths.parsed,
        paths.normalized,
        paths.structured,
        paths.chunks,
        paths.embeddings,
    ):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

    return paths