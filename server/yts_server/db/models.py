"""业务模型骨架(stub)。真实表 TODO;两端(SQLite/PG)共用。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base


class CreationJob(Base):
    __tablename__ = "creation_job"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_uuid: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # TODO: payload / outbox / heartbeat 等(参考 yuetools creation job)
