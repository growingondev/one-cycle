from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ChunkSet(Base):
    __tablename__ = "chunk_sets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_chunk_sets_status",
        ),
        CheckConstraint(
            "chunk_count >= 0",
            name="ck_chunk_sets_chunk_count_nonnegative",
        ),
        CheckConstraint(
            "(NOT is_active) OR status = 'completed'",
            name="ck_chunk_sets_active_requires_completed",
        ),
        Index(
            "uq_chunk_sets_one_active_per_processing_run",
            "processing_run_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processing_run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "processing_runs.id",
            name="fk_chunk_sets_processing_run_id_processing_runs",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chunker_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    chunking_config: Mapped[dict] = mapped_column(
        "config",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    input_content_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    processing_run: Mapped["ProcessingRun"] = relationship(
        back_populates="chunk_sets",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="chunk_set",
        cascade="all, delete-orphan",
    )