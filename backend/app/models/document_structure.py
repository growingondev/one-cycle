from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class DocumentStructure(Base):
    __tablename__ = "document_structures"
    __table_args__ = (
        CheckConstraint(
            "element_count >= 0",
            name="ck_document_structures_element_count_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    processing_run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "processing_runs.id",
            name=(
                "fk_document_structures_processing_run_id_"
                "processing_runs"
            ),
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    structure_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    element_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    processing_run: Mapped["ProcessingRun"] = relationship()