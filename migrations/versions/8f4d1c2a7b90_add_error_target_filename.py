"""add error target filename

Revision ID: 8f4d1c2a7b90
Revises: c4b2e71a9d10
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "8f4d1c2a7b90"
down_revision: str | Sequence[str] | None = "c4b2e71a9d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "error_logs",
        sa.Column(
            "target_filename",
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("error_logs", "target_filename")
