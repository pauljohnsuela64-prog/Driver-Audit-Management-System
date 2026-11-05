"""Offline draft and view adapters: no Tk interpreter or networking required."""
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

import pytest


def values(**changes):
    return dict(driver_name='Fictional Driver', helper_name='', audit_date='2026-11-05',
                station='Fictional Station', plate_number='TEST-001', remarks='') | changes


def test_query_mapping_preserves_filters_and_maps_creation_order():
    from desktop.models import AuditQuery
    from desktop.offline.presentation import local_filter
    query = AuditQuery(page=3, page_size=50, sort='id', driver_name='Driver',
                       plate_number='TEST', station='Station', date_from='2026-11-01',
                       date_to='2026-11-05', include_deleted=True)
    result = local_filter(query)
    assert (result.driver, result.plate, result.station, result.sort) == ('Driver', 'TEST', 'Station', 'created')
    assert (result.date_from, result.date_to, result.page, result.page_size, result.include_archived) == (
        '2026-11-01', '2026-11-05', 3, 50, True)


def test_unknown_create_retry_freezes_uuid_and_normalized_payload():
    from desktop.offline.presentation import OfflineDraft
    draft = OfflineDraft(values())
    identity, payload = draft.creation()
    draft.uncertain = True
    draft.values['driver_name'] = 'Changed after submit'
    retry_id, retry_payload = draft.creation()
    payload['driver_name'] = 'Mutated caller copy'
    assert retry_id == identity
    assert retry_payload['driver_name'] == 'Fictional Driver'
    assert draft.creation()[1]['driver_name'] == 'Fictional Driver'
    assert draft.dirty


def test_validation_failure_does_not_freeze_creation():
    from desktop.offline.models import OfflineError
    from desktop.offline.presentation import OfflineDraft
    draft = OfflineDraft(values(driver_name=''))
    with pytest.raises(OfflineError):
        draft.creation()
    assert draft.intent is None
    draft.values['driver_name'] = 'Repaired Fictional Driver'
    assert draft.creation()[1]['driver_name'] == 'Repaired Fictional Driver'


def test_snapshot_adapter_preserves_uuid_and_archived_revision():
    from desktop.offline.presentation import present_audit
    stamp = datetime(2026, 11, 5, tzinfo=timezone.utc)
    record = SimpleNamespace(id='891af727-919c-42f0-841d-dc3262c586d5', revision=4,
                             archived_at=stamp, created_at=stamp, updated_at=stamp,
                             audited_by_name='Original Fictional Auditor', **values())
    view = present_audit(record)
    assert view.id == '891af727-919c-42f0-841d-dc3262c586d5'
    assert view.version == 4 and view.deleted_at == stamp
    assert view.audited_by_name == 'Original Fictional Auditor'
    assert view.driver_name == 'Fictional Driver'


def test_close_error_published_after_drain_is_shown_before_destroying_ui():
    from desktop.offline.app import OfflineApplication
    from desktop.offline.models import OfflineError
    stopped = Event()
    outcome = []
    # The worker can finish immediately after drain's stopped/error check.
    worker = SimpleNamespace(drain=stopped.set, stopped=stopped,
                             close_error=OfflineError('storage', 'Storage did not close cleanly.'))
    controller = SimpleNamespace(worker=worker, collector=SimpleNamespace(poll=lambda: None),
        closing=True, closed=False, _close_warning=False, _retry_bootstrap=False,
        _shutdown_write_error=None,
        _show_close_error=lambda error: outcome.append(('warning', error.code)),
        after=lambda *args: None, poll=lambda: None)
    controller._finish_close = lambda: OfflineApplication._finish_close(controller)
    OfflineApplication.poll(controller)
    assert outcome == [('warning', 'storage')]


def test_admitted_write_failure_is_retained_when_close_was_requested():
    from desktop.offline.app import OfflineApplication
    from desktop.offline.models import OfflineError
    callbacks = []
    worker = SimpleNamespace(submit=lambda work, done, **options: callbacks.append(done) or True)
    controller = SimpleNamespace(worker=worker, closing=False, mutation_pending=False)
    OfflineApplication.mutate(controller, lambda repo: None, lambda result, error: None)
    controller.closing = True
    callbacks[0](None, OfflineError('storage', 'Local operation failed.'))
    retained = getattr(controller, '_shutdown_write_error', None)
    assert retained is not None and retained.code == 'storage'


def test_final_drain_write_failure_requires_acknowledgment_even_when_database_closed(monkeypatch):
    from desktop.offline import app as module
    from desktop.offline.models import OfflineError
    stopped = Event()
    stopped.set()
    outcome = []
    controller = SimpleNamespace(closed=False, _close_warning=False, _poll_timer=None,
        worker=SimpleNamespace(stopped=stopped, drain=lambda: None, close_error=None),
        collector=SimpleNamespace(close=lambda: outcome.append('collected')),
        _shutdown_write_error=OfflineError('storage', 'Submitted change not confirmed.'),
        _show_close_error=lambda error: outcome.append('warning'))
    monkeypatch.setattr(module, 'destroy_view', lambda target: outcome.append('destroyed'))
    module.OfflineApplication._finish_close(controller)
    assert outcome == ['warning'] and not controller.closed
