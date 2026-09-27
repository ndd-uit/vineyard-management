from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.season import AcquisitionType, SeasonStatus


class SeasonCreate(BaseModel):
    garden_id: int = Field(gt=0)
    variety_id: int = Field(gt=0)
    season_name: str | None = Field(default=None, max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    acquisition_type: AcquisitionType
    purchase_price: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    status: SeasonStatus
    note: str | None = None


class SeasonUpdate(BaseModel):
    garden_id: int | None = Field(default=None, gt=0)
    variety_id: int | None = Field(default=None, gt=0)
    season_name: str | None = Field(default=None, max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    acquisition_type: AcquisitionType | None = None
    purchase_price: Decimal | None = Field(
        default=None, max_digits=15, decimal_places=2
    )
    status: SeasonStatus | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in ("garden_id", "variety_id", "acquisition_type", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SeasonRead(SeasonCreate):
    model_config = ConfigDict(from_attributes=True)

    season_id: int
    created_at: datetime
