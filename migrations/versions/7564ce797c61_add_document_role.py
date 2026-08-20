"""add document role

Revision ID: 7564ce797c61
Revises: 9289f1ddee4d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7564ce797c61"
down_revision: Union[str, Sequence[str], None] = "9289f1ddee4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "document_role",
            sa.String(length=20),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE documents
        SET document_role =
            CASE
                WHEN original_filename ~*
                    '(\uac1c\uc778\uc815\ubcf4|\ub3d9\uc758\uc11c|\uc704\uc784\uc7a5|qna|q[&]?a|\uae08\uc735\uc815\ubcf4|\uc790\uc0b0\ubcf4\uc720|\uac01\uc11c|\uacf5\ub3d9\uc2e0\uccad|\uc138\ub300\uad6c\uc131|\uc911\ubcf5\uc120\uc815|\ud544\uc218\uc81c\ucd9c\uc11c\ub958|\ucd94\uac00\uc11c\ub958|\uc2e0\uccad\uc548\ub0b4|\ud655\uc57d\uc11c|\ud655\uc778\uc11c|\uc791\uc131\uc11c\ub958|required_documents|supplement)'
                    THEN 'supporting'

                WHEN original_filename ~*
                    '(\uacf5\uace0|\ubaa8\uc9d1|main_notice)'
                    THEN 'primary'

                ELSE 'unknown'
            END
        """
    )

    op.create_check_constraint(
        "ck_documents_role",
        "documents",
        "document_role IN ('primary', 'supporting', 'unknown')",
    )

    op.create_index(
        "ix_documents_document_role",
        "documents",
        ["document_role"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_document_role",
        table_name="documents",
    )

    op.drop_constraint(
        "ck_documents_role",
        "documents",
        type_="check",
    )

    op.drop_column(
        "documents",
        "document_role",
    )
