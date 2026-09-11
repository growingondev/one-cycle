"""add glossary

Revision ID: 3d70b82ff082
Revises: 7564ce797c61
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d70b82ff082"
down_revision: Union[str, Sequence[str], None] = "7564ce797c61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "glossary",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "term",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "definition",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
    )


def downgrade() -> None:
    op.drop_table("glossary")
