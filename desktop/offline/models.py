"""Immutable local audit values and the established Android input contract."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Generic, TypeVar
from uuid import uuid4


class OfflineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def invalid_input():
    raise OfflineError("validation", "Check the entered values.")


_REQUIRED_SPACE = "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
_OPTIONAL_SPACE = _REQUIRED_SPACE + "\u001c\u001d\u001e\u001f"
FIELDS = ("driver_name", "helper_name", "audit_date", "station", "plate_number", "remarks")


def normalize_text(value, limit, *, optional=False):
    if not isinstance(value, str):
        invalid_input()
    text = value.strip(_OPTIONAL_SPACE if optional else _REQUIRED_SPACE)
    if (not optional and not text) or len(text) > limit:
        invalid_input()
    return text


def normalize_name(value):
    return normalize_text(value, 200)


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def normalize_values(values):
    if not isinstance(values, Mapping) or set(values) - set(FIELDS):
        invalid_input()
    if not valid_date(values.get("audit_date")):
        invalid_input()
    result = {}
    for field, limit in (("driver_name", 200), ("helper_name", 200), ("station", 150), ("plate_number", 30), ("remarks", 10000)):
        optional = field in ("helper_name", "remarks")
        value = values.get(field)
        result[field] = None if optional and value is None else normalize_text(value, limit, optional=optional)
        if optional and result[field] == "":
            result[field] = None
    result["audit_date"] = values["audit_date"]
    return {key: result[key] for key in FIELDS}


def new_uuid():
    return str(uuid4())


def validate_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value):
        invalid_input()


@dataclass(frozen=True)
class LocalProfile:
    id: str
    name: str


@dataclass(frozen=True)
class LocalAudit:
    id: str
    driver_name: str
    helper_name: str | None
    audit_date: str
    station: str
    plate_number: str
    remarks: str | None
    audited_by_name: str
    profile_id: str
    revision: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @property
    def archived(self):
        return self.archived_at is not None


@dataclass(frozen=True)
class LocalEvent:
    id: str
    audit_id: str
    revision: int
    action: str
    actor_name: str
    actor_profile_id: str
    created_at: datetime
    before: LocalAudit | None
    after: LocalAudit


@dataclass(frozen=True)
class AuditFilter:
    driver: str = ""
    plate: str = ""
    station: str = ""
    date_from: str | None = None
    date_to: str | None = None
    include_archived: bool = False
    sort: str = "-created"
    page: int = 1
    page_size: int = 25


T = TypeVar("T")


@dataclass(frozen=True)
class LocalPage(Generic[T]):
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int
