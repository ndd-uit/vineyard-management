from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LaborRecord(Base):
    __tablename__ = "labor_records"

    labor_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("workers.worker_id"), nullable=False
    )
    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.season_id"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    work_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
