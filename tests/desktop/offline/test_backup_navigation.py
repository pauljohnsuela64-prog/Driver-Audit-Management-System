"""Post-restore callbacks cannot display the previous database's drafts/state."""
from types import SimpleNamespace

from desktop.models import AuditQuery
from desktop.offline.app import OfflineApplication


def test_restored_state_invalidates_old_reads_and_drafts_before_profile_reload(monkeypatch):
    import desktop.offline.app as module
    events = []
    monkeypatch.setattr(module, 'destroy_view', lambda view: events.append('destroy'))
    monkeypatch.setattr(module, 'StatePanel', lambda *a, **k: 'loading-panel')
    root = SimpleNamespace(
        closing=False, _generation=7, draft=object(), selected_id='old',
        query=AuditQuery(page=4), profile=object(), shell=object(), screen=object(),
        worker=SimpleNamespace(invalidate_reads=lambda: events.append('invalidate')),
        _replace_root_view=lambda view: events.append(view),
        request=lambda work, done, **kw: events.append(('reload', done)),
        _bootstrapped=lambda result, error: events.append(('profile', result, error)),
    )
    OfflineApplication.backup_restored(root)
    assert root.draft is None and root.selected_id is None and root.profile is None
    assert root._generation == 8 and root.query.page == 1
    assert events[:3] == ['invalidate', 'destroy', 'loading-panel']
    events[-1][1]('fresh-profile', None)
    assert events[-1] == ('profile', ('fresh-profile', None), None)


def test_shutdown_never_refreshes_ui_after_restored_callback():
    root = SimpleNamespace(closing=True)
    OfflineApplication.backup_restored(root)


def test_shutdown_drains_backup_cancellation_before_stopping_worker():
    events = []
    job = SimpleNamespace(pending=True, shutdown=lambda: events.append('cancel'))
    root = SimpleNamespace(closing=True, backup_job=job,
                           worker=SimpleNamespace(close=lambda: events.append('close')))
    OfflineApplication._close_worker_when_ready(root)
    assert events == ['cancel']
    job.pending = False
    OfflineApplication._close_worker_when_ready(root)
    assert events == ['cancel', 'close']


def test_unknown_outcome_closes_admission_and_preserves_assisted_guidance(monkeypatch):
    import desktop.offline.app as module
    events = []
    monkeypatch.setattr(module, 'destroy_view', lambda view: events.append('destroy'))
    monkeypatch.setattr(module, 'StatePanel', lambda *a, **k: events.append(a) or 'guidance')
    root = SimpleNamespace(
        closing=False, _generation=3, draft=object(), profile=object(),
        selected_id='old', shell=object(), screen=object(),
        worker=SimpleNamespace(invalidate_reads=lambda: events.append('invalidate'),
                               close=lambda: events.append('close')),
        retry_bootstrap=lambda: None, _replace_root_view=lambda view: events.append(view),
    )
    OfflineApplication.backup_unknown(root, 'Keep originals. Use a fresh OS user.')
    assert root.recovery_blocked and root.profile is None and root.draft is None
    assert root.selected_id is None and root._generation == 4
    assert 'close' in events and events[-1] == 'guidance'
    assert any(isinstance(value, tuple) and 'Keep originals' in str(value) for value in events)
