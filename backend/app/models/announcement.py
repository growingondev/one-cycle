from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.models.collection_run import CollectionRun
    from backend.app.models.document import Document


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "source_announcement_id",
            name="uq_announcements_run_source_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    collection_run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "collection_runs.id",
            name="fk_announcements_collection_run_id_collection_runs",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # LH panId, wrtancNo 또는 URL 기반 대체 식별값
    source_announcement_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Display number from the LH announcement list
    notice_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail_url: Mapped[str] = mapped_column(Text, nullable=False)

    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    notice_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    announcement_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    deadline_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    publication_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    normalized_title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="initial",
        server_default="initial",
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    supersedes_announcement_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "announcements.id",
            name=(
                "fk_announcements_supersedes_announcement_id_"
                "announcements"
            ),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    collection_run: Mapped["CollectionRun"] = relationship(
        back_populates="announcements",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="announcement",
        cascade="all, delete-orphan",
    )
