from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class AuditFields(BaseModel):
    """Exactly the seven business fields; identity is supplied by future auth."""
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    driver_name: Name
    helper_name: Annotated[str, StringConstraints(max_length=200)] | None = None
    audit_date: date
    station: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    plate_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    remarks: str | None = None
    audited_by_name: Name


class AuditRead(AuditFields):
    id: int
    version: int = Field(ge=1)
