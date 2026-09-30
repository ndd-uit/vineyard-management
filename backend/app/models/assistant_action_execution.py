"""Durable, user-scoped record of a completed assistant write."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, DateTime, JSON, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssistantActionExecution(Base):
    __tablename__ = "assistant_action_executions"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    action_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
