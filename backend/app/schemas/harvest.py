from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HarvestCreate(BaseModel):
    season_id: int = Field(gt=0)
    harvest_date: date
    quantity_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    note: str | None = None


class HarvestUpdate(BaseModel):
    season_id: int | None = Field(default=None, gt=0)
    harvest_date: date | None = None
    quantity_kg: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    note: str | None = None

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in ("season_id", "harvest_date", "quantity_kg"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class HarvestRead(HarvestCreate):
    model_config = ConfigDict(from_attributes=True)

    harvest_id: int
    created_at: datetime
