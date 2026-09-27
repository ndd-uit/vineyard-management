from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GrapeVariety(Base):
    __tablename__ = "grape_varieties"

    variety_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    variety_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )