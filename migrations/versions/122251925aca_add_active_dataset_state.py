"""add active dataset state

Revision ID: 122251925aca
Revises: 9672336f0911
Create Date: 2026-08-06 17:10:54.448814

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '122251925aca'
down_revision: Union[str, Sequence[str], None] = '9672336f0911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "system_state",
        sa.Column(
            "id",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "active_collection_run_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_system_state_singleton",
        ),
        sa.ForeignKeyConstraint(
            ["active_collection_run_id"],
            ["collection_runs.id"],
            name=(
                "fk_system_state_active_collection_run_id_"
                "collection_runs"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "active_collection_run_id",
            name="uq_system_state_active_collection_run_id",
        ),
    )

    # 싱글턴 상태 행을 미리 생성한다.
    op.execute(
        """
        INSERT INTO system_state (
            id,
            active_collection_run_id
        )
        VALUES (
            1,
            NULL
        )
        """
    )

    op.add_column(
        "processing_runs",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "processing_runs",
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_processing_runs_active_requires_verified_success",
        "processing_runs",
        (
            "(NOT is_active) OR "
            "("
            "execution_status = 'succeeded' "
            "AND verification_status = 'pass' "
            "AND activated_at IS NOT NULL"
            ")"
        ),
    )

    op.create_index(
        "uq_processing_runs_one_active_per_document",
        "processing_runs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "uq_processing_runs_one_active_per_document",
        table_name="processing_runs",
        postgresql_where=sa.text("is_active"),
    )

    op.drop_constraint(
        "ck_processing_runs_active_requires_verified_success",
        "processing_runs",
        type_="check",
    )

    op.drop_column(
        "processing_runs",
        "activated_at",
    )
    op.drop_column(
        "processing_runs",
        "is_active",
    )

    op.drop_table("system_state")
    # ### end Alembic commands ###
