from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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


class KeyInformation(Base):
    __tablename__ = "key_information"
    __table_args__ = (
        CheckConstraint(
            "extraction_status IN "
            "('pending', 'completed', 'failed')",
            name="ck_key_information_extraction_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey(
            "announcements.id",
            name="fk_key_information_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    source_processing_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "processing_runs.id",
            name=(
                "fk_key_information_source_processing_run_id_"
                "processing_runs"
            ),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    application_period: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    eligibility: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    supply_information: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    income_asset_criteria: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    required_documents: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    winner_announcement: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    contact_information: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    extraction_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    announcement: Mapped["Announcement"] = relationship()
    source_processing_run: Mapped["ProcessingRun | None"] = relationship()