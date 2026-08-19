"""add notice type to announcements

Revision ID: 9289f1ddee4d
Revises: b328bf2c4b4e
Create Date: 2026-08-19 14:18:59.939551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9289f1ddee4d'
down_revision: Union[str, Sequence[str], None] = 'b328bf2c4b4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column(
            "notice_type",
            sa.String(length=100),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "announcements",
        "notice_type",
    )
