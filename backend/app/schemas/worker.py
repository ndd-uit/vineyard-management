from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


WorkerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]


class WorkerCreate(BaseModel):
    worker_name: WorkerName
    phone: str | None = Field(default=None, max_length=20)
    note: str | None = None


class WorkerUpdate(BaseModel):
    worker_name: WorkerName | None = None
    phone: str | None = Field(default=None, max_length=20)
    note: str | None = None

    @model_validator(mode="after")
    def require_name_when_provided(self):
        if "worker_name" in self.model_fields_set and self.worker_name is None:
            raise ValueError("worker_name cannot be null")
        return self


class WorkerRead(WorkerCreate):
    model_config = ConfigDict(from_attributes=True)

    worker_id: int
    created_at: datetime
