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
class Account(User):
    is_active: bool

    @classmethod
    def parse(cls,data):
        user=User.parse(data)
        if type(data.get('is_active')) is not bool:
            raise ValueError('Invalid active status')
        return cls(user.id,user.username,user.full_name,user.role,data['is_active'])


@dataclass(frozen=True)
class AccountPage:
    items: tuple[Account,...]
    total: int
    page: int
    page_size: int

    @classmethod
    def parse(cls,data):
        items=data['items']
        total,page,size=integer(data['total'],0),integer(data['page']),integer(data['page_size'])
        if not isinstance(items,list) or len(items)>min(total,size) or not 1<=size<=100 or page>10000:
            raise ValueError('Invalid account page')
        users=tuple(Account.parse(item) for item in items)
        if len({user.id for user in users})!=len(users):raise ValueError('Duplicate account')
        return cls(users,total,page,size)


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
    deleted_at: datetime | None = None

    @classmethod
    def parse(cls, data, etag=None, allow_deleted=False):
        audit_date = data['audit_date']
        if not isinstance(audit_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', audit_date):
            raise ValueError('Invalid audit date')
        date.fromisoformat(audit_date)
        if data.get('deleted_at') is not None and not allow_deleted:
            raise ValueError('Deleted record')
        return cls(integer(data['id']), integer(data['version']), text(data, 'driver_name'),
                   text(data, 'helper_name', optional=True), audit_date, text(data, 'station', 150),
                   text(data, 'plate_number', 30), text(data, 'remarks', 10000, True),
                   text(data, 'audited_by_name'), integer(data['audited_by_user_id']),
                   timestamp(data['created_at']), timestamp(data['updated_at']), etag,
                   timestamp(data['deleted_at']) if data.get('deleted_at') else None)


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
    include_deleted: bool = False

    def __post_init__(self):
        if type(self.include_deleted) is not bool:
            raise ValueError('Invalid deleted filter')
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
        return urlencode({k: ('true' if v is True else v) for k, v in vars(self).items()
                          if v is not None and v != '' and v is not False})


@dataclass(frozen=True)
class AuditPage:
    items: tuple[Audit, ...]
    total: int
    page: int
    page_size: int

    @classmethod
    def parse(cls, data, allow_deleted=False):
        items = data['items']
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError('Invalid items')
        records=tuple(Audit.parse(item,allow_deleted=allow_deleted) for item in items)
        total,page,size=integer(data['total'],0),integer(data['page']),integer(data['page_size'])
        if len({r.id for r in records})!=len(records) or len(records)>min(total,size) or page>10000 or size>100:
            raise ValueError('Invalid audit page')
        return cls(records,total,page,size)


@dataclass(frozen=True)
class AuditEvent:
    id: int
    audit_id: int
    actor_user_id: int
    action: str
    before_data: Audit | None
    after_data: Audit
    created_at: datetime

    @classmethod
    def parse(cls,data,audit_id):
        if data['audit_id'] != audit_id or type(data['audit_id']) is not int or data['action'] not in ('CREATE','UPDATE','DELETE'):
            raise ValueError('Invalid history event')
        before=Audit.parse(data['before_data'],allow_deleted=True) if data['before_data'] is not None else None
        after=Audit.parse(data['after_data'],allow_deleted=True)
        if after.id != audit_id or before and before.id != audit_id:
            raise ValueError('Invalid history snapshot')
        if (data['action']=='CREATE') != (before is None):
            raise ValueError('Invalid history transition')
        return cls(integer(data['id']),audit_id,integer(data['actor_user_id']),data['action'],
                   before,after,timestamp(data['created_at']))


@dataclass(frozen=True)
class EventPage:
    items: tuple[AuditEvent,...]
    total: int
    page: int
    page_size: int

    @classmethod
    def parse(cls,data,audit_id):
        items=data['items']
        total,page,size=integer(data['total'],0),integer(data['page']),integer(data['page_size'])
        if not isinstance(items,list) or size != 25 or len(items)>min(total,size) or page>10000:
            raise ValueError('Invalid history page')
        events=tuple(AuditEvent.parse(item,audit_id) for item in items)
        if any(a.id>=b.id for a,b in zip(events,events[1:])):
            raise ValueError('Invalid history ordering')
        return cls(events,total,page,size)
