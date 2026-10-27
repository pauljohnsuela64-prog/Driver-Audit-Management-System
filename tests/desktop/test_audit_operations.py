from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from desktop import audit_operations as operations
from desktop.models import Audit
from tests.desktop.test_api import AUDIT


def values(**changes):
    return dict(driver_name=' Example ', helper_name=' ', audit_date='2026-10-27',
                station=' North ', plate_number=' ABC ', remarks=' Notes ', **{}) | changes


def test_normalization_and_immutable_creation_intent():
    data = operations.normalize(values())
    assert data == dict(driver_name='Example', helper_name=None, audit_date='2026-10-27',
                        station='North', plate_number='ABC', remarks='Notes')
    intent = operations.CreationIntent(1, data)
    assert str(UUID(intent.key)) == intent.key
    data['driver_name'] = 'Changed'
    assert intent.payload['driver_name'] == 'Example'
    copy = intent.payload
    copy['driver_name'] = 'Changed again'
    assert intent.payload['driver_name'] == 'Example'
    with pytest.raises((FrozenInstanceError, AttributeError)):
        intent.key = 'replacement'


@pytest.mark.parametrize('field,value', [('driver_name',' '), ('driver_name','x'*201),
    ('helper_name','x'*201), ('station','x'*151), ('plate_number','x'*31),
    ('remarks','x'*10001), ('audit_date','2026-02-30'), ('audit_date','0999-12-31'),
    ('audit_date','2026-1-1'), ('driver_name',None), ('remarks',42)])
def test_invalid_form_values_have_safe_field_errors(field,value):
    with pytest.raises(operations.ValidationError) as error:
        operations.normalize(values(**{field:value}))
    assert field in error.value.errors
    assert str(value) not in str(error.value) if len(str(value)) > 20 else True


def test_mass_assignment_and_optional_clearing_and_changed_fields():
    with pytest.raises(operations.ValidationError):
        operations.normalize(values(role='ADMIN'))
    record = Audit.parse(AUDIT, '"2"')
    data = operations.record_values(record)
    assert operations.changed_fields(record, data) == {}
    data['helper_name'] = ''
    data['remarks'] = ' New '
    assert operations.changed_fields(record, data) == {'remarks':'New'}
    assert operations.can_edit(record, 1, 'AUDITOR')
    assert not operations.can_edit(record, 2, 'AUDITOR')
    assert operations.can_edit(record, 2, 'ADMIN')


def test_creation_retry_policy_is_conservative():
    from desktop.api import ApiError
    for status in (0, 500, 502, 503):
        assert operations.ambiguous(ApiError(status))
    for status in (401,403,404,409,422,429):
        assert not operations.ambiguous(ApiError(status))
