from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkerPaymentCreate(BaseModel):
    worker_id: int = Field(gt=0)
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    note: str | None = None


class WorkerPaymentUpdate(BaseModel):
    worker_id: int | None = Field(default=None, gt=0)
    payment_date: date | None = None
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )
    note: str | None = None

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in ("worker_id", "payment_date", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class WorkerPaymentRead(WorkerPaymentCreate):
    model_config = ConfigDict(from_attributes=True)

    worker_payment_id: int
    created_at: datetime
