"""Owner-thread backup generation and bounded, new-only encrypted file IO.

Only encrypted bytes reach disk. Handles expose neither passwords nor SQL.
Retained encrypted artifacts are deliberately excluded from transient cleanup.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import time
from uuid import uuid4

from .backup_crypto import MAX_PAYLOAD, open_backup, seal_backup
from .backup_state import capture_state, decode_state, encode_state
from .models import OfflineError

MAX_FILE = MAX_PAYLOAD + 112
MAX_WORKSPACE = 512 * 1024 * 1024


def read_bounded(path):
    path = Path(path)
    if path.is_symlink():
        raise OfflineError('backup_file', 'Backup files must be regular files.')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 112 <= info.st_size <= MAX_FILE or path.is_symlink():
            raise OfflineError('backup_file', 'This backup is incomplete or exceeds safe limits.')
        raw = stream.read(MAX_FILE + 1)
        if len(raw) != info.st_size or len(raw) > MAX_FILE:
            raise OfflineError('backup_file', 'The backup changed while being read.')
        return raw


def _flush_directory(directory):
    if os.name != 'nt':
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _move_new(source, target):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        move = ctypes.WinDLL('kernel32', use_last_error=True).MoveFileExW
        move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move.restype = wintypes.BOOL
        # WRITE_THROUGH, deliberately without REPLACE_EXISTING or COPY_ALLOWED.
        if not move(str(source), str(target), 8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.link(source, target)
        source.unlink()
        _flush_directory(target.parent)


def _write_new(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        if stream.write(raw) != len(raw):
            raise OSError('Incomplete encrypted write')
        stream.flush()
        os.fsync(stream.fileno())
    _flush_directory(path.parent)


@dataclass(frozen=True)
class BackupArtifact:
    id: str
    ciphertext_digest: str
    state_digest: str
    size: int


@dataclass(frozen=True)
class BackupPreview:
    artifact_id: str
    candidate_digest: str
    current_digest: str
    candidate: object
    current: object


@dataclass(frozen=True)
class Publication:
    path: Path
    cleanup_warning: str = ''


class BackupJobs:
    def __init__(self, repository, private_directory):
        self.repository = repository
        directory = Path(private_directory)
        if directory.is_symlink():
            raise OfflineError('backup_file', 'The private backup directory is unavailable.')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory = directory.resolve(strict=True)
        self._artifacts = {}

    def _path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier):
            raise OfflineError('backup_file', 'The encrypted backup handle is unavailable.')
        return self.directory / ('backup-' + identifier + '.bhlibackup')

    def _check(self, cancel, deadline):
        if cancel():
            raise OfflineError('cancelled', 'Backup cancelled before completion.')
        if time.monotonic() > deadline:
            raise OfflineError('backup_limit', 'The backup exceeded the operation time limit.')

    def _retain(self, raw, state):
        # Retained evidence counts toward the private workspace ceiling. Refuse
        # growth instead of automatic retention deletion, including pending data.
        used = 0
        for entry in self.directory.iterdir():
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise OfflineError('backup_file', 'Unexpected private backup entries require review. No evidence was removed.')
            used += info.st_size
            if used + len(raw) > MAX_WORKSPACE:
                raise OfflineError('backup_limit', 'The private backup workspace is full. Preserve existing encrypted recovery files and arrange assisted review before creating another backup.')
        if len(raw) > MAX_WORKSPACE or shutil.disk_usage(self.directory).free < len(raw) + 1024 * 1024:
            raise OfflineError('backup_limit', 'Insufficient private backup space. Existing encrypted evidence is retained.')
        identifier = uuid4().hex
        path = self._path(identifier)
        try:
            _write_new(path, raw)
            if read_bounded(path) != raw:
                raise OSError('Encrypted artifact readback failed')
        except BaseException:
            # Retain a failed stage if deletion cannot be confirmed; never hide it.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise OfflineError('backup_cleanup', 'An incomplete private encrypted backup could not be removed. Preserve the private backup directory for review.') from None
            raise
        artifact = BackupArtifact(identifier, hashlib.sha256(raw).hexdigest(), state.digest, len(raw))
        self._artifacts[identifier] = artifact
        return artifact

    def create(self, password, *, cancel=lambda: False, progress=lambda value: None):
        deadline = time.monotonic() + 600
        self._check(cancel, deadline)
        progress('Reading complete local state')
        state = capture_state(self.repository, cancel=cancel)
        return self._create_snapshot(state, password, cancel=cancel, progress=progress, deadline=deadline)

    def _create_snapshot(self, state, password, *, cancel=lambda: False, progress=lambda value: None, deadline=None):
        deadline = deadline or time.monotonic() + 600
        self._check(cancel, deadline)
        payload = encode_state(state.rows, platform='windows', sequence=state.sequence,
                               backup_id=str(uuid4()), created_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'), source_version='offline-development')
        progress('Encrypting complete backup')
        raw = seal_backup(payload, password, platform='windows')
        self._check(cancel, deadline)
        verified = decode_state(open_backup(raw, password, platform='windows'), platform='windows')
        if verified.digest != state.digest:
            raise OfflineError('backup_file', 'The encrypted backup did not match the complete snapshot.')
        self._check(cancel, deadline)
        artifact = self._retain(raw, state)
        self._check(cancel, deadline)
        return artifact

    def read_artifact(self, identifier):
        artifact = self._artifacts.get(identifier)
        if artifact is None:
            raise OfflineError('backup_file', 'The encrypted backup handle is unavailable.')
        raw = read_bounded(self._path(identifier))
        if hashlib.sha256(raw).hexdigest() != artifact.ciphertext_digest:
            raise OfflineError('backup_file', 'The private encrypted backup changed. Select the source again.')
        return raw

    def inspect(self, source, password, *, cancel=lambda: False):
        deadline = time.monotonic() + 600
        self._check(cancel, deadline)
        raw = read_bounded(source)
        self._check(cancel, deadline)
        state = decode_state(open_backup(raw, password, platform='windows'), platform='windows')
        self._check(cancel, deadline)
        current = capture_state(self.repository, cancel=cancel)
        self._check(cancel, deadline)
        artifact = self._retain(raw, state)
        self._check(cancel, deadline)
        return BackupPreview(artifact.id, state.digest, current.digest, state, current)

    def publish(self, identifier, destination, *, cancel=lambda: False):
        deadline = time.monotonic() + 600
        self._check(cancel, deadline)
        raw = self.read_artifact(identifier)
        target = Path(destination).absolute()
        name = target.name
        if (target.suffix.lower() != '.bhlibackup' or not target.parent.is_dir() or
                name.endswith((' ', '.')) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or
                re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I)):
            raise OfflineError('backup_file', 'Choose a new .bhlibackup filename in an existing folder.')
        if os.path.lexists(target):
            raise OfflineError('exists', 'Choose a new filename. The existing file was not replaced.')
        stage = target.parent / ('.bhli-backup-' + uuid4().hex + '.tmp')
        published = False
        verified = False
        failure = None
        cleanup = []
        try:
            self._check(cancel, deadline)
            _write_new(stage, raw)
            if read_bounded(stage) != raw:
                raise OSError('Encrypted stage readback failed')
            self._check(cancel, deadline)
            _move_new(stage, target)
            published = True
            if read_bounded(target) != raw:
                raise OSError('Published encrypted readback failed')
            verified = True
        except Exception as error:
            failure = error
        finally:
            for path in (stage, target) if published and not verified else (stage,):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    cleanup.append(str(path))
        warning = ('Owned incomplete encrypted output could not be removed: ' + ', '.join(cleanup)) if cleanup else ''
        if failure is not None:
            raise OfflineError(getattr(failure, 'code', 'backup_file'), 'The backup could not be saved and verified. The private encrypted copy is retained. ' + warning) from None
        return Publication(target, warning)
