from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_embeddings_status",
        ),
        CheckConstraint(
            "dimension = 1024",
            name="ck_embeddings_dimension",
        ),
        CheckConstraint(
            "status <> 'completed' OR embedding IS NOT NULL",
            name="ck_embeddings_completed_requires_vector",
        ),
        UniqueConstraint(
            "chunk_id",
            "model_name",
            "model_version",
            name="uq_embeddings_chunk_model_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey(
            "chunks.id",
            name="fk_embeddings_chunk_id_chunks",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        server_default="default",
    )

    dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1024,
        server_default="1024",
    )
    normalized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    embedding_text_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # 실패 또는 대기 상태에서는 벡터가 없을 수 있다.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chunk: Mapped["Chunk"] = relationship(
        back_populates="embeddings",
    )