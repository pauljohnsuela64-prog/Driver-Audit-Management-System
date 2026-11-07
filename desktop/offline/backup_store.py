"""Owned same-platform replacement with independently verified recovery proof.

All entrypoints run on the repository owner. A prepared ticket is one-use and
memory-only. Startup markers describe evidence, never authorize replay.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from uuid import UUID, uuid4

from .backup_crypto import open_backup
from .backup_jobs import _flush_directory, _move_new, _write_new, read_bounded
from .backup_state import APPS, TABLES, canonical, capture_state, capture_transaction_state, decode_state
from .models import OfflineError

MARKER = 'restore-pending.json'
MARKER_KEYS = {'version', 'operation_id', 'platform', 'app_id', 'original_digest', 'intended_digest',
               'input_file', 'input_digest', 'recovery_file', 'recovery_digest', 'stage'}
DELETE_ORDER = ('audit_events', 'transfer_receipts', 'audit_records', 'local_profile', 'auditor_identities', 'app_meta')
ASSISTED_RECOVERY = (
    'Preserve this installation, its database, sidecars and encrypted recovery files. '
    'Close other offline app copies and older versions before Retry. '
    'If storage remains unreadable, use a verified encrypted backup in a fresh same-platform instance: '
    'a separate Windows OS user or new Windows PC using its normal private app data directory '
    '(Android: a separate device or supported OS user using the normal app sandbox). '
    'Complete the normal backup and restore workflow there, protecting that fresh target first. '
    'Do not clear data, uninstall, overwrite or move the damaged original. Retain it for assisted recovery '
    'and retire duplicate active identities. A lost backup password cannot be reset.'
)


@dataclass(frozen=True)
class RestorePreview:
    id: str
    candidate: object
    current: object
    unchanged: bool


@dataclass(frozen=True)
class RestoreResult:
    outcome: str
    message: str
    cleanup_warning: str = ''


def _commit(db):
    db.commit()


def _validated_current(repo, *, cancel=lambda: False):
    db = repo._connection
    db.execute('BEGIN')
    try:
        return capture_transaction_state(db, cancel=cancel)
    finally:
        if db.in_transaction:
            db.rollback()


def _reopen(repo):
    # No initializer: missing or corrupt files must never become fresh stores.
    repo._connection.close()
    db = sqlite3.connect(repo._path.as_uri() + '?mode=rw', uri=True,
                         isolation_level=None, timeout=repo._timeout)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    repo._connection = db


def _read_marker(directory):
    path = directory / MARKER
    if path.is_symlink():
        raise ValueError('Unsafe marker')
    with path.open('rb') as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('Oversize marker')
    marker = json.loads(raw.decode('ascii'))
    if not isinstance(marker, dict) or set(marker) != MARKER_KEYS or canonical(marker) + b'\n' != raw:
        raise ValueError('Invalid marker')
    if (type(marker['version']) is not int or marker['version'] != 1 or marker['platform'] != 'windows' or
            marker['app_id'] != APPS['windows'] or marker['stage'] != 'pending' or
            str(UUID(marker['operation_id'], version=4)) != marker['operation_id']):
        raise ValueError('Unsupported marker')
    for key in ('original_digest', 'intended_digest', 'input_digest', 'recovery_digest'):
        if not isinstance(marker[key], str) or not re.fullmatch('[0-9a-f]{64}', marker[key]):
            raise ValueError('Invalid digest')
    for key, digest_key in (('input_file', 'input_digest'), ('recovery_file', 'recovery_digest')):
        name = marker[key]
        if not isinstance(name, str) or not re.fullmatch(r'backup-[0-9a-f]{32}\.bhlibackup', name):
            raise ValueError('Unsafe evidence filename')
        if hashlib.sha256(read_bounded(directory / name)).hexdigest() != marker[digest_key]:
            raise ValueError('Missing or changed evidence')
    return marker


def _resolve_marker(directory, marker):
    try:
        _move_new(directory / MARKER, directory / ('restore-resolved-' + marker['operation_id'] + '.json'))
        return ''
    except OSError:
        return 'The verified outcome is known, but its recovery marker could not be archived. Retain all encrypted evidence.'


def _publish_marker(directory, raw):
    stage = directory / ('restore-marker-stage-' + uuid4().hex + '.tmp')
    try:
        _write_new(stage, raw)
        with stage.open('rb') as stream:
            if stream.read(4097) != raw:
                raise OSError('Recovery marker stage readback failed')
        _move_new(stage, directory / MARKER)
    finally:
        try:
            stage.unlink(missing_ok=True)
        except OSError:
            raise OfflineError('backup_cleanup', 'An owned temporary recovery marker could not be removed. Preserve the recovery directory; replacement was not admitted.') from None


def _classify(repo, directory, *, reopen):
    try:
        marker = _read_marker(directory)
        if reopen:
            _reopen(repo)
        current = _validated_current(repo)
        if current.digest == marker['intended_digest']:
            outcome = 'RESTORED'
        elif current.digest == marker['original_digest']:
            outcome = 'ORIGINAL'
        else:
            raise ValueError('Current state does not match either complete state')
        warning = _resolve_marker(directory, marker)
        repo._write_blocked = False
        repo._recovery_pending = bool(warning)
        return RestoreResult(outcome,
            'The complete restored state is present.' if outcome == 'RESTORED' else
            'Replacement did not take effect. A fresh confirmed attempt is required.', warning)
    except Exception:
        repo._write_blocked = True
        return RestoreResult('UNKNOWN', 'The restoration outcome cannot be verified. Local changes are blocked. ' + ASSISTED_RECOVERY)


def reconcile_startup(repository, private_directory):
    """Call before cleanup or ordinary UI admission, while lifetime lease is held."""
    repository._check()
    if repository._lease is None or not repository._lease.held:
        raise OfflineError('store_owned', 'Recovery reconciliation requires exclusive local store ownership.')
    directory = Path(private_directory)
    if directory.is_symlink():
        repository._write_blocked = True
        return RestoreResult('UNKNOWN', ASSISTED_RECOVERY)
    if not os.path.lexists(directory / MARKER):
        return None
    return _classify(repository, directory, reopen=False)


def bootstrap_check(database_path, private_directory):
    """Read-only guard before the ordinary repository initializer can run.

    Hold StoreLease first. Missing/empty stores with pending evidence are never
    initialized. Invalid evidence fails closed without opening SQLite at all.
    """
    directory = Path(private_directory)
    path = Path(database_path)
    try:
        if directory.is_symlink():
            raise ValueError('Unsafe recovery directory')
        if not os.path.lexists(directory / MARKER):
            return
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError('Pending recovery requires an existing nonempty store')
        _read_marker(directory)
    except Exception:
        raise OfflineError('recovery_required', 'Pending recovery evidence or current storage cannot be verified. ' + ASSISTED_RECOVERY) from None


class BackupStore:
    def __init__(self, jobs):
        self.jobs = jobs
        self.repository = jobs.repository
        self._previews = {}
        self._tickets = {}

    def _ownership(self):
        repo = self.repository
        repo._check()
        if repo._lease is None or not repo._lease.held or repo._write_blocked or repo._recovery_pending:
            raise OfflineError('recovery_required', 'Exclusive valid local storage is required for restoration. ' + ASSISTED_RECOVERY)

    def inspect_restore(self, source, password, *, cancel=lambda: False):
        self._ownership()
        self._previews.clear()
        inspected = self.jobs.inspect(source, password, cancel=cancel)
        identifier = uuid4().hex
        if inspected.candidate_digest != inspected.current_digest:
            self._previews[identifier] = inspected
        return RestorePreview(identifier, inspected.candidate, inspected.current,
                              inspected.candidate_digest == inspected.current_digest)

    def cancel_preview(self, preview_id=None):
        self.repository._check()
        if preview_id is None:
            self._previews.clear()
        else:
            self._previews.pop(preview_id, None)

    def cancel_prepared(self, ticket):
        self.repository._check()
        if self._tickets.pop(ticket, None) is not None:
            self.repository._maintenance = None

    def prepare_restore(self, preview_id, password, recovery_destination, *, cancel=lambda: False, progress=lambda value: None):
        self._ownership()
        budget = _RestoreBudget(cancel)
        repo = self.repository
        preview = self._previews.pop(preview_id, None)
        if preview is None or preview.candidate_digest == preview.current_digest:
            raise OfflineError('restore_preview', 'Inspect a changed backup before preparing replacement.')
        if repo._maintenance is not None or os.path.lexists(self.jobs.directory / MARKER):
            raise OfflineError('maintenance', 'Resolve the pending recovery operation first.')
        ticket = uuid4().hex
        repo._maintenance = ticket
        try:
            budget.check()
            current = _validated_current(repo, cancel=budget.cancelled)
            budget.check()
            if current.digest != preview.current_digest:
                raise OfflineError('restore_stale', 'Local state changed. Inspect the backup again before replacement.')
            # Authenticate the frozen private incoming artifact again, never the selected source.
            incoming = decode_state(open_backup(self.jobs.read_artifact(preview.artifact_id), password, platform='windows'), platform='windows')
            budget.check()
            if incoming.digest != preview.candidate_digest:
                raise OfflineError('restore_stale', 'The frozen candidate changed. Inspect it again.')
            progress('Protecting current data with this backup password')
            recovery = self.jobs._create_snapshot(current, password, cancel=budget.cancelled, progress=progress)
            budget.check()
            published = self.jobs.publish(recovery.id, recovery_destination, cancel=budget.cancelled)
            budget.check()
            # Independently authenticate actual PUBLIC destination before final-confirm ticket.
            proof = decode_state(open_backup(read_bounded(published.path), password, platform='windows'), platform='windows')
            budget.check()
            private_proof = decode_state(open_backup(self.jobs.read_artifact(recovery.id), password, platform='windows'), platform='windows')
            budget.check()
            if proof.digest != current.digest or private_proof.digest != current.digest:
                raise OfflineError('restore_recovery', 'The current recovery backup could not be verified.')
            self._tickets[ticket] = (preview, incoming, recovery, current.digest)
            return ticket
        except BaseException:
            repo._maintenance = None
            raise

    def apply_restore(self, ticket, *, cancel=lambda: False):
        self._ownership()
        # Human final-confirmation time is deliberately outside active work.
        budget = _RestoreBudget(cancel)
        prepared = self._tickets.pop(ticket, None)
        repo = self.repository
        if prepared is None or repo._maintenance != ticket:
            raise OfflineError('restore_ticket', 'A verified prepared replacement ticket is required.')
        preview, incoming, recovery, original_digest = prepared
        directory = self.jobs.directory
        marked = False
        db = repo._connection
        try:
            # Cancellation is classified with durable evidence below. Time is
            # bounded immediately; no replacement is admitted before both checks.
            budget.check(check_cancel=False)
            marker = dict(version=1, operation_id=str(uuid4()), platform='windows', app_id=APPS['windows'],
                          original_digest=original_digest, intended_digest=incoming.digest,
                          input_file=self.jobs._path(preview.artifact_id).name,
                          input_digest=hashlib.sha256(self.jobs.read_artifact(preview.artifact_id)).hexdigest(),
                          recovery_file=self.jobs._path(recovery.id).name,
                          recovery_digest=hashlib.sha256(self.jobs.read_artifact(recovery.id)).hexdigest(), stage='pending')
            budget.check(check_cancel=False)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=EXTRA')
            if (db.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or
                    db.execute('PRAGMA synchronous').fetchone()[0] != 3 or
                    db.execute('PRAGMA journal_mode').fetchone()[0].lower() not in ('delete', 'truncate', 'persist', 'wal')):
                raise OfflineError('restore_durability', 'Required SQLite durability settings are unavailable.')
            raw = canonical(marker) + b'\n'
            if len(raw) > 4096:
                raise OfflineError('restore_marker', 'The recovery marker exceeds safe limits.')
            _publish_marker(directory, raw)
            marked = True
            _read_marker(directory)
            budget.check()
            db.execute('BEGIN IMMEDIATE')
            if capture_transaction_state(db, cancel=budget.cancelled).digest != original_digest:
                raise OfflineError('restore_stale', 'Local state changed after preparation.')
            budget.check()
            for table in DELETE_ORDER:
                budget.check()
                db.execute('DELETE FROM ' + table)
            for table in TABLES:
                budget.check()
                # Known built-in schema defines column names; payload supplies values only.
                columns = tuple(row[1] for row in db.execute('PRAGMA table_info(' + table + ')'))
                sql = 'INSERT INTO ' + table + ' (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')'
                for row in incoming.rows[table]:
                    budget.check()
                    db.execute(sql, tuple(row[column] for column in columns))
            budget.check()
            db.execute("DELETE FROM sqlite_sequence WHERE name='audit_records'")
            if incoming.sequence is not None:
                db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('audit_records',?)", (incoming.sequence,))
            if capture_transaction_state(db, cancel=budget.cancelled).digest != incoming.digest:
                raise OfflineError('restore_verify', 'The complete replacement state could not be validated.')
            budget.check()
            _commit(db)
        except BaseException:
            try:
                if db.in_transaction:
                    db.rollback()
            except sqlite3.Error:
                pass
            if not marked:
                raise
        finally:
            repo._maintenance = None
        # COMMIT success, exception, lost acknowledgement and rollback all use proof.
        return _classify(repo, directory, reopen=True)


class _RestoreBudget:
    """One active-work deadline; mandatory outcome checks always run afterward."""
    def __init__(self, cancel):
        self.deadline = time.monotonic() + 600
        self.cancel = cancel

    def check(self, *, check_cancel=True):
        if time.monotonic() > self.deadline:
            raise OfflineError('restore_timeout', 'Restoration exceeded the active operation time limit. Encrypted recovery evidence is retained.')
        if check_cancel and self.cancel():
            raise OfflineError('cancelled', 'Restoration cancelled before COMMIT. Encrypted recovery evidence is retained.')

    def cancelled(self):
        self.check()
        return False
