from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Garden(Base):
    __tablename__ = "gardens"

    garden_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    garden_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    owner_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    location_note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
