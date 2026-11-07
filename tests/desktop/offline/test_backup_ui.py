from types import SimpleNamespace as NS

from desktop.offline.backup_ui import BackupController


class Worker:
    def submit(self, work, done, *, write=False):
        assert write
        self.work, self.done = work, done
        return True


def app():
    return NS(worker=Worker(), closing=False, mutation_pending=False, draft=None,
              _notice=lambda *args: None)


def test_password_confirmation_and_busy_admission():
    root = app()
    job = BackupController(root)
    assert not job.create('short', 'short', 'new.bhlibackup')
    assert not job.create('long enough password', 'different password', 'new.bhlibackup')
    assert job.create('long enough password', 'long enough password', 'new.bhlibackup')
    assert job.pending
    assert not job.inspect('source', 'long enough password')


def test_replacement_needs_prepared_ticket_and_explicit_confirmation():
    job = BackupController(app())
    assert not job.apply()
    job.phase, job.pending, job._ticket = 'prepared', True, 'opaque'
    assert not job.apply()
    assert not job.apply(confirmed=True)
    assert job.apply(confirmed=True, acknowledged=True)


def test_prepared_cancel_is_durable_and_retains_admission_until_drained():
    root = app()
    job = BackupController(root)
    job.phase, job.pending, job._ticket = 'prepared', True, 'opaque'
    job.cancel()
    assert job.pending
    root.worker.done(None, None)
    assert not job.pending and job._ticket is None


def test_late_cancel_does_not_hide_restored_or_unknown_outcome():
    for outcome in ('RESTORED', 'UNKNOWN'):
        root = app()
        calls = []
        root.backup_restored = lambda: calls.append('restored')
        root.backup_unknown = lambda message: calls.append('unknown')
        job = BackupController(root)
        job.phase, job.pending, job._ticket = 'prepared', True, 'opaque'
        assert job.apply(confirmed=True, acknowledged=True)
        job.cancel()
        root.worker.done(NS(outcome=outcome, message=outcome, cleanup_warning=''), None)
        assert calls == [outcome.lower()]
        assert job.blocked == (outcome == 'UNKNOWN')


def test_dirty_draft_and_missing_recovery_destination_refused():
    root = app()
    root.draft = NS(dirty=True)
    job = BackupController(root)
    assert not job.inspect('source', 'long enough password')
    job.phase, job.pending = 'preview', True
    assert not job.prepare('long enough password', '')


def test_shutdown_during_preparation_cancels_ticket_on_owner():
    root = app()
    job = BackupController(root)
    job.phase, job.pending, job.preview = 'preview', True, NS(id='preview')
    calls = []
    def prepare(*args, **kwargs):
        # Cancellation arrives after prepare minted its ticket, before return.
        job.shutdown()
        return 'ticket'
    owner = NS(prepare_restore=prepare, cancel_prepared=lambda ticket: calls.append(ticket))
    assert job.prepare('long enough password', 'recovery.bhlibackup')
    import pytest
    from desktop.offline.models import OfflineError
    with pytest.raises(OfflineError, match='cancelled'):
        root.worker.work(NS(_backup_store=owner))
    assert calls == ['ticket']


def test_owner_uses_startup_recovery_directory(tmp_path, monkeypatch):
    from desktop.offline import backup_jobs, backup_store
    from desktop.offline.backup_ui import _owner
    calls = []
    monkeypatch.setattr(backup_jobs, 'BackupJobs', lambda repo, path: calls.append(path) or NS(repository=repo))
    monkeypatch.setattr(backup_store, 'BackupStore', lambda jobs: NS(jobs=jobs))
    repo = NS(_path=tmp_path / 'audit.sqlite')
    assert _owner(repo) is _owner(repo)
    assert calls == [tmp_path / 'backup-recovery']


def test_shutdown_restored_preserves_outcome_without_refreshing_views():
    root = app()
    root.backup_restored = lambda: (_ for _ in ()).throw(AssertionError('closed view refreshed'))
    job = BackupController(root)
    job.phase, job.pending, job._ticket = 'prepared', True, 'ticket'
    assert job.apply(confirmed=True, acknowledged=True)
    root.closing = True
    root.worker.done(NS(outcome='RESTORED', message='Restored verified state.', cleanup_warning=''), None)
    assert 'Restored verified state' in str(root._shutdown_write_error)
    assert not job.pending


def test_cancelled_inspection_cannot_reappear_when_late_result_arrives():
    from desktop.offline.backup_ui import Preview
    root = app()
    job = BackupController(root)
    assert job.inspect('fictional.bhlibackup', 'long enough password')
    job.cancel()
    root.worker.done(Preview('opaque-preview', {}, {}, False), None)
    assert job.phase == 'cancelled' and not job.pending and job.preview is None


def test_rejected_replacement_retains_ticket_and_maintenance_admission():
    root = app()
    job = BackupController(root)
    job.phase, job.pending, job._ticket = 'prepared', True, 'opaque'
    root.worker.submit = lambda *a, **kw: False
    assert not job.apply(confirmed=True, acknowledged=True)
    assert job.phase == 'prepared' and job.pending and job._ticket == 'opaque'
    root.worker.submit = Worker().submit
    assert job.cancel()
