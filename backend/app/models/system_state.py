from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class SystemState(Base):
    __tablename__ = "system_state"
    __table_args__ = (
        CheckConstraint(
            "id = 1",
            name="ck_system_state_singleton",
        ),
    )

    # 시스템 전체에서 한 행만 사용한다.
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        server_default="1",
    )

    active_collection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "collection_runs.id",
            name="fk_system_state_active_collection_run_id_collection_runs",
            ondelete="RESTRICT",
        ),
        nullable=True,
        unique=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    active_collection_run: Mapped["CollectionRun | None"] = relationship()