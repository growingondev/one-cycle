"""add previous collection run

Revision ID: d91f7a63b2c4
Revises: 8f4d1c2a7b90
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d91f7a63b2c4"
down_revision: str | Sequence[str] | None = "8f4d1c2a7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "system_state",
        sa.Column(
            "previous_collection_run_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_system_state_previous_collection_run_id_collection_runs",
        "system_state",
        "collection_runs",
        ["previous_collection_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_system_state_previous_collection_run_id",
        "system_state",
        ["previous_collection_run_id"],
    )
    op.create_check_constraint(
        "ck_system_state_active_previous_different",
        "system_state",
        (
            "previous_collection_run_id IS NULL "
            "OR active_collection_run_id IS NULL "
            "OR previous_collection_run_id <> active_collection_run_id"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_system_state_active_previous_different",
        "system_state",
        type_="check",
    )
    op.drop_constraint(
        "uq_system_state_previous_collection_run_id",
        "system_state",
        type_="unique",
    )
    op.drop_constraint(
        "fk_system_state_previous_collection_run_id_collection_runs",
        "system_state",
        type_="foreignkey",
    )
    op.drop_column(
        "system_state",
        "previous_collection_run_id",
    )
