"""Snapshot export and consent-preserving append-only import on the owning thread."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json

from .models import OfflineError, new_uuid, valid_date
from .transfer import (
    AUDIT_KEYS, MAX_AUDITS, MAX_EVENTS, canonical_json, decode_transfer,
    encode_transfer, invalid,
)


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            invalid()
        return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (TypeError, ValueError):
        invalid()


def wire_audit(row):
    if set(row) != AUDIT_KEYS:
        invalid()
    result = dict(row)
    for key in ('created_at', 'updated_at', 'archived_at'):
        if result[key] is not None:
            result[key] = timestamp(result[key])
    return result


def _stored_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                invalid()
            result[key] = item
        return result
    try:
        return json.loads(value, object_pairs_hook=unique)
    except (TypeError, ValueError, RecursionError):
        invalid()


def wire_event(row):
    return dict(id=row['id'], audit_id=row['audit_id'], revision=row['revision'],
        action=row['action'], actor_name=row['actor_name'], actor_profile_id=row['actor_profile_id'],
        created_at=timestamp(row['created_at']),
        before=None if row['before_json'] is None else wire_audit(_stored_json(row['before_json'])),
        after=wire_audit(_stored_json(row['after_json'])))


def _canceled(cancel):
    if cancel():
        raise OfflineError('canceled', 'Transfer canceled before completion. Check records before retrying if completion was interrupted.')


@dataclass(frozen=True)
class ImportPreview:
    content_sha256: str
    new_ids: tuple
    duplicate_ids: tuple
    conflict_ids: tuple


@dataclass(frozen=True)
class ImportResult:
    imported: int
    duplicates: int
    conflicts: int


class TransferStore:
    def __init__(self, repository):
        self.repository = repository

    @property
    def db(self):
        return self.repository._connection

    def _audit(self, identity):
        row = self.db.execute('SELECT * FROM audit_records WHERE id=?', (identity,)).fetchone()
        if row is None:
            return None
        return wire_audit({key: row[key] for key in AUDIT_KEYS})

    def _events(self, identity):
        rows = self.db.execute('SELECT * FROM audit_events WHERE audit_id=? ORDER BY revision', (identity,))
        result = []
        for row in rows:
            if len(result) >= MAX_EVENTS:
                invalid()
            result.append(wire_event(row))
        return result

    def export(self, date_from=None, date_to=None, cancel=lambda: False):
        for value in (date_from, date_to):
            if value is not None and not valid_date(value):
                invalid()
        if date_from is not None and date_to is not None and date_from > date_to:
            invalid()
        _canceled(cancel)
        with self.repository._transaction():
            clauses, args = [], []
            for op, value in (('>=', date_from), ('<=', date_to)):
                if value is not None:
                    clauses.append('audit_date ' + op + ' ?')
                    args.append(value)
            where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
            rows = self.db.execute('SELECT * FROM audit_records' + where + ' ORDER BY id LIMIT ?', (*args, MAX_AUDITS + 1))
            audits, events = [], []
            for row in rows:
                _canceled(cancel)
                if len(audits) >= MAX_AUDITS:
                    invalid()
                audits.append(wire_audit({key: row[key] for key in AUDIT_KEYS}))
                events.extend(self._events(row['id']))
                if len(events) > MAX_EVENTS:
                    invalid()
            source = self.db.execute("SELECT value FROM app_meta WHERE key='installation_id'").fetchone()[0]
        _canceled(cancel)
        manifest = dict(format='bhli-audit-transfer', format_version=1, package_id=new_uuid(),
            source_installation_id=source, exported_at=timestamp(datetime.now(timezone.utc).isoformat()),
            filters=dict(date_from=date_from, date_to=date_to, include_archived=True))
        result = encode_transfer(manifest, audits, events)
        _canceled(cancel)
        return result

    def _classify(self, package, cancel=lambda: False):
        receipt = self.db.execute('SELECT content_sha256 FROM transfer_receipts WHERE package_id=?', (package.manifest['package_id'],)).fetchone()
        if receipt is not None and receipt[0] != package.content_sha256:
            raise OfflineError('conflict', 'This package identity was already used for different content. Nothing was imported.')
        histories = {}
        for event in package.events:
            _canceled(cancel)
            histories.setdefault(event['audit_id'], []).append(event)
            row = self.db.execute('SELECT * FROM audit_events WHERE id=?', (event['id'],)).fetchone()
            if row is not None and wire_event(row) != event:
                raise OfflineError('conflict', 'This file contains a history identity already used for different content. Nothing was imported.')
        new, duplicate, conflict = [], [], []
        for audit in package.audits:
            _canceled(cancel)
            existing = self._audit(audit['id'])
            if existing is None:
                new.append(audit['id'])
            elif existing == audit and self._events(audit['id']) == histories[audit['id']]:
                duplicate.append(audit['id'])
            else:
                conflict.append(audit['id'])
        return ImportPreview(package.content_sha256, tuple(new), tuple(duplicate), tuple(conflict))

    def preview(self, raw):
        package = decode_transfer(raw)
        with self.repository._transaction():
            return self._classify(package)

    def apply(self, raw, preview, cancel=lambda: False):
        # Decode again from immutable staged bytes; a mutable package object or
        # UI-supplied preview never authorizes bypassing validation.
        package = decode_transfer(raw)
        _canceled(cancel)
        with self.repository._transaction(write=True):
            current = self._classify(package, cancel)
            if not isinstance(preview, ImportPreview) or current != preview:
                raise OfflineError('conflict', 'Local audits changed after preview. Review the file again before importing.')
            selected = set(current.new_ids)
            for audit in package.audits:
                if audit['id'] not in selected:
                    continue
                _canceled(cancel)
                self.db.execute('INSERT OR IGNORE INTO auditor_identities(id) VALUES (?)', (audit['profile_id'],))
                columns = tuple(audit)
                self.db.execute('INSERT INTO audit_records (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(audit.values()))
            for event in package.events:
                if event['audit_id'] not in selected:
                    continue
                _canceled(cancel)
                self.db.execute('INSERT OR IGNORE INTO auditor_identities(id) VALUES (?)', (event['actor_profile_id'],))
                self.db.execute('INSERT INTO audit_events(id,audit_id,revision,action,actor_name,actor_profile_id,created_at,before_json,after_json) VALUES (?,?,?,?,?,?,?,?,?)',
                    (event['id'], event['audit_id'], event['revision'], event['action'], event['actor_name'], event['actor_profile_id'], event['created_at'],
                     None if event['before'] is None else canonical_json(event['before']), canonical_json(event['after'])))
            _canceled(cancel)
            self.db.execute('INSERT INTO transfer_receipts(package_id,content_sha256,source_installation_id,imported_at,imported_count) VALUES (?,?,?,?,?) ON CONFLICT(package_id) DO NOTHING',
                (package.manifest['package_id'], package.content_sha256, package.manifest['source_installation_id'], timestamp(datetime.now(timezone.utc).isoformat()), len(selected)))
            if self.db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                invalid()
            _canceled(cancel)
        return ImportResult(len(current.new_ids), len(current.duplicate_ids), len(current.conflict_ids))
