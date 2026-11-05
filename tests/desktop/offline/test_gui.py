"""Opt-in Windows offline acceptance using one interpreter and fictional temp data."""
import os
import socket
import sys
import time
from dataclasses import replace
from threading import Event

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
    reason='Native Windows GUI requires DAMS_DESKTOP_GUI_TESTS=1')


def pump(app, predicate=lambda: True, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), 'Offline interface did not reach expected state'


def fill(screen, **changes):
    data = dict(driver_name='Fictional Offline Driver', helper_name='Fictional Helper',
                audit_date='2026-11-05', station='Fictional Station',
                plate_number='TEST-6C', remarks='Fictional development record') | changes
    for key, value in data.items():
        widget = screen.inputs[key]
        start = '1.0' if key == 'remarks' else 0
        widget.delete(start, 'end')
        widget.insert(start, value)


@pytest.fixture(scope='module')
def offline_app(tmp_path_factory):
    from desktop.offline.app import OfflineApplication
    from desktop.offline.models import OfflineError
    from desktop.offline.repository import SqliteRepository
    from desktop.offline.worker import DatabaseWorker
    faults = dict(list=False, unknown_create=False, block=None, bootstrap=True, close=False,
                  shutdown_write=False,
                  read_block=None, read_started=Event())
    class Repository(SqliteRepository):
        def list(self, query):
            if faults['list']:
                raise OfflineError('storage', 'Local records could not be read. Retry Refresh.')
            return super().list(query)

        def create(self, identity, values):
            gate = faults['block']
            if gate is not None:
                gate.wait(6)
            result = super().create(identity, values)
            if faults['unknown_create']:
                faults['unknown_create'] = False
                raise OfflineError('storage', 'Save outcome could not be confirmed.')
            if faults['shutdown_write']:
                raise OfflineError('storage', 'Fictional unconfirmed write outcome.')
            return result

        def read(self, identity):
            gate = faults['read_block']
            if gate is not None:
                faults['read_started'].set()
                gate.wait(6)
            return super().read(identity)

        def close(self):
            super().close()
            if faults['close']:
                raise OfflineError('storage', 'Fictional shutdown storage failure.')

    def make_repository():
        if faults['bootstrap']:
            faults['bootstrap'] = False
            raise OfflineError('storage', 'Fictional startup storage failure. Retry.')
        return Repository(path)
    patch = pytest.MonkeyPatch()
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline application attempted network access')
    patch.setattr(socket.socket, 'connect', forbidden)
    patch.setattr(socket, 'create_connection', forbidden)
    path = tmp_path_factory.mktemp('offline-native') / 'fictional.db'
    app = OfflineApplication(db_path=path,
        worker_factory=lambda factory: DatabaseWorker(make_repository))
    app.faults = faults
    app.callback_errors = []
    app.tk.createcommand('offline_test_bgerror', lambda message: app.callback_errors.append(message))
    app.tk.eval('proc bgerror {message} {offline_test_bgerror $message}')
    app.report_callback_exception = lambda exc, value, tb: app.callback_errors.append((exc.__name__, str(value)))
    pump(app, lambda: app.worker.stopped.is_set())
    failed_worker = app.worker
    assert app.profile is None and app.shell is None
    assert not path.exists()
    app.retry_bootstrap()
    assert failed_worker.stopped.is_set() and app.worker is not failed_worker
    pump(app, lambda: getattr(app.screen, 'name', None) is not None)
    assert app.profile is None
    assert app.screen.name.get() == ''
    app.screen.name.insert(0, 'Fictional Local Auditor')
    app.screen.save()
    pump(app, lambda: app.destination == 'Dashboard' and app.screen.loaded)
    assert app.screen.total == 0
    yield app
    faults['block'] = None
    if not app.closed:
        app.close(force=True)
        pump(app, lambda: app.closed)
    assert app.worker.stopped.is_set()
    app.worker.join(1)
    assert app.collector.closed
    assert app.callback_errors == []
    patch.undo()


def test_fictional_workflow_uuid_history_profile_and_layout(offline_app):
    app = offline_app
    assert tuple(app.shell.nav_buttons) == ('Dashboard', 'Driver Audits', 'Local profile')
    app.open_create()
    app.screen.save()
    assert app.draft.errors and app.draft.intent is None
    fill(app.screen)
    app.set_theme('Dark')
    app.geometry('800x600')
    pump(app)
    assert app.screen._columns == 1
    assert app.screen.inputs['driver_name'].get() == 'Fictional Offline Driver'
    app.screen.save()
    pump(app, lambda: app.destination == 'Driver Audits' and app.screen.loaded)
    identity = app.selected_id
    assert isinstance(identity, str) and len(identity) == 36
    assert app.screen.table.selected() == identity
    app.screen.open_selected()
    pump(app, lambda: app.screen.loaded)
    assert app.screen.record.audited_by_name == 'Fictional Local Auditor'
    app.navigate('Local profile')
    app.screen.name.delete(0, 'end')
    app.screen.name.insert(0, 'Renamed Fictional Auditor')
    app.screen.save()
    pump(app, lambda: app.profile.name == 'Renamed Fictional Auditor')
    app.navigate('Audit Details', identity)
    pump(app, lambda: app.screen.loaded)
    assert app.screen.record.audited_by_name == 'Fictional Local Auditor'
    app.open_edit(app.screen.record)
    pump(app, lambda: app.destination == 'Edit Audit')
    fill(app.screen, remarks='Edited fictional record')
    app.screen.save()
    pump(app, lambda: app.destination == 'Driver Audits' and app.screen.loaded)
    app.navigate('Audit History', identity)
    pump(app, lambda: app.screen.loaded)
    assert [event.actor_name for event in app.screen.events.items] == [
        'Renamed Fictional Auditor', 'Fictional Local Auditor']
    assert app.screen.events.items[-1].after.audited_by_name == 'Fictional Local Auditor'
    app.test_record_id = identity
    app.set_theme('Light')


