from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.announcement import Announcement
from backend.app.models.collection_run import CollectionRun
from backend.app.models.document import Document
from backend.app.models.processing_run import ProcessingRun
from backend.app.models.system_state import SystemState


@dataclass
class _RetentionPlan:
    active_collection_run_id: int | None
    previous_collection_run_id: int | None
    candidate_run_ids: list[int] = field(default_factory=list)
    skipped_running_run_ids: list[int] = field(default_factory=list)
    document_files: list[Path] = field(default_factory=list)
    output_directories: list[Path] = field(default_factory=list)
    unsafe_paths: list[str] = field(default_factory=list)
    reason: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "active_collection_run_id": self.active_collection_run_id,
            "previous_collection_run_id": self.previous_collection_run_id,
            "candidate_run_ids": self.candidate_run_ids,
            "candidate_run_count": len(self.candidate_run_ids),
            "skipped_running_run_ids": self.skipped_running_run_ids,
            "document_file_count": len(self.document_files),
            "output_directory_count": len(self.output_directories),
            "unsafe_paths": self.unsafe_paths,
            "reason": self.reason,
        }


def _resolved_path(value: str, root: Path) -> Path | None:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        return None

    resolved = raw.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root):
        return None

    return resolved


def _safe_file_targets(
    values: Iterable[str],
    *,
    retained_values: Iterable[str],
    root: Path,
    unsafe_paths: list[str],
) -> list[Path]:
    retained = {
        path
        for value in retained_values
        if (path := _resolved_path(value, root)) is not None
    }
    targets: set[Path] = set()

    for value in values:
        path = _resolved_path(value, root)
        if path is None:
            unsafe_paths.append(value)
            continue
        if path in retained:
            continue
        targets.add(path)

    return sorted(targets, key=str)


def _safe_directory_targets(
    values: Iterable[str],
    *,
    retained_values: Iterable[str],
    root: Path,
    unsafe_paths: list[str],
) -> list[Path]:
    retained = {
        path
        for value in retained_values
        if (path := _resolved_path(value, root)) is not None
    }
    candidates: set[Path] = set()

    for value in values:
        path = _resolved_path(value, root)
        if path is None:
            unsafe_paths.append(value)
            continue
        if any(
            retained_path == path
            or retained_path.is_relative_to(path)
            for retained_path in retained
        ):
            continue
        candidates.add(path)

    targets: list[Path] = []
    for path in sorted(candidates, key=lambda item: (len(item.parts), str(item))):
        if any(path.is_relative_to(parent) for parent in targets):
            continue
        targets.append(path)

    return targets


def _nonempty_strings(values: Iterable[str | None]) -> list[str]:
    return [
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ]


def _build_plan(db: Session, *, lock_state: bool) -> _RetentionPlan:
    state_query = select(SystemState).where(SystemState.id == 1)
    if lock_state:
        state_query = state_query.with_for_update()

    system_state = db.scalar(state_query)
    if system_state is None:
        raise RuntimeError("system_state singleton 행이 없습니다.")

    active_id = system_state.active_collection_run_id
    previous_id = system_state.previous_collection_run_id
    plan = _RetentionPlan(
        active_collection_run_id=active_id,
        previous_collection_run_id=previous_id,
    )

    if active_id is None:
        plan.reason = "active_collection_run_not_initialized"
        return plan

    if previous_id is None:
        plan.reason = "previous_collection_run_not_initialized"
        return plan

    protected_ids = {active_id, previous_id}
    all_runs = list(
        db.execute(
            select(CollectionRun.id, CollectionRun.status).order_by(
                CollectionRun.id
            )
        )
    )
    plan.skipped_running_run_ids = [
        run_id
        for run_id, status in all_runs
        if run_id not in protected_ids and status == "running"
    ]
    plan.candidate_run_ids = [
        run_id
        for run_id, status in all_runs
        if run_id not in protected_ids and status != "running"
    ]

    if not plan.candidate_run_ids:
        plan.reason = "no_old_collection_runs"
        return plan

    candidate_ids = plan.candidate_run_ids
    candidate_document_paths = _nonempty_strings(
        db.scalars(
            select(Document.storage_path)
            .join(
                Announcement,
                Announcement.id == Document.announcement_id,
            )
            .where(Announcement.collection_run_id.in_(candidate_ids))
        )
    )
    retained_document_paths = _nonempty_strings(
        db.scalars(
            select(Document.storage_path)
            .join(
                Announcement,
                Announcement.id == Document.announcement_id,
            )
            .where(~Announcement.collection_run_id.in_(candidate_ids))
        )
    )
    candidate_output_paths = _nonempty_strings(
        db.scalars(
            select(ProcessingRun.output_root_path)
            .join(Document, Document.id == ProcessingRun.document_id)
            .join(
                Announcement,
                Announcement.id == Document.announcement_id,
            )
            .where(Announcement.collection_run_id.in_(candidate_ids))
        )
    )
    retained_output_paths = _nonempty_strings(
        db.scalars(
            select(ProcessingRun.output_root_path)
            .join(Document, Document.id == ProcessingRun.document_id)
            .join(
                Announcement,
                Announcement.id == Document.announcement_id,
            )
            .where(~Announcement.collection_run_id.in_(candidate_ids))
        )
    )

    document_root = Path(settings.crawler_staging_dir).expanduser().resolve()
    output_root = Path(
        settings.collection_retention_output_root
    ).expanduser().resolve()

    plan.document_files = _safe_file_targets(
        candidate_document_paths,
        retained_values=retained_document_paths,
        root=document_root,
        unsafe_paths=plan.unsafe_paths,
    )
    plan.output_directories = _safe_directory_targets(
        candidate_output_paths,
        retained_values=retained_output_paths,
        root=output_root,
        unsafe_paths=plan.unsafe_paths,
    )
    return plan


