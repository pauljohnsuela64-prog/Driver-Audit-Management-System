"""Request fields exclude server-owned identity and lifecycle metadata."""
import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator
from backend.schemas.audit import AuditRead


def calendar_date(value):
    if type(value) is not date:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Use YYYY-MM-DD")
        value = date.fromisoformat(value)
    if value.year < 1000:
        raise ValueError("Date is outside MySQL DATE range")
    return value


def optional_text(value):
    return (value.strip() or None) if isinstance(value, str) else value


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]
Name = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)]
Station = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=150)]
Plate = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=30)]
Helper = Annotated[Annotated[str, StringConstraints(strict=True, max_length=200)] | None, BeforeValidator(optional_text)]
Remarks = Annotated[Annotated[str, StringConstraints(strict=True, max_length=10000)] | None, BeforeValidator(optional_text)]


class AuditCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    driver_name: Name
    helper_name: Helper = None
    audit_date: CalendarDate
    station: Station
    plate_number: Plate
    remarks: Remarks = None


class AuditPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    driver_name: Name | None = None
    helper_name: Helper = None
    audit_date: CalendarDate | None = None
    station: Station | None = None
    plate_number: Plate | None = None
    remarks: Remarks = None

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("Empty patch")
        for field in self.model_fields_set & {"driver_name", "audit_date", "station", "plate_number"}:
            if getattr(self, field) is None:
                raise ValueError("Required field cannot be null")
        return self


class AuditResponse(AuditRead):
    audited_by_user_id: int
    updated_by_user_id: int | None
    deleted_by_user_id: int | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuditPage(BaseModel):
    items: list[AuditResponse]
    page: int
    page_size: int
    total: int


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    audit_id: int
    actor_user_id: int
    action: str
    before_data: dict | None
    after_data: dict | None
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventResponse]
    page: int
    page_size: int
    total: int
