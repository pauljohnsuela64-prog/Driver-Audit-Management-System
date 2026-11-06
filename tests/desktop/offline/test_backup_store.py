"""Restore behavior uses complete fictional real SQLite files, never live data."""
import json
import sqlite3
import time

import pytest

from desktop.offline.backup_crypto import open_backup
from desktop.offline.backup_state import capture_state, decode_state
from desktop.offline.models import OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository
from desktop.offline.store_lease import StoreLease

PASSWORD = 'fictional unique passphrase 123'
VALUES = dict(driver_name='Fictional Driver', helper_name=None, audit_date='2026-11-06', station='Test', plate_number='00123', remarks='Full history')


@pytest.fixture
def setup_store(tmp_path):
    from desktop.offline.backup_jobs import BackupJobs
    from desktop.offline.backup_store import BackupStore
    lease = StoreLease.acquire(tmp_path)
    repo = SqliteRepository(tmp_path / 'fictional.db', lease=lease)
    repo.save_profile('Incoming fictional auditor')
    audit = repo.create(new_uuid(), VALUES)
    repo.update(audit.id, 1, dict(VALUES, remarks='Changed'))
    repo.archive(audit.id, 2)
    repo._connection.execute('INSERT INTO transfer_receipts VALUES (?,?,?,?,?)', (new_uuid(), 'a'*64, new_uuid(), '2026-11-06T00:00:00.000000Z', 1))
    repo._connection.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='audit_records'")
    jobs = BackupJobs(repo, tmp_path / 'private')
    artifact = jobs.create(PASSWORD)
    source = tmp_path / 'incoming.bhlibackup'
    jobs.publish(artifact.id, source)
    incoming = capture_state(repo)
    repo.save_profile('Current fictional auditor')
    current = capture_state(repo)
    store = BackupStore(jobs)
    yield repo, jobs, store, source, incoming, current
    repo.close()


@pytest.mark.parametrize('journal', ['delete', 'wal'])
def test_preparation_protects_current_before_ticket_and_restore_replaces_exact_state(setup_store, tmp_path, journal):
    repo, jobs, store, source, incoming, current = setup_store
    repo._connection.execute('PRAGMA journal_mode='+journal)
    preview = store.inspect_restore(source, PASSWORD)
    recovery = tmp_path / 'current-recovery.bhlibackup'
    ticket = store.prepare_restore(preview.id, PASSWORD, recovery)
    protected = decode_state(open_backup(recovery.read_bytes(), PASSWORD, platform='windows'), platform='windows')
    assert protected.rows == current.rows and protected.digest == current.digest
    with pytest.raises(OfflineError):
        repo.save_profile('Must not race maintenance')
    result = store.apply_restore(ticket)
    assert result.outcome == 'RESTORED'
    restored = capture_state(repo)
    assert restored.rows == incoming.rows and restored.sequence == 90
    assert restored.rows['local_profile'][0]['name'] == 'Incoming fictional auditor'
    assert len(restored.rows['audit_events']) == 3 and len(restored.rows['transfer_receipts']) == 1
    assert repo._connection.execute('PRAGMA user_version').fetchone()[0] == 2
    assert repo._connection.execute('PRAGMA journal_mode').fetchone()[0] == journal
    assert recovery.exists()
    with pytest.raises(OfflineError):
        store.apply_restore(ticket)


