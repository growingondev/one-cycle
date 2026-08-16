from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "document_format IN ('hwp', 'hwpx')",
            name="ck_documents_format",
        ),
        CheckConstraint(
            "download_status IN ('completed', 'failed', 'skipped')",
            name="ck_documents_download_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    announcement_id: Mapped[int] = mapped_column(
        ForeignKey(
            "announcements.id",
            name="fk_documents_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    document_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )

    # 다운로드 실패 시 경로와 체크섬은 존재하지 않을 수 있음
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    download_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    announcement: Mapped["Announcement"] = relationship(
        back_populates="documents",
    )
    processing_runs: Mapped[list["ProcessingRun"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )