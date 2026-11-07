"""Backup file tests use fictional SQLite and private temporary destinations."""
import pytest

from desktop.offline.backup_state import capture_state, decode_state
from desktop.offline.backup_crypto import open_backup
from desktop.offline.models import OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository

PASSWORD = 'fictional unique passphrase 123'
VALUES = dict(driver_name='Fictional Driver', helper_name=None, audit_date='2026-11-06', station='Test', plate_number='00123', remarks='Archive retained')


def test_create_all_state_verified_artifact_and_new_only_publication(tmp_path):
    from desktop.offline.backup_jobs import BackupJobs
    repo = SqliteRepository(tmp_path / 'fictional.db')
    repo.save_profile('Fictional Auditor')
    record = repo.create(new_uuid(), VALUES)
    repo.archive(record.id, 1)
    jobs = BackupJobs(repo, tmp_path / 'private')
    artifact = jobs.create(PASSWORD)
    target = tmp_path / 'complete.bhlibackup'
    result = jobs.publish(artifact.id, target)
    decoded = decode_state(open_backup(target.read_bytes(), PASSWORD, platform='windows'), platform='windows')
    assert decoded.rows == capture_state(repo).rows
    assert decoded.rows['audit_records'][0]['archived_at'] is not None
    assert result.path == target and not result.cleanup_warning
    before = target.read_bytes()
    with pytest.raises(OfflineError):
        jobs.publish(artifact.id, target)
    assert target.read_bytes() == before
    assert jobs.read_artifact(artifact.id) == before
    assert PASSWORD not in repr(artifact)
    repo.close()


def test_cancellation_and_failed_readback_do_not_advertise_output(tmp_path, monkeypatch):
    from desktop.offline import backup_jobs
    repo = SqliteRepository(tmp_path / 'fictional.db')
    jobs = backup_jobs.BackupJobs(repo, tmp_path / 'private')
    with pytest.raises(OfflineError):
        jobs.create(PASSWORD, cancel=lambda: True)
    artifact = jobs.create(PASSWORD)
    target = tmp_path / 'failed.bhlibackup'
    original = backup_jobs.read_bounded
    def broken(path):
        if path == target:
            raise OSError('fictional readback refusal')
        return original(path)
    monkeypatch.setattr(backup_jobs, 'read_bounded', broken)
    with pytest.raises(OfflineError):
        jobs.publish(artifact.id, target)
    assert not target.exists()
    assert jobs.read_artifact(artifact.id).startswith(b'BHLIBAK\0')
    repo.close()


def test_inspect_freezes_source_and_never_trusts_changed_artifact(tmp_path):
    from desktop.offline.backup_jobs import BackupJobs
    repo = SqliteRepository(tmp_path / 'fictional.db')
    jobs = BackupJobs(repo, tmp_path / 'private')
    artifact = jobs.create(PASSWORD)
    source = tmp_path / 'selected.bhlibackup'
    jobs.publish(artifact.id, source)
    preview = jobs.inspect(source, PASSWORD)
    source.write_bytes(b'changed selected source')
    assert preview.candidate_digest == artifact.state_digest
    assert jobs.read_artifact(preview.artifact_id).startswith(b'BHLIBAK\0')
    with pytest.raises(OfflineError):
        jobs.inspect(source, PASSWORD)
    repo.close()


def test_publication_timeout_has_one_deadline_across_file_phases(tmp_path, monkeypatch):
    from desktop.offline import backup_jobs
    repo = SqliteRepository(tmp_path / 'fictional.db')
    jobs = backup_jobs.BackupJobs(repo, tmp_path / 'private')
    artifact = jobs.create(PASSWORD)
    clock = [0]
    monkeypatch.setattr(backup_jobs.time, 'monotonic', lambda: clock[0])
    write = backup_jobs._write_new
    def slow_write(path, raw):
        write(path, raw)
        clock[0] = 601
    monkeypatch.setattr(backup_jobs, '_write_new', slow_write)
    target = tmp_path / 'timeout.bhlibackup'
    with pytest.raises(OfflineError):
        jobs.publish(artifact.id, target)
    assert not target.exists()
    assert jobs.read_artifact(artifact.id)
    repo.close()


def test_private_workspace_budget_refuses_growth_and_preserves_existing_evidence(tmp_path, monkeypatch):
    from desktop.offline import backup_jobs
    repo = SqliteRepository(tmp_path / 'fictional.db')
    jobs = backup_jobs.BackupJobs(repo, tmp_path / 'private')
    artifact = jobs.create(PASSWORD)
    existing = jobs.read_artifact(artifact.id)
    monkeypatch.setattr(backup_jobs, 'MAX_WORKSPACE', len(existing), raising=False)
    with pytest.raises(OfflineError):
        jobs.create(PASSWORD)
    assert jobs.read_artifact(artifact.id) == existing
    repo.close()
