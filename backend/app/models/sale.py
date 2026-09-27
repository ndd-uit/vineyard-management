from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    sale_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    harvest_id: Mapped[int] = mapped_column(
        ForeignKey("harvests.harvest_id"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
