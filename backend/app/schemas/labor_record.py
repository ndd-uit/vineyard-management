from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


WorkType = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class LaborRecordCreate(BaseModel):
    worker_id: int = Field(gt=0)
    season_id: int = Field(gt=0)
    work_date: date
    work_type: WorkType
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    note: str | None = None


class LaborRecordUpdate(BaseModel):
    worker_id: int | None = Field(default=None, gt=0)
    season_id: int | None = Field(default=None, gt=0)
    work_date: date | None = None
    work_type: WorkType | None = None
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )
    note: str | None = None

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in ("worker_id", "season_id", "work_date", "work_type", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class LaborRecordRead(LaborRecordCreate):
    model_config = ConfigDict(from_attributes=True)

    labor_id: int
    created_at: datetime