def plan_collection_run_retention() -> dict[str, Any]:
    """DB와 파일을 변경하지 않고 정리 대상을 계산한다."""

    with SessionLocal() as db:
        plan = _build_plan(db, lock_state=False)
    return {
        "status": "skipped" if plan.reason else "dry_run",
        **plan.summary(),
    }


def _prune_empty_parents(path: Path, root: Path) -> None:
    parent = path.parent
    while parent != root and parent.is_relative_to(root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _delete_files(plan: _RetentionPlan) -> dict[str, Any]:
    document_root = Path(settings.crawler_staging_dir).expanduser().resolve()
    output_root = Path(
        settings.collection_retention_output_root
    ).expanduser().resolve()
    deleted_document_files = 0
    deleted_output_directories = 0
    missing_paths = 0
    errors: list[str] = []

    for path in plan.output_directories:
        try:
            if not path.exists():
                missing_paths += 1
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted_output_directories += 1
            _prune_empty_parents(path, output_root)
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    for path in plan.document_files:
        try:
            if not path.exists():
                missing_paths += 1
                continue
            if path.is_dir():
                errors.append(f"{path}: expected a file, found a directory")
                continue
            path.unlink()
            deleted_document_files += 1
            _prune_empty_parents(path, document_root)
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    return {
        "deleted_document_file_count": deleted_document_files,
        "deleted_output_directory_count": deleted_output_directories,
        "missing_path_count": missing_paths,
        "file_errors": errors,
    }


def apply_collection_run_retention(
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """
    활성 Run과 직전 Run을 보호하고 그보다 오래된 Run을 정리한다.

    비활성 파일을 먼저 정리하고 모두 성공한 경우에만 DB Run을 삭제한다.
    중간 실패 시 DB 참조를 남겨 다음 실행에서 같은 대상을 다시 찾을 수 있다.
    """

    with SessionLocal.begin() as db:
        plan = _build_plan(db, lock_state=True)

        if plan.reason is not None:
            return {
                "status": "skipped",
                **plan.summary(),
            }

        if dry_run:
            return {
                "status": "dry_run",
                **plan.summary(),
            }

        file_result = _delete_files(plan)
        if file_result["file_errors"] or plan.unsafe_paths:
            return {
                "status": "file_cleanup_incomplete",
                **plan.summary(),
                "deleted_run_count": 0,
                **file_result,
            }

        deletion = db.execute(
            delete(CollectionRun).where(
                CollectionRun.id.in_(plan.candidate_run_ids)
            )
        )
        deleted_run_count = int(deletion.rowcount or 0)

    return {
        "status": "completed",
        **plan.summary(),
        "deleted_run_count": deleted_run_count,
        **file_result,
    }
