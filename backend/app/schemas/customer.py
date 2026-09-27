from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


CustomerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]


class CustomerCreate(BaseModel):
    customer_name: CustomerName
    phone: str | None = Field(default=None, max_length=20)
    address_note: str | None = Field(default=None, max_length=255)
    note: str | None = None


class CustomerUpdate(BaseModel):
    customer_name: CustomerName | None = None
    phone: str | None = Field(default=None, max_length=20)
    address_note: str | None = Field(default=None, max_length=255)
    note: str | None = None

    @model_validator(mode="after")
    def require_name_when_provided(self):
        if "customer_name" in self.model_fields_set and self.customer_name is None:
            raise ValueError("customer_name cannot be null")
        return self


class CustomerRead(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    created_at: datetime
