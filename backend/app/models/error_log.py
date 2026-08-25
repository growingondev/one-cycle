from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (
        CheckConstraint(
            "error_type IN ("
            "'collection', "
            "'download', "
            "'parsing', "
            "'normalizing', "
            "'structuring', "
            "'verification', "
            "'chunking', "
            "'embedding', "
            "'database', "
            "'rag', "
            "'llm'"
            ")",
            name="ck_error_logs_error_type",
        ),
        CheckConstraint(
            "status IN ('unresolved', 'in_progress', 'resolved')",
            name="ck_error_logs_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    collection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "collection_runs.id",
            name="fk_error_logs_collection_run_id_collection_runs",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    announcement_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "announcements.id",
            name="fk_error_logs_announcement_id_announcements",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    document_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_error_logs_document_id_documents",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    processing_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "processing_runs.id",
            name="fk_error_logs_processing_run_id_processing_runs",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    error_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    stack_trace: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unresolved",
        server_default="unresolved",
        index=True,
    )

    resolution: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )