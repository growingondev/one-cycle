from __future__ import annotations

import math

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.glossary import Glossary
from backend.app.schemas.glossary import (
    GlossaryAdminListResponse,
    GlossaryCreateRequest,
    GlossaryStatusUpdateRequest,
    GlossaryUpdateRequest,
)


class DuplicateGlossaryTermError(Exception):
    """같은 용어가 이미 존재할 때 발생한다."""


def _total_pages(total: int, size: int) -> int:
    return math.ceil(total / size) if total else 0


def list_public_glossary(
    db: Session,
) -> list[Glossary]:
    return list(
        db.scalars(
            select(Glossary)
            .where(Glossary.is_active.is_(True))
            .order_by(Glossary.id.asc())
        ).all()
    )


def list_admin_glossary(
    db: Session,
    page: int,
    size: int,
    search: str | None,
    category: str | None,
    is_active: bool | None,
) -> GlossaryAdminListResponse:
    conditions = []

    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Glossary.term.ilike(pattern),
                Glossary.definition.ilike(pattern),
            )
        )

    if category:
        conditions.append(Glossary.category == category)

    if is_active is not None:
        conditions.append(Glossary.is_active.is_(is_active))

    total_stmt = select(func.count()).select_from(Glossary)

    if conditions:
        total_stmt = total_stmt.where(*conditions)

    total = db.scalar(total_stmt) or 0

    items_stmt = (
        select(Glossary)
        .order_by(Glossary.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )

    if conditions:
        items_stmt = items_stmt.where(*conditions)

    items = list(db.scalars(items_stmt).all())

    return GlossaryAdminListResponse(
        items=items,
        page=page,
        size=size,
        total=total,
        total_pages=_total_pages(total, size),
    )


def create_glossary(
    db: Session,
    request: GlossaryCreateRequest,
) -> Glossary:
    glossary = Glossary(
        term=request.term,
        definition=request.definition,
        category=request.category,
        is_active=request.is_active,
    )

    db.add(glossary)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateGlossaryTermError(request.term) from exc

    db.refresh(glossary)
    return glossary


def update_glossary(
    db: Session,
    glossary_id: int,
    request: GlossaryUpdateRequest,
) -> Glossary | None:
    glossary = db.get(Glossary, glossary_id)

    if glossary is None:
        return None

    glossary.term = request.term
    glossary.definition = request.definition
    glossary.category = request.category
    glossary.is_active = request.is_active

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateGlossaryTermError(request.term) from exc

    db.refresh(glossary)
    return glossary


def update_glossary_status(
    db: Session,
    glossary_id: int,
    request: GlossaryStatusUpdateRequest,
) -> Glossary | None:
    glossary = db.get(Glossary, glossary_id)

    if glossary is None:
        return None

    glossary.is_active = request.is_active
    db.commit()
    db.refresh(glossary)

    return glossary


def delete_glossary(
    db: Session,
    glossary_id: int,
) -> bool:
    glossary = db.get(Glossary, glossary_id)

    if glossary is None:
        return False

    db.delete(glossary)
    db.commit()

    return True
