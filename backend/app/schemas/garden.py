from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GardenCreate(BaseModel):
    garden_name: str = Field(min_length=1, max_length=150)
    owner_name: str | None = Field(default=None, max_length=150)
    location_note: str | None = Field(default=None, max_length=255)
    note: str | None = None


class GardenUpdate(BaseModel):
    garden_name: str | None = Field(default=None, min_length=1, max_length=150)
    owner_name: str | None = Field(default=None, max_length=150)
    location_note: str | None = Field(default=None, max_length=255)
    note: str | None = None

    @model_validator(mode="after")
    def require_name_when_provided(self):
        if "garden_name" in self.model_fields_set and self.garden_name is None:
            raise ValueError("garden_name cannot be null")
        return self


class GardenRead(GardenCreate):
    model_config = ConfigDict(from_attributes=True)

    garden_id: int
    created_at: datetime
