from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SaleCreate(BaseModel):
    harvest_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    sale_date: date
    quantity_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    note: str | None = None


class SaleUpdate(BaseModel):
    harvest_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    sale_date: date | None = None
    quantity_kg: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=15, decimal_places=2
    )
    note: str | None = None

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in (
            "harvest_id", "customer_id", "sale_date", "quantity_kg", "unit_price"
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SaleRead(SaleCreate):
    model_config = ConfigDict(from_attributes=True)

    sale_id: int
    total_amount: Decimal
    created_at: datetime
