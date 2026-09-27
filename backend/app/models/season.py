from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AcquisitionType(str, Enum):
    OWNED = "OWNED"
    PURCHASED = "PURCHASED"


class SeasonStatus(str, Enum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    HARVESTING = "HARVESTING"
    COMPLETED = "COMPLETED"


class Season(Base):
    __tablename__ = "seasons"

    season_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    garden_id: Mapped[int] = mapped_column(
        ForeignKey("gardens.garden_id"),
        nullable=False
    )

    variety_id: Mapped[int] = mapped_column(
        ForeignKey("grape_varieties.variety_id"),
        nullable=False
    )

    season_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    acquisition_type: Mapped[AcquisitionType] = mapped_column(
        SqlEnum(AcquisitionType, name="season_acquisition_type"),
        nullable=False
    )

    purchase_price: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2),
        nullable=True
    )

    status: Mapped[SeasonStatus] = mapped_column(
        SqlEnum(SeasonStatus, name="season_status"),
        nullable=False
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
