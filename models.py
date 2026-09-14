from pydantic import BaseModel, ConfigDict, field_validator
from typing import Any


# pydantic models catch data before hits the database, validate and cleans it

class AppBaseModel(BaseModel):
    # form_attributes allows Pydantic to read from ORM objects directly
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        """
        Intercepts all incoming data and converts blank or whitespace-only
        strings into None (Null) to prevent database corruption.
        """
        # only attempt to strip() if the incoming data is text
        if isinstance(v, str) and not v.strip():
            return None
        # If valid text or number, let it pass through unchanged
        return v


# ensure data is two strings after AppBaseModel does cleaning and validation
class ReadingBase(AppBaseModel):
    temperature: str
    humidity: str
