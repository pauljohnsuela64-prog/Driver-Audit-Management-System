"""Untrusted transfer bytes cross the same codec seam used by both applications."""
from copy import deepcopy
import hashlib
import io
import json
import zipfile

import pytest


def sample():
    stamp = '2026-11-06T01:02:03.000004Z'
    identity = '00000000-0000-4000-8000-000000000001'
    audit = dict(id='00000000-0000-4000-8000-000000000002', profile_id=identity,
        driver_name='Fictional \u99d5\u99db\U0001f69a', helper_name=None, audit_date='2026-11-06',
        station='North', plate_number='000123', remarks='Line\nTwo',
        audited_by_name='Original Auditor', created_at=stamp, updated_at=stamp,
        revision=1, archived_at=None)
    event = dict(id='00000000-0000-4000-8000-000000000003', audit_id=audit['id'],
        revision=1, action='CREATE', actor_name=audit['audited_by_name'],
        actor_profile_id=identity, created_at=stamp, before=None, after=deepcopy(audit))
    manifest = dict(format='bhli-audit-transfer', format_version=1,
        package_id='00000000-0000-4000-8000-000000000004',
        source_installation_id='00000000-0000-4000-8000-000000000005',
        exported_at=stamp, filters=dict(date_from=None, date_to=None, include_archived=True))
    return manifest, [audit], [event]


def repack(data, entry, transform):
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        entries = [(i.filename, source.read(i)) for i in source.infolist()]
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_STORED) as output:
        for name, raw in entries:
            output.writestr(name, transform(raw) if name == entry else raw)
    return result.getvalue()


def test_roundtrip_unicode_identifiers_nulls_and_canonical_bytes():
    from desktop.offline.transfer import canonical_json, encode_transfer, decode_transfer
    manifest, audits, events = sample()
    raw = encode_transfer(manifest, audits, events)
    result = decode_transfer(raw)
    assert result.audits == tuple(audits) and result.events == tuple(events)
    assert result.audits[0]['plate_number'] == '000123'
    assert canonical_json({'z': '\U0001f69a', 'a': None}) == '{"a":null,"z":"\\ud83d\\ude9a"}'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.namelist() == ['manifest.json', 'audits.ndjson', 'events.ndjson']
        a = archive.read('audits.ndjson')
        assert a.isascii() and a.endswith(b'\n')
        assert result.manifest['audits_sha256'] == hashlib.sha256(a).hexdigest()
        assert result.content_sha256 == hashlib.sha256(b''.join(archive.read(n) for n in archive.namelist())).hexdigest()


@pytest.mark.parametrize('change', ['origin', 'revision', 'born_archived', 'create_time', 'actor', 'extra', 'bool_revision'])
def test_reject_invalid_create_chain(change):
    from desktop.offline.transfer import encode_transfer
    from desktop.offline.models import OfflineError
    manifest, audits, events = sample()
    if change == 'origin': events[0]['after']['profile_id'] = manifest['package_id']
    if change == 'revision': audits[0]['revision'] = 2
    if change == 'born_archived': audits[0]['archived_at'] = events[0]['after']['archived_at'] = audits[0]['created_at']
    if change == 'create_time': events[0]['after']['updated_at'] = '2026-11-06T01:02:04.000004Z'
    if change == 'actor': events[0]['actor_profile_id'] = manifest['package_id']
    if change == 'extra': audits[0]['sql'] = 'DROP TABLE audit_records'
    if change == 'bool_revision': audits[0]['revision'] = True
    with pytest.raises(OfflineError): encode_transfer(manifest, audits, events)


def test_complete_update_archive_chain_and_clock_correction():
    from desktop.offline.transfer import encode_transfer, decode_transfer
    manifest, audits, events = sample()
    before = deepcopy(audits[0])
    audits[0].update(driver_name='Changed', revision=2, updated_at='2026-11-05T01:02:03.000004Z')
    update = dict(events[0], id=manifest['package_id'], revision=2, action='UPDATE', before=before, after=deepcopy(audits[0]), created_at=audits[0]['updated_at'])
    events.append(update)
    before = deepcopy(audits[0])
    audits[0].update(revision=3, archived_at='2026-11-06T02:00:00.000000Z', updated_at='2026-11-06T02:00:00.000000Z')
    events.append(dict(update, id=manifest['source_installation_id'], action='ARCHIVE', revision=3, before=before, after=deepcopy(audits[0]), created_at=audits[0]['updated_at']))
    assert decode_transfer(encode_transfer(manifest, audits, events)).audits[0]['revision'] == 3


@pytest.mark.parametrize('entry,transform', [
    ('manifest.json', lambda b: b.replace(b'"format_version":1', b'"format_version":2')),
    ('manifest.json', lambda b: b.replace(b'"format_version":1', b'"format_version":1,"format_version":1')),
    ('audits.ndjson', lambda b: b.replace(b'000123', b'000999')),
    ('events.ndjson', lambda b: b[:-1]),
])
def test_reject_corruption_versions_duplicate_keys_and_noncanonical(entry, transform):
    from desktop.offline.transfer import encode_transfer, decode_transfer
    from desktop.offline.models import OfflineError
    with pytest.raises(OfflineError): decode_transfer(repack(encode_transfer(*sample()), entry, transform))


@pytest.mark.parametrize('bad', [b'not zip', b'PK\x03\x04', b''])
def test_reject_malformed_zip(bad):
    from desktop.offline.transfer import decode_transfer
    from desktop.offline.models import OfflineError
    with pytest.raises(OfflineError): decode_transfer(bad)


def test_empty_package_and_trailing_payload_rejection():
    from desktop.offline.transfer import encode_transfer, decode_transfer
    from desktop.offline.models import OfflineError
    raw = encode_transfer(sample()[0], [], [])
    assert decode_transfer(raw).audits == ()
    with pytest.raises(OfflineError): decode_transfer(raw + b'payload')


@pytest.mark.parametrize('value', [float('nan'), 1.5, {'x': '\ud800'}, {'x': 2**53}, {'x': -1}])
def test_canonical_rejects_unsupported_values(value):
    from desktop.offline.transfer import canonical_json
    from desktop.offline.models import OfflineError
    with pytest.raises(OfflineError): canonical_json(value)