def test_unknown_retry_refresh_failure_and_explicit_revision_review(offline_app):
    app = offline_app
    app.query = replace(app.query, driver_name='Fictional', page=3)
    app.open_create()
    fill(app.screen, driver_name='Fictional Retry Driver', plate_number='TEST-RETRY')
    app.faults['unknown_create'] = True
    app.screen.save()
    pump(app, lambda: app.draft is not None and app.draft.uncertain)
    identity = app.draft.intent.key
    assert app.screen.inputs['driver_name'].cget('state') == 'disabled'
    app.faults['list'] = True
    app.screen.save()
    pump(app, lambda: app.destination == 'Driver Audits' and app.screen.last_error is not None)
    assert app.draft is None and app.selected_id == identity
    assert app.query.driver_name == 'Fictional' and app.query.page == 1
    assert 'saved' in app.shell.notice.cget('text').lower()
    app.faults['list'] = False
    app.screen.refresh()
    pump(app, lambda: app.screen.loaded)
    assert app.screen.total == 2
    app.navigate('Audit Details', identity)
    pump(app, lambda: app.screen.loaded)
    app.open_edit(app.screen.record)
    pump(app, lambda: app.destination == 'Edit Audit')
    fill(app.screen, driver_name='Fictional Retry Driver', remarks='My conflict draft')
    baseline = app.draft.baseline
    complete = []
    changed = {key: getattr(baseline, key) for key in app.draft.values}
    changed['station'] = 'Changed Fictional Station'
    app.worker.submit(lambda repo: repo.update(identity, baseline.revision, changed),
                      lambda result, error: complete.append((result, error)), write=True)
    pump(app, lambda: bool(complete))
    assert complete[0][1] is None
    app.screen.save()
    pump(app, lambda: app.draft is not None and not app.draft.pending)
    assert app.draft.uncertain
    app.screen.fetch_latest()
    pump(app, lambda: app.draft.latest is not None)
    assert app.draft.values['remarks'] == 'My conflict draft'
    app.screen.reload_latest()
    assert app.draft.values['station'] == 'Changed Fictional Station'
    assert app.draft.values['remarks'] != 'My conflict draft'
    app.navigate('Driver Audits')
    pump(app, lambda: app.screen.loaded)
    app.navigate('Audit Details', identity)
    pump(app, lambda: app.screen.loaded)
    app.confirm_archive(app.screen.record)
    pump(app, lambda: app.dialog is not None)
    app.dialog.accept()
    pump(app, lambda: app.destination == 'Driver Audits' and app.screen.loaded)
    assert app.screen.total == 1
    app.screen.include_deleted.select()
    app.screen.apply()
    pump(app, lambda: app.screen.loaded)
    assert app.screen.total == 2
    assert app.screen.table.tree.item(identity, 'values')[1].startswith('[Archived] ')
    app.navigate('Audit Details', identity)
    pump(app, lambda: app.screen.loaded)
    assert app.screen.record.deleted_at is not None


def test_navigation_drops_callbacks_for_destroyed_views(offline_app):
    app = offline_app
    gate = Event()
    app.faults['read_block'] = gate
    app.navigate('Audit Details', app.test_record_id)
    old_screen = app.screen
    pump(app, lambda: app.faults['read_started'].is_set())
    app.navigate('Dashboard')
    gate.set()
    app.faults['read_block'] = None
    pump(app, lambda: app.screen.loaded)
    assert app.destination == 'Dashboard' and not old_screen.winfo_exists()
    assert app.callback_errors == []


def test_dirty_cancel_and_close_waits_for_admitted_write(offline_app):
    app = offline_app
    app.open_create()
    fill(app.screen, driver_name='Fictional Closing Driver')
    app.navigate('Dashboard')
    assert app.dialog is not None
    app.dialog.cancel()
    assert app.destination == 'Create Audit'
    gate = Event()
    app.faults['block'] = gate
    app.screen.save()
    assert app.mutation_pending
    app.navigate('Dashboard')
    assert app.destination == 'Create Audit'
    app.faults['close'] = os.getenv('DAMS_OFFLINE_CLOSE_FAILURE') == '1'
    app.faults['shutdown_write'] = not app.faults['close']
    app.close()
    assert app.closing and not app.closed
    app.update()
    assert not app.worker.stopped.is_set()
    gate.set()
    pump(app, lambda: app._close_warning)
    assert not app.closed and app.worker.stopped.is_set()
    if app.faults['shutdown_write']:
        assert app.worker.close_error is None
        assert app._shutdown_write_error is not None
        assert 'not confirmed' in app._shutdown_write_error.message
    acknowledgment = app.screen.winfo_children()[-1]
    assert acknowledgment.cget('text') == 'Close application'
    acknowledgment.invoke()
    pump(app, lambda: app.closed)
    assert app.worker.stopped.is_set()
    from desktop.offline.repository import SqliteRepository
    with_repository = SqliteRepository(app.db_path)
    try:
        from desktop.offline.models import AuditFilter
        assert with_repository.list(AuditFilter(driver='Fictional Closing Driver')).total == 1
    finally:
        with_repository.close()
