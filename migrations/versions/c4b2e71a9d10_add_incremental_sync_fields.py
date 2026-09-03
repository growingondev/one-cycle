"""add incremental announcement sync fields

Revision ID: c4b2e71a9d10
Revises: 112877185a58
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4b2e71a9d10"
down_revision: str | Sequence[str] | None = "112877185a58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column("normalized_title", sa.Text(), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("metadata_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column(
            "change_type",
            sa.String(length=20),
            server_default="initial",
            nullable=False,
        ),
    )
    op.add_column(
        "announcements",
        sa.Column(
            "is_visible",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "announcements",
        sa.Column(
            "supersedes_announcement_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "announcements",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        (
            "fk_announcements_supersedes_announcement_id_"
            "announcements"
        ),
        "announcements",
        "announcements",
        ["supersedes_announcement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_announcements_metadata_hash"),
        "announcements",
        ["metadata_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_is_visible"),
        "announcements",
        ["is_visible"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_supersedes_announcement_id"),
        "announcements",
        ["supersedes_announcement_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_announcements_supersedes_announcement_id"),
        table_name="announcements",
    )
    op.drop_index(
        op.f("ix_announcements_is_visible"),
        table_name="announcements",
    )
    op.drop_index(
        op.f("ix_announcements_metadata_hash"),
        table_name="announcements",
    )
    op.drop_constraint(
        (
            "fk_announcements_supersedes_announcement_id_"
            "announcements"
        ),
        "announcements",
        type_="foreignkey",
    )
    op.drop_column("announcements", "last_seen_at")
    op.drop_column("announcements", "supersedes_announcement_id")
    op.drop_column("announcements", "is_visible")
    op.drop_column("announcements", "change_type")
    op.drop_column("announcements", "metadata_hash")
    op.drop_column("announcements", "normalized_title")
