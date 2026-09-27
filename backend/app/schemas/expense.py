from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ExpenseCategory = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class ExpenseCreate(BaseModel):
    season_id: int = Field(gt=0)
    expense_date: date
    category: ExpenseCategory
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    description: str | None = Field(default=None, max_length=255)


class ExpenseUpdate(BaseModel):
    season_id: int | None = Field(default=None, gt=0)
    expense_date: date | None = None
    category: ExpenseCategory | None = None
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )
    description: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_non_nullable_fields(self):
        for field in ("season_id", "expense_date", "category", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ExpenseRead(ExpenseCreate):
    model_config = ConfigDict(from_attributes=True)

    expense_id: int
    created_at: datetime