def test_failed_recovery_readback_never_yields_ticket_or_replaces_current(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_jobs
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    recovery = tmp_path / 'recovery.bhlibackup'
    original = backup_jobs.read_bounded
    def refused(path):
        if path == recovery:
            raise OSError('fictional readback refusal')
        return original(path)
    monkeypatch.setattr(backup_jobs, 'read_bounded', refused)
    with pytest.raises(OfflineError):
        store.prepare_restore(preview.id, PASSWORD, recovery)
    assert capture_state(repo).rows == current.rows
    assert not (jobs.directory / 'restore-pending.json').exists()
    with pytest.raises(OfflineError):
        store.apply_restore('fabricated-ui-verified-ticket')


def test_equal_count_external_change_after_preparation_invalidates_ticket(setup_store, tmp_path):
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    with sqlite3.connect(repo._path) as other:
        other.execute("UPDATE local_profile SET name='External fictional writer'")
    result = store.apply_restore(ticket)
    assert result.outcome == 'UNKNOWN'
    with pytest.raises(OfflineError):
        repo.save_profile('Blocked after unknown')
    assert repo._connection.execute('SELECT name FROM local_profile').fetchone()[0] == 'External fictional writer'


@pytest.mark.parametrize('lost_ack', [False, True])
def test_commit_failure_classifies_actual_state_without_retry(setup_store, tmp_path, monkeypatch, lost_ack):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    def failed(db):
        if lost_ack:
            db.commit()
        raise sqlite3.OperationalError('fictional COMMIT acknowledgement failure')
    monkeypatch.setattr(backup_store, '_commit', failed)
    result = store.apply_restore(ticket)
    assert result.outcome == ('RESTORED' if lost_ack else 'ORIGINAL')
    assert capture_state(repo).rows == (incoming.rows if lost_ack else current.rows)


def test_partial_table_failure_rolls_back_every_owned_row_and_sequence(setup_store, tmp_path):
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    def deny(action, table, column, database, trigger):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and table == 'audit_records' else sqlite3.SQLITE_OK
    repo._connection.set_authorizer(deny)
    result = store.apply_restore(ticket)
    assert result.outcome == 'ORIGINAL'
    assert capture_state(repo).rows == current.rows


def test_startup_reconciles_pending_marker_and_missing_evidence_blocks_writes(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    monkeypatch.setattr(backup_store, '_resolve_marker', lambda directory, marker: 'marker retained for fictional restart')
    result = store.apply_restore(ticket)
    assert result.outcome == 'RESTORED'
    with pytest.raises(OfflineError):
        repo.save_profile('Blocked until marker can be archived')
    marker_path = jobs.directory / 'restore-pending.json'
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    assert marker_path.stat().st_size <= 4096
    assert PASSWORD not in marker_path.read_text(encoding='utf-8')
    assert backup_store.reconcile_startup(repo, jobs.directory).outcome == 'RESTORED'
    (jobs.directory / marker['recovery_file']).unlink()
    assert backup_store.reconcile_startup(repo, jobs.directory).outcome == 'UNKNOWN'
    with pytest.raises(OfflineError):
        repo.save_profile('Must stay blocked')


@pytest.mark.parametrize('existing', [False, True])
def test_bootstrap_guard_never_creates_or_initializes_missing_or_empty_current(tmp_path, existing):
    from desktop.offline.backup_store import bootstrap_check
    directory = tmp_path / 'backup-recovery'
    directory.mkdir()
    (directory / 'restore-pending.json').write_bytes(b'{}\n')
    path = tmp_path / 'fictional.db'
    if existing:
        path.touch()
    with pytest.raises(OfflineError):
        bootstrap_check(path, directory)
    assert path.exists() is existing
    if existing:
        assert path.read_bytes() == b''


@pytest.mark.parametrize('raw', [b'{}\n', b'x'*4097, b'{"input_file":"../outside"}\n'])
def test_bootstrap_guard_rejects_invalid_marker_without_touching_current(tmp_path, raw):
    from desktop.offline.backup_store import bootstrap_check
    directory = tmp_path / 'backup-recovery'
    directory.mkdir()
    (directory / 'restore-pending.json').write_bytes(raw)
    path = tmp_path / 'fictional.db'
    path.write_bytes(b'fictional original bytes')
    with pytest.raises(OfflineError):
        bootstrap_check(path, directory)
    assert path.read_bytes() == b'fictional original bytes'


def test_changed_private_evidence_before_apply_releases_maintenance_without_writes(setup_store, tmp_path):
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    candidate = next(item for item in jobs._artifacts.values() if item.state_digest == incoming.digest)
    # Inspection retained another encrypted copy; tamper all incoming copies.
    for artifact in jobs._artifacts.values():
        if artifact.state_digest == incoming.digest:
            jobs._path(artifact.id).write_bytes(b'changed')
    with pytest.raises(OfflineError):
        store.apply_restore(ticket)
    assert capture_state(repo).rows == current.rows
    assert repo._maintenance is None


def test_failed_durable_marker_publication_prevents_any_replacement(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    move = backup_store._move_new
    def refused(source, target):
        if target.name == backup_store.MARKER:
            raise OSError('fictional durable marker publication failure')
        return move(source, target)
    monkeypatch.setattr(backup_store, '_move_new', refused)
    with pytest.raises(OSError):
        store.apply_restore(ticket)
    assert capture_state(repo).rows == current.rows


def test_restore_requires_lifetime_owner_and_cancel_preserves_recovery(setup_store, tmp_path):
    from desktop.offline.backup_jobs import BackupJobs
    from desktop.offline.backup_store import BackupStore
    repo, jobs, store, source, incoming, current = setup_store
    direct = SqliteRepository(tmp_path / 'low-level-fixture.db')
    try:
        with pytest.raises(OfflineError):
            BackupStore(BackupJobs(direct, tmp_path / 'direct-private')).inspect_restore(source, PASSWORD)
    finally:
        direct.close()
    preview = store.inspect_restore(source, PASSWORD)
    recovery = tmp_path / 'recovery.bhlibackup'
    ticket = store.prepare_restore(preview.id, PASSWORD, recovery)
    store.cancel_prepared(ticket)
    assert capture_state(repo).rows == current.rows and recovery.exists()
    with pytest.raises(OfflineError):
        store.apply_restore(ticket)


@pytest.mark.parametrize('table', ['app_meta', 'auditor_identities', 'local_profile', 'audit_records', 'audit_events', 'transfer_receipts', 'sqlite_sequence'])
def test_each_dependent_table_write_failure_preserves_complete_original(setup_store, tmp_path, table):
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    def deny(action, target, column, database, trigger):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and target == table else sqlite3.SQLITE_OK
    repo._connection.set_authorizer(deny)
    result = store.apply_restore(ticket)
    assert result.outcome == 'ORIGINAL'
    assert capture_state(repo).rows == current.rows and capture_state(repo).sequence == current.sequence


def test_cancel_before_commit_rolls_back_and_cancel_after_commit_is_truthful(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'first-recovery.bhlibackup')
    assert store.apply_restore(ticket, cancel=lambda: True).outcome == 'ORIGINAL'
    assert capture_state(repo).rows == current.rows
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'second-recovery.bhlibackup')
    cancelled = False
    def committed(db):
        nonlocal cancelled
        db.commit()
        cancelled = True
    monkeypatch.setattr(backup_store, '_commit', committed)
    assert store.apply_restore(ticket, cancel=lambda: cancelled).outcome == 'RESTORED'
    assert capture_state(repo).rows == incoming.rows


def test_empty_backup_replaces_identity_and_removes_sequence_then_allows_fresh_creation(setup_store, tmp_path):
    from desktop.offline.backup_jobs import BackupJobs
    repo, jobs, store, source, incoming, current = setup_store
    empty = SqliteRepository(tmp_path / 'empty.db')
    try:
        empty_state = capture_state(empty)
        empty_jobs = BackupJobs(empty, tmp_path / 'empty-private')
        artifact = empty_jobs.create(PASSWORD)
        source = tmp_path / 'empty.bhlibackup'
        empty_jobs.publish(artifact.id, source)
    finally:
        empty.close()
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    assert store.apply_restore(ticket).outcome == 'RESTORED'
    restored = capture_state(repo)
    assert restored.rows == empty_state.rows and restored.sequence is None
    assert not restored.rows['local_profile'] and restored.rows['app_meta'] != current.rows['app_meta']
    repo.save_profile('Fresh fictional auditor')
    repo.create(new_uuid(), VALUES)
    assert capture_state(repo).sequence == 1


def test_marker_archival_retry_unblocks_known_restored_store(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    resolve = backup_store._resolve_marker
    monkeypatch.setattr(backup_store, '_resolve_marker', lambda directory, marker: 'fictional archive refusal')
    assert store.apply_restore(ticket).outcome == 'RESTORED'
    assert repo._recovery_pending and not repo._write_blocked
    with pytest.raises(OfflineError):
        repo.save_profile('Must wait for marker archival')
    monkeypatch.setattr(backup_store, '_resolve_marker', resolve)
    assert backup_store.reconcile_startup(repo, jobs.directory).outcome == 'RESTORED'
    repo.save_profile('Fictional write after archive retry')
    assert not repo._recovery_pending


def test_prepare_timeout_spans_recovery_generation_and_publication_without_ticket(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    clock = [0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    generate = jobs._create_snapshot
    publish = jobs.publish
    def slow_generate(*args, **kwargs):
        result = generate(*args, **kwargs)
        clock[0] += 350
        return result
    def slow_publish(*args, **kwargs):
        result = publish(*args, **kwargs)
        clock[0] += 350
        return result
    monkeypatch.setattr(jobs, '_create_snapshot', slow_generate)
    monkeypatch.setattr(jobs, 'publish', slow_publish)
    with pytest.raises(OfflineError) as error:
        store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    assert error.value.code == 'restore_timeout'
    assert not store._tickets and repo._maintenance is None
    assert capture_state(repo).rows == current.rows


def test_apply_timeout_during_inserts_rolls_back_before_commit(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    clock = [0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    def trace(sql):
        if sql.startswith('INSERT INTO audit_records '):
            clock[0] = 601
    repo._connection.set_trace_callback(trace)
    commit_calls = []
    def must_not_commit(db):
        commit_calls.append(True)
        db.commit()
    monkeypatch.setattr(backup_store, '_commit', must_not_commit)
    assert store.apply_restore(ticket).outcome == 'ORIGINAL'
    assert clock[0] == 601 and not commit_calls
    assert capture_state(repo).rows == current.rows


def test_new_apply_deadline_excludes_human_confirmation_wait(setup_store, tmp_path, monkeypatch):
    from desktop.offline import backup_store
    repo, jobs, store, source, incoming, current = setup_store
    clock = [0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    preview = store.inspect_restore(source, PASSWORD)
    ticket = store.prepare_restore(preview.id, PASSWORD, tmp_path / 'recovery.bhlibackup')
    clock[0] = 3600
    assert store.apply_restore(ticket).outcome == 'RESTORED'
    assert capture_state(repo).rows == incoming.rows


def test_restore_keeps_only_one_preview_and_cancel_releases_it(setup_store):
    repo, jobs, store, source, incoming, current = setup_store
    first = store.inspect_restore(source, PASSWORD)
    second = store.inspect_restore(source, PASSWORD)
    assert set(store._previews) == {second.id}
    store.cancel_preview(second.id)
    assert not store._previews
    repo.save_profile('Incoming fictional auditor')
    unchanged = store.inspect_restore(source, PASSWORD)
    assert unchanged.unchanged and not store._previews
