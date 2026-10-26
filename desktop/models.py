"""Strict, immutable desktop contracts, independent of backend implementation."""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from urllib.parse import urlencode
import re


def integer(value, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid integer')
    return value


def text(data, key, maximum=200, optional=False):
    value = data.get(key)
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip()):
        raise ValueError('Invalid text')
    return value


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Invalid time')
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class User:
    id: int
    username: str
    full_name: str
    role: str

    @classmethod
    def parse(cls, data):
        if data.get('role') not in ('ADMIN', 'AUDITOR'):
            raise ValueError('Unknown role')
        return cls(integer(data['id']), text(data, 'username', 100), text(data, 'full_name'), data['role'])


@dataclass(frozen=True)
class Login:
    token: str = field(repr=False)
    expires_at: datetime
    user: User


@dataclass(frozen=True)
class Audit:
    id: int
    version: int
    driver_name: str
    helper_name: str | None
    audit_date: str
    station: str
    plate_number: str
    remarks: str | None
    audited_by_name: str
    audited_by_user_id: int
    created_at: datetime
    updated_at: datetime
    etag: str | None = None

    @classmethod
    def parse(cls, data, etag=None):
        audit_date = data['audit_date']
        if not isinstance(audit_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', audit_date):
            raise ValueError('Invalid audit date')
        date.fromisoformat(audit_date)
        if data.get('deleted_at') is not None:
            raise ValueError('Deleted record')
        return cls(integer(data['id']), integer(data['version']), text(data, 'driver_name'),
                   text(data, 'helper_name', optional=True), audit_date, text(data, 'station', 150),
                   text(data, 'plate_number', 30), text(data, 'remarks', 10000, True),
                   text(data, 'audited_by_name'), integer(data['audited_by_user_id']),
                   timestamp(data['created_at']), timestamp(data['updated_at']), etag)


@dataclass(frozen=True)
class AuditQuery:
    page: int = 1
    page_size: int = 25
    sort: str = '-id'
    driver_name: str = ''
    plate_number: str = ''
    station: str = ''
    date_from: str = ''
    date_to: str = ''
    audited_by_user_id: int | None = None

    def __post_init__(self):
        if integer(self.page) > 10000 or integer(self.page_size) > 100:
            raise ValueError('Page is out of range')
        if self.sort not in ('id', '-id', 'audit_date', '-audit_date'):
            raise ValueError('Invalid sort')
        for value in (self.driver_name, self.plate_number, self.station):
            if not isinstance(value, str) or len(value) > 200:
                raise ValueError('Search must contain at most 200 characters')
        for value in (self.date_from, self.date_to):
            if value and (not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value)
                          or date.fromisoformat(value).year < 1000):
                raise ValueError('Use a real date in YYYY-MM-DD format')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('Start date must not follow end date')
        if self.audited_by_user_id is not None:
            integer(self.audited_by_user_id)

    def encoded(self):
        return urlencode({k: v for k, v in vars(self).items() if v is not None and v != ''})


@dataclass(frozen=True)
class AuditPage:
    items: tuple[Audit, ...]
    total: int
    page: int
    page_size: int

    @classmethod
    def parse(cls, data):
        items = data['items']
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError('Invalid items')
        return cls(tuple(Audit.parse(item) for item in items), integer(data['total'], 0),
                   integer(data['page']), integer(data['page_size']))
