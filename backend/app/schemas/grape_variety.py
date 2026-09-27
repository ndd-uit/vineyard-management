from pydantic import BaseModel, ConfigDict, Field, model_validator


class GrapeVarietyCreate(BaseModel):
    variety_name: str = Field(min_length=1, max_length=100)
    note: str | None = None


class GrapeVarietyUpdate(BaseModel):
    variety_name: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = None

    @model_validator(mode="after")
    def require_name_when_provided(self):
        if "variety_name" in self.model_fields_set and self.variety_name is None:
            raise ValueError("variety_name cannot be null")
        return self


class GrapeVarietyRead(GrapeVarietyCreate):
    model_config = ConfigDict(from_attributes=True)

    variety_id: int
