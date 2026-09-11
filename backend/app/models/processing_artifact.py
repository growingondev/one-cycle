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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ProcessingArtifact(Base):
    __tablename__ = "processing_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN "
            "('parsed', 'normalized', 'structured', 'verification', 'log')",
            name="ck_processing_artifacts_type",
        ),
        CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_processing_artifacts_file_size_nonnegative",
        ),
        UniqueConstraint(
            "processing_run_id",
            "artifact_type",
            name="uq_processing_artifacts_run_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processing_run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "processing_runs.id",
            name="fk_processing_artifacts_run_id_processing_runs",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    schema_version: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # metadata는 SQLAlchemy가 사용하는 이름이므로
    # Python 속성명은 artifact_metadata로 구분한다.
    artifact_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    processing_run: Mapped["ProcessingRun"] = relationship(
        back_populates="artifacts",
    )