"""Strict, bounded, STORE-only offline interchange. No filesystem extraction."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
import re
import stat
import struct
import zipfile

from .models import FIELDS, OfflineError, normalize_name, normalize_values, valid_date, validate_uuid

MAX_BYTES = 32 * 1024 * 1024
MAX_MANIFEST = 64 * 1024
MAX_LINE = 256 * 1024
MAX_AUDITS = 2000
MAX_EVENTS = 10000
NAMES = ('manifest.json', 'audits.ndjson', 'events.ndjson')
AUDIT_KEYS = set(FIELDS) | {'id', 'profile_id', 'audited_by_name', 'created_at', 'updated_at', 'revision', 'archived_at'}
EVENT_KEYS = {'id', 'audit_id', 'revision', 'action', 'actor_name', 'actor_profile_id', 'created_at', 'before', 'after'}
BASE_KEYS = {'format', 'format_version', 'package_id', 'source_installation_id', 'exported_at', 'filters'}
MANIFEST_KEYS = BASE_KEYS | {'record_count', 'event_count', 'audits_sha256', 'events_sha256'}


def invalid():
    raise OfflineError('transfer', 'This transfer file is invalid, damaged, unsupported, or exceeds safe limits. No audits were imported.')


def _text(value):
    if not isinstance(value, str) or any(0xd800 <= ord(c) <= 0xdfff for c in value):
        invalid()


def canonical_json(value):
    def check(item, depth):
        if depth > 6:
            invalid()
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if not 0 <= item <= 2**53 - 1:
                invalid()
        elif isinstance(item, str):
            _text(item)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
        elif isinstance(item, dict):
            for key, child in item.items():
                _text(key)
                if not key.isascii():
                    invalid()
                check(child, depth + 1)
        else:
            invalid()
    check(value, 0)
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':'))


def _parse(raw):
    # Bound nesting before the standard parser can recurse; duplicate keys must
    # be rejected before ordinary dictionary decoding erases them.
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 6:
                invalid()
        elif byte in (93, 125):
            depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid()
            result[key] = value
        return result
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                            parse_constant=lambda _: invalid())
        if canonical_json(result).encode('ascii') + b'\n' != raw:
            invalid()
        return result
    except (ValueError, UnicodeError, RecursionError):
        invalid()


def _shape(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        invalid()


def _integer(value, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        invalid()


def _stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z', value):
        invalid()
    try:
        datetime.fromisoformat(value)
    except ValueError:
        invalid()


def validate_audit(value):
    _shape(value, AUDIT_KEYS)
    validate_uuid(value['id'])
    validate_uuid(value['profile_id'])
    _integer(value['revision'], 1)
    if normalize_values({key: value[key] for key in FIELDS}) != {key: value[key] for key in FIELDS}:
        invalid()
    if normalize_name(value['audited_by_name']) != value['audited_by_name']:
        invalid()
    _stamp(value['created_at'])
    _stamp(value['updated_at'])
    if value['archived_at'] is not None:
        _stamp(value['archived_at'])
    canonical_json(value)


def validate_content(manifest, audits, events):
    _shape(manifest, MANIFEST_KEYS)
    if manifest['format'] != 'bhli-audit-transfer' or type(manifest['format_version']) is not int or manifest['format_version'] != 1:
        invalid()
    validate_uuid(manifest['package_id'])
    validate_uuid(manifest['source_installation_id'])
    _stamp(manifest['exported_at'])
    filters = manifest['filters']
    _shape(filters, {'date_from', 'date_to', 'include_archived'})
    if filters['include_archived'] is not True:
        invalid()
    for key in ('date_from', 'date_to'):
        if filters[key] is not None and not valid_date(filters[key]):
            invalid()
    if filters['date_from'] is not None and filters['date_to'] is not None and filters['date_from'] > filters['date_to']:
        invalid()
    _integer(manifest['record_count'], maximum=MAX_AUDITS)
    _integer(manifest['event_count'], maximum=MAX_EVENTS)
    if len(audits) != manifest['record_count'] or len(events) != manifest['event_count']:
        invalid()
    for key in ('audits_sha256', 'events_sha256'):
        if not isinstance(manifest[key], str) or not re.fullmatch('[0-9a-f]{64}', manifest[key]):
            invalid()
    records = {}
    for audit in audits:
        validate_audit(audit)
        if audit['id'] in records:
            invalid()
        if filters['date_from'] is not None and audit['audit_date'] < filters['date_from']:
            invalid()
        if filters['date_to'] is not None and audit['audit_date'] > filters['date_to']:
            invalid()
        records[audit['id']] = audit
    ids = set()
    previous = {}
    for event in events:
        _shape(event, EVENT_KEYS)
        validate_uuid(event['id'])
        validate_uuid(event['audit_id'])
        validate_uuid(event['actor_profile_id'])
        if event['id'] in ids or event['audit_id'] not in records:
            invalid()
        ids.add(event['id'])
        _integer(event['revision'], 1)
        if normalize_name(event['actor_name']) != event['actor_name']:
            invalid()
        _stamp(event['created_at'])
        after = event['after']
        validate_audit(after)
        if after['id'] != event['audit_id'] or after['revision'] != event['revision'] or event['created_at'] != after['updated_at']:
            invalid()
        prior = previous.get(after['id'])
        if prior is None:
            if (event['action'] != 'CREATE' or event['revision'] != 1 or event['before'] is not None
                    or after['archived_at'] is not None or after['created_at'] != after['updated_at']
                    or event['actor_profile_id'] != after['profile_id'] or event['actor_name'] != after['audited_by_name']):
                invalid()
        else:
            validate_audit(event['before'])
            if event['before'] != prior or prior['archived_at'] is not None or after['revision'] != prior['revision'] + 1:
                invalid()
            if any(after[k] != prior[k] for k in ('id', 'profile_id', 'audited_by_name', 'created_at')):
                invalid()
            changed = any(after[k] != prior[k] for k in FIELDS)
            if event['action'] == 'UPDATE':
                if not changed or after['archived_at'] is not None:
                    invalid()
            elif event['action'] == 'ARCHIVE':
                if changed or after['archived_at'] != after['updated_at']:
                    invalid()
            else:
                invalid()
        previous[after['id']] = after
    if previous != records:
        invalid()


@dataclass(frozen=True)
class TransferPackage:
    manifest: dict
    audits: tuple
    events: tuple
    content_sha256: str


def _lines(rows, maximum):
    if len(rows) > maximum:
        invalid()
    out = bytearray()
    for row in rows:
        line = canonical_json(row).encode('ascii') + b'\n'
        if len(line) > MAX_LINE or len(out) + len(line) > MAX_BYTES:
            invalid()
        out.extend(line)
    return bytes(out)


def encode_transfer(manifest, audits, events):
    if not isinstance(manifest, dict) or set(manifest) not in (BASE_KEYS, MANIFEST_KEYS):
        invalid()
    # Validate original shapes before sorting keys from possibly hostile maps.
    for row in audits:
        _shape(row, AUDIT_KEYS)
        validate_audit(row)
    for row in events:
        _shape(row, EVENT_KEYS)
        if not isinstance(row['audit_id'], str): invalid()
        _integer(row['revision'], 1)
    audits = sorted(audits, key=lambda row: row['id'])
    events = sorted(events, key=lambda row: (row['audit_id'], row['revision']))
    a = _lines(audits, MAX_AUDITS)
    e = _lines(events, MAX_EVENTS)
    result = {key: manifest[key] for key in BASE_KEYS}
    result.update(record_count=len(audits), event_count=len(events),
                  audits_sha256=hashlib.sha256(a).hexdigest(), events_sha256=hashlib.sha256(e).hexdigest())
    validate_content(result, audits, events)
    m = canonical_json(result).encode('ascii') + b'\n'
    if len(m) > MAX_MANIFEST or len(m) + len(a) + len(e) > MAX_BYTES:
        invalid()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in zip(NAMES, (m, a, e)):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, raw)
    raw = buffer.getvalue()
    if len(raw) > MAX_BYTES: invalid()
    return raw


def _unzip(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES or len(raw) < 22:
        invalid()
    try:
        end = struct.unpack('<4s4H2IH', raw[-22:])
        if (end[0] != b'PK\x05\x06' or end[1:5] != (0, 0, 3, 3) or end[7] != 0
                or end[5] != sum(46 + len(name) for name in NAMES)
                or end[5] + end[6] != len(raw) - 22):
            invalid()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if tuple(i.filename for i in infos) != NAMES or archive.comment:
                invalid()
            offset = 0
            central = end[6]
            result = []
            total = 0
            for i in infos:
                if (i.header_offset != offset or i.compress_type != 0 or i.flag_bits not in (0, 0x800)
                        or i.extra or i.comment or i.external_attr & 0x10
                        or stat.S_IFMT(i.external_attr >> 16) not in (0, stat.S_IFREG)
                        or i.compress_size != i.file_size or i.file_size > MAX_BYTES):
                    invalid()
                header = struct.unpack_from('<4s5H3I2H', raw, offset)
                name = i.filename.encode('ascii')
                if (header[0] != b'PK\x03\x04' or header[1] > 20 or header[2] != i.flag_bits
                        or header[3] != 0 or header[6:9] != (i.CRC, i.file_size, i.file_size)
                        or header[9:] != (len(name), 0) or raw[offset+30:offset+30+len(name)] != name):
                    invalid()
                offset += 30 + len(name) + i.file_size
                c = struct.unpack_from('<4s6H3I5H2I', raw, central)
                if (c[0] != b'PK\x01\x02' or c[2] > 20 or c[3] != i.flag_bits or c[4] != 0
                        or c[5:7] != header[4:6]
                        or c[7:10] != (i.CRC, i.file_size, i.file_size) or c[10:14] != (len(name), 0, 0, 0)
                        or c[16] != i.header_offset or raw[central+46:central+46+len(name)] != name):
                    invalid()
                central += 46 + len(name)
                total += i.file_size
                if total > MAX_BYTES or (i.filename == NAMES[0] and i.file_size > MAX_MANIFEST):
                    invalid()
                result.append(archive.read(i))
            if offset != end[6] or central != len(raw) - 22:
                invalid()
            return result
    except (zipfile.BadZipFile, ValueError, IndexError, struct.error, UnicodeError, OverflowError, NotImplementedError):
        invalid()


def decode_transfer(raw):
    m, a, e = _unzip(raw)
    manifest = _parse(m)
    def rows(data, limit):
        result = []
        stream = io.BytesIO(data)
        while line := stream.readline(MAX_LINE + 1):
            if len(line) > MAX_LINE or len(result) >= limit:
                invalid()
            result.append(_parse(line))
        return result
    audits, events = rows(a, MAX_AUDITS), rows(e, MAX_EVENTS)
    validate_content(manifest, audits, events)
    if (manifest['audits_sha256'] != hashlib.sha256(a).hexdigest()
            or manifest['events_sha256'] != hashlib.sha256(e).hexdigest()
            or [r['id'] for r in audits] != sorted(r['id'] for r in audits)
            or [(r['audit_id'], r['revision']) for r in events] != sorted((r['audit_id'], r['revision']) for r in events)):
        invalid()
    digest = hashlib.sha256()
    for entry in (m, a, e):
        digest.update(entry)
    return TransferPackage(manifest, tuple(audits), tuple(events), digest.hexdigest())
