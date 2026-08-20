from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_chunks_status",
        ),
        CheckConstraint(
            "document_format IN ('hwp', 'hwpx')",
            name="ck_chunks_document_format",
        ),
        CheckConstraint(
            "(token_count IS NULL OR token_count >= 0) "
            "AND (character_count IS NULL OR character_count >= 0)",
            name="ck_chunks_counts_nonnegative",
        ),
        CheckConstraint(
            "source_page IS NULL OR source_page >= 1",
            name="ck_chunks_source_page_positive",
        ),
        UniqueConstraint(
            "chunk_set_id",
            "external_chunk_key",
            name="uq_chunks_set_external_key",
        ),
        UniqueConstraint(
            "chunk_set_id",
            "chunk_index",
            name="uq_chunks_set_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chunk_set_id: Mapped[int] = mapped_column(
        ForeignKey(
            "chunk_sets.id",
            name="fk_chunks_chunk_set_id_chunk_sets",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # 검색 범위 제한과 결과 반환을 단순하게 하기 위해 직접 보관한다.
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey(
            "announcements.id",
            name="fk_chunks_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    external_chunk_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    document_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    section_path: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    search_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    embedding_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    character_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_block_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    source_table_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    source_reference: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
        server_default="completed",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chunk_set: Mapped["ChunkSet"] = relationship(
        back_populates="chunks",
    )
    embeddings: Mapped[list["Embedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )