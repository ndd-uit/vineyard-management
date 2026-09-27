from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.garden import Garden
from app.models.grape_variety import GrapeVariety
from app.models.season import AcquisitionType


def validate_season(
    db: Session,
    *,
    garden_id: int,
    variety_id: int,
    start_date: date | None,
    end_date: date | None,
    acquisition_type: AcquisitionType,
    purchase_price: Decimal | None,
) -> None:
    if db.get(Garden, garden_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "garden_id does not exist")
    if db.get(GrapeVariety, variety_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "variety_id does not exist")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date is before start_date")
    if acquisition_type == AcquisitionType.OWNED and purchase_price is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "purchase_price must be null for an owned season",
        )
