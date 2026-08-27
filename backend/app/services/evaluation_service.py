from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.document import Document
from backend.app.services.collection_service import (
    persist_collection_result,
)
from backend.app.services.document_role_service import (
    DOCUMENT_ROLE_PRIMARY,
)
from config.paths import PROJECT_ROOT


EVALUATION_DB_NAME = "one_cycle_evaluation_tmp"
VALID_DOCUMENT_FORMATS = {"hwp", "hwpx"}


@dataclass(frozen=True)
class EvaluationDocumentInput:
    evaluation_document_id: str
    source_path: str
    document_format: str
    title: str | None = None


def _assert_evaluation_database() -> None:
    if settings.postgres_db != EVALUATION_DB_NAME:
        raise RuntimeError(
            "평가 작업은 평가 DB에서만 실행할 수 있습니다. "
            f"configured={settings.postgres_db}, "
            f"required={EVALUATION_DB_NAME}"
        )

    with SessionLocal() as db:
        current_database = db.execute(
            text("SELECT current_database()")
        ).scalar_one()

    if current_database != EVALUATION_DB_NAME:
        raise RuntimeError(
            "실제 연결 DB가 평가 DB가 아닙니다. "
            f"actual={current_database}, "
            f"required={EVALUATION_DB_NAME}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _normalize_source_path(
    raw_path: str,
) -> tuple[Path, str]:
    source_path = Path(raw_path).expanduser()

    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path

    source_path = source_path.resolve()

    if not source_path.is_file():
        raise ValueError(
            f"평가 원본 문서를 찾을 수 없습니다: {source_path}"
        )

    try:
        relative_path = source_path.relative_to(
            PROJECT_ROOT.resolve()
        )
        storage_path = relative_path.as_posix()
    except ValueError:
        storage_path = str(source_path)

    return source_path, storage_path


def _normalize_dataset_id(dataset_id: str) -> str:
    value = dataset_id.strip()

    if not value:
        raise ValueError("dataset_id가 비어 있습니다.")

    normalized = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "-",
        value,
    ).strip("-")

    if not normalized:
        normalized = "dataset"

    return normalized[:20]


def _make_execution_id(dataset_id: str) -> str:
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d%H%M%S%f")

    return (
        f"eval_"
        f"{_normalize_dataset_id(dataset_id)}"
        f"_{timestamp}"
    )


def register_evaluation_dataset(
    *,
    dataset_id: str,
    documents: list[EvaluationDocumentInput],
) -> dict:
    """
    평가 원본 문서를 크롤링 없이 평가 DB에 등록한다.

    기존 persist_collection_result()를 재사용하여
    CollectionRun → Announcement → Document를 생성한다.
    """

    _assert_evaluation_database()

    if not documents:
        raise ValueError(
            "등록할 평가 문서가 없습니다."
        )

    normalized_documents = []
    seen_ids: set[str] = set()

    for document in documents:
        evaluation_document_id = (
            document.evaluation_document_id.strip()
        )

        if not evaluation_document_id:
            raise ValueError(
                "evaluation_document_id가 비어 있습니다."
            )

        if len(evaluation_document_id) > 255:
            raise ValueError(
                "evaluation_document_id는 "
                "255자를 초과할 수 없습니다."
            )

        if evaluation_document_id in seen_ids:
            raise ValueError(
                "중복 evaluation_document_id입니다: "
                f"{evaluation_document_id}"
            )

        seen_ids.add(evaluation_document_id)

        document_format = (
            document.document_format
            .strip()
            .lower()
        )

        if document_format not in VALID_DOCUMENT_FORMATS:
            raise ValueError(
                "지원하지 않는 문서 형식입니다: "
                f"{document_format}"
            )

        source_path, storage_path = (
            _normalize_source_path(
                document.source_path
            )
        )

        normalized_documents.append(
            {
                "evaluation_document_id": (
                    evaluation_document_id
                ),
                "source_path": source_path,
                "storage_path": storage_path,
                "document_format": document_format,
                "title": (
                    document.title.strip()
                    if document.title
                    and document.title.strip()
                    else source_path.stem
                ),
            }
        )

    execution_id = _make_execution_id(
        dataset_id
    )

    payload = {
        "execution_id": execution_id,
        "execution_status": "success",
        "total_count": len(
            normalized_documents
        ),
        "success_count": len(
            normalized_documents
        ),
        "failed_count": 0,
        "fatal_error": None,
        "data": [],
    }

    for item in normalized_documents:
        source_path = item["source_path"]

        payload["data"].append(
            {
                "source_announcement_id": (
                    item[
                        "evaluation_document_id"
                    ]
                ),
                "title": item["title"],
                "detail_url": (
                    "evaluation://"
                    f"{dataset_id}/"
                    f"{item['evaluation_document_id']}"
                ),
                "notice_type": "evaluation",
                "region": None,
                "post_date": None,
                "publication_status": (
                    "evaluation"
                ),
                "documents": [
                    {
                        "file_format": (
                            item[
                                "document_format"
                            ]
                        ),
                        "download_status": (
                            "completed"
                        ),
                        "file_name": (
                            source_path.name
                        ),
                        "storage_path": (
                            item["storage_path"]
                        ),
                        "file_size_bytes": (
                            source_path.stat().st_size
                        ),
                        "checksum_sha256": (
                            _sha256_file(
                                source_path
                            )
                        ),
                        "error_message": None,
                    }
                ],
            }
        )

    persistence = (
        persist_collection_result(
            payload
        )
    )

    collection_run_id = int(
        persistence[
            "collection_run_id"
        ]
    )

    registered_documents = []

    # 평가 입력은 모두 분석 대상 원본 문서이므로
    # filename 기반 자동 분류 결과와 관계없이
    # primary로 확정한다.
    with SessionLocal.begin() as db:
        for item in normalized_documents:
            announcement = db.scalar(
                select(Announcement).where(
                    Announcement.collection_run_id
                    == collection_run_id,
                    Announcement.source_announcement_id
                    == item[
                        "evaluation_document_id"
                    ],
                )
            )

            if announcement is None:
                raise RuntimeError(
                    "등록된 평가 Announcement를 "
                    "찾을 수 없습니다: "
                    f"{item['evaluation_document_id']}"
                )

            rows = list(
                db.scalars(
                    select(Document).where(
                        Document.announcement_id
                        == announcement.id
                    )
                )
            )

            if len(rows) != 1:
                raise RuntimeError(
                    "평가 Announcement에는 "
                    "Document가 정확히 1개여야 합니다. "
                    f"announcement_id="
                    f"{announcement.id}, "
                    f"actual={len(rows)}"
                )

            document = rows[0]
            document.document_role = (
                DOCUMENT_ROLE_PRIMARY
            )

            registered_documents.append(
                {
                    "evaluation_document_id": (
                        item[
                            "evaluation_document_id"
                        ]
                    ),
                    "announcement_id": (
                        announcement.id
                    ),
                    "document_id": document.id,
                    "document_format": (
                        document.document_format
                    ),
                    "storage_path": (
                        document.storage_path
                    ),
                }
            )

    return {
        "dataset_id": dataset_id,
        "execution_id": execution_id,
        "collection_run_id": (
            collection_run_id
        ),
        "document_count": len(
            registered_documents
        ),
        "analysis_document_ids": [
            item["document_id"]
            for item
            in registered_documents
        ],
        "documents": (
            registered_documents
        ),
    }
