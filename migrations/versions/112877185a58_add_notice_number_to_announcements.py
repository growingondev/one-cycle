"""add notice number to announcements

Revision ID: 112877185a58
Revises: 5f4c391df25e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "112877185a58"
down_revision: Union[str, Sequence[str], None] = "5f4c391df25e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column(
            "notice_number",
            sa.String(length=20),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "announcements",
        "notice_number",
    )
