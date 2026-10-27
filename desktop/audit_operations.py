"""Audit decisions independent of widgets, transports, and backend internals."""
from dataclasses import dataclass, field
from datetime import date
import re
from uuid import uuid4

FIELDS = ('driver_name','helper_name','audit_date','station','plate_number','remarks')
LABELS = {'driver_name':'Driver name','helper_name':'Helper name','audit_date':'Audit date',
          'station':'Station','plate_number':'Plate number','remarks':'Remarks'}
LIMITS = {'driver_name':200,'helper_name':200,'station':150,'plate_number':30,'remarks':10000}


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('Check the indicated audit fields.')


def normalize(values):
    errors, result = {}, {}
    if set(values) - set(FIELDS):
        errors['form'] = 'Only audit form fields are accepted.'
    for key in FIELDS:
        value = values.get(key)
        optional = key in ('helper_name','remarks')
        if optional and value is None:
            result[key] = None
            continue
        if not isinstance(value,str):
            errors[key] = 'Enter text.'
            continue
        value = value.strip()
        if key == 'audit_date':
            try:
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value) or date.fromisoformat(value).year < 1000:
                    raise ValueError
            except ValueError:
                errors[key] = 'Use a real YYYY-MM-DD date (years 1000–9999).'
        elif len(value) > LIMITS[key]:
            errors[key] = f'Use at most {LIMITS[key]:,} characters.'
        elif not optional and not value:
            errors[key] = 'This field is required.'
        result[key] = value or None if optional else value
    if errors:
        raise ValidationError(errors)
    return result


def record_values(record):
    return {key:getattr(record,key) for key in FIELDS}


def changed_fields(record,values):
    return {key:value for key,value in normalize(values).items() if value != getattr(record,key)}


def can_edit(record,user_id,role):
    return record.deleted_at is None and (role == 'ADMIN' or
            role == 'AUDITOR' and record.audited_by_user_id == user_id)


def ambiguous(error):
    return error.status == 0 or error.status >= 500


@dataclass(frozen=True,init=False,repr=False)
class CreationIntent:
    user_id: int
    key: str
    _values: tuple

    def __init__(self,user_id,payload):
        object.__setattr__(self,'user_id',user_id)
        object.__setattr__(self,'key',str(uuid4()))
        object.__setattr__(self,'_values',tuple(normalize(payload).items()))

    @property
    def payload(self):
        return dict(self._values)


@dataclass(repr=False)
class AuditDraft:
    values: dict
    baseline: object = None
    intent: CreationIntent | None = None
    pending: bool = False
    uncertain: bool = False
    unavailable: bool = False
    latest: object = None
    message: str = ''
    errors: dict = field(default_factory=dict)

    @property
    def dirty(self):
        if self.pending or self.uncertain:
            return True
        try:
            current=normalize(self.values)
            if self.baseline:
                return bool(changed_fields(self.baseline,current))
            return any(value for key,value in self.values.items() if key != 'audit_date')
        except ValidationError:
            return True
