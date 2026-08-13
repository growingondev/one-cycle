"""add collection runs and documents

Revision ID: 7450a47c33a3
Revises: c8d429bc3cf3
Create Date: 2026-08-06 15:25:35.849896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7450a47c33a3'
down_revision: Union[str, Sequence[str], None] = 'c8d429bc3cf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="running",
            nullable=False,
        ),
        sa.Column(
            "total_announcement_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "successful_announcement_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "failed_announcement_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("fatal_error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_collection_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_collection_runs_execution_id"),
        "collection_runs",
        ["execution_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_collection_runs_status"),
        "collection_runs",
        ["status"],
        unique=False,
    )

    # 기존 announcements 컬럼을 보존하면서 새 모델에 맞게 변경한다.
    op.add_column(
        "announcements",
        sa.Column("collection_run_id", sa.Integer(), nullable=False),
    )
    op.add_column(
        "announcements",
        sa.Column(
            "source_announcement_id",
            sa.String(length=255),
            nullable=False,
        ),
    )
    op.add_column(
        "announcements",
        sa.Column("region", sa.String(length=100), nullable=True),
    )

    op.alter_column(
        "announcements",
        "source_url",
        new_column_name="detail_url",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "announcements",
        "status",
        new_column_name="publication_status",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "announcements",
        "title",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )

    op.create_index(
        op.f("ix_announcements_announcement_date"),
        "announcements",
        ["announcement_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_collection_run_id"),
        "announcements",
        ["collection_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_publication_status"),
        "announcements",
        ["publication_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_region"),
        "announcements",
        ["region"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_announcements_run_source_id",
        "announcements",
        ["collection_run_id", "source_announcement_id"],
    )
    op.create_foreign_key(
        "fk_announcements_collection_run_id_collection_runs",
        "announcements",
        "collection_runs",
        ["collection_run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_column("announcements", "updated_at")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column(
            "document_format",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "download_status",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "document_format IN ('hwp', 'hwpx')",
            name="ck_documents_format",
        ),
        sa.CheckConstraint(
            "download_status IN ('completed', 'failed', 'skipped')",
            name="ck_documents_download_status",
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name="fk_documents_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_documents_announcement_id"),
        "documents",
        ["announcement_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_checksum_sha256"),
        "documents",
        ["checksum_sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_document_format"),
        "documents",
        ["document_format"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_download_status"),
        "documents",
        ["download_status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_documents_download_status"),
        table_name="documents",
    )
    op.drop_index(
        op.f("ix_documents_document_format"),
        table_name="documents",
    )
    op.drop_index(
        op.f("ix_documents_checksum_sha256"),
        table_name="documents",
    )
    op.drop_index(
        op.f("ix_documents_announcement_id"),
        table_name="documents",
    )
    op.drop_table("documents")

    op.add_column(
        "announcements",
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.drop_constraint(
        "fk_announcements_collection_run_id_collection_runs",
        "announcements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_announcements_run_source_id",
        "announcements",
        type_="unique",
    )

    op.drop_index(
        op.f("ix_announcements_region"),
        table_name="announcements",
    )
    op.drop_index(
        op.f("ix_announcements_publication_status"),
        table_name="announcements",
    )
    op.drop_index(
        op.f("ix_announcements_collection_run_id"),
        table_name="announcements",
    )
    op.drop_index(
        op.f("ix_announcements_announcement_date"),
        table_name="announcements",
    )

    op.alter_column(
        "announcements",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )

    # publication_status가 NULL인 데이터가 있다면 기존 NOT NULL 구조에 맞게 보정한다.
    op.execute(
        "UPDATE announcements "
        "SET publication_status = 'unknown' "
        "WHERE publication_status IS NULL"
    )

    op.alter_column(
        "announcements",
        "publication_status",
        new_column_name="status",
        existing_type=sa.String(length=50),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "announcements",
        "detail_url",
        new_column_name="source_url",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    op.drop_column("announcements", "region")
    op.drop_column("announcements", "source_announcement_id")
    op.drop_column("announcements", "collection_run_id")

    op.drop_index(
        op.f("ix_collection_runs_status"),
        table_name="collection_runs",
    )
    op.drop_index(
        op.f("ix_collection_runs_execution_id"),
        table_name="collection_runs",
    )
    op.drop_table("collection_runs")
    # ### end Alembic commands ###
