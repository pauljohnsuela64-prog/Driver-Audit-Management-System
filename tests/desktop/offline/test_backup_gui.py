"""Native acceptance uses only fresh fictional stores and programmatic widgets."""
import os
from pathlib import Path
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
    reason='Native Windows GUI requires DAMS_DESKTOP_GUI_TESTS=1',
)


def pump(app, predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), 'Fictional backup acceptance did not reach its expected state'


def call(app, operation):
    received = []
    assert app.worker.submit(operation, lambda result, error: received.append((result, error)), write=True)
    pump(app, lambda: bool(received))
    result, error = received[0]
    assert error is None, str(error)
    return result


def test_native_full_backup_preview_cancel_restore_and_restart(tmp_path, monkeypatch):
    from tkinter import filedialog, messagebox
    from desktop.offline.app import OfflineApplication
    from desktop.offline.models import AuditFilter
    from desktop.offline.backup_crypto import open_backup
    from desktop.offline.backup_state import decode_state

    path = tmp_path / 'fictional-instance' / 'audit.db'
    target = tmp_path / 'fictional-complete.bhlibackup'
    recovery = tmp_path / 'fictional-current-recovery.bhlibackup'
    password = 'Fictional acceptance passphrase!'
    app = OfflineApplication(db_path=path)
    try:
        pump(app, lambda: hasattr(app.screen, 'name'))
        app.screen.name.insert(0, 'Fictional Backup Auditor')
        app.screen.save()
        pump(app, lambda: app.profile is not None and app.destination == 'Dashboard')
        values = dict(driver_name='Fictional preserved driver', helper_name=None,
                      audit_date='2026-11-06', station='Fictional station',
                      plate_number='00123', remarks='Fictional Unicode 日本語 🚚')
        from uuid import uuid4
        call(app, lambda repo: repo.create(str(uuid4()), values))
        app.open_backup()
        assert app.destination == 'Backup & restore'
        view = app.screen
        view.secret.insert(0, password)
        view.confirmation.insert(0, password)
        monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **kw: str(target))
        view.create()
        assert view.secret.get() == '' and view.confirmation.get() == ''
        pump(app, lambda: not app.backup_job.pending)
        assert app.backup_job.phase == 'saved', app.backup_job.message
        state = decode_state(open_backup(target.read_bytes(), password, platform='windows'), platform='windows')
        assert len(state.rows['audit_records']) == 1
        call(app, lambda repo: repo.create(str(uuid4()), values | {'driver_name': 'Fictional later driver'}))
        monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kw: str(target))
        view.secret.insert(0, password)
        view.inspect()
        pump(app, lambda: app.backup_job.phase == 'preview')
        assert app.backup_job.preview.candidate['counts']['audit_records'] == 1
        assert app.backup_job.preview.current['counts']['audit_records'] == 2
        monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **kw: str(recovery))
        view.secret.insert(0, password)
        view.prepare()
        pump(app, lambda: app.backup_job.phase == 'prepared')
        protected = decode_state(open_backup(recovery.read_bytes(), password, platform='windows'), platform='windows')
        assert len(protected.rows['audit_records']) == 2
        view.acknowledgement.set(True)
        prompts = []
        def reject(*args, **kwargs):
            prompts.append(kwargs)
            return False
        monkeypatch.setattr(messagebox, 'askokcancel', reject)
        view.apply()
        assert prompts[0]['default'] == messagebox.CANCEL
        assert app.backup_job.phase == 'prepared'
        monkeypatch.setattr(messagebox, 'askokcancel', lambda *a, **kw: True)
        view.acknowledgement.set(True)
        view.apply()
        pump(app, lambda: app.backup_job.phase == 'restored' and app.destination == 'Dashboard')
        audits = call(app, lambda repo: repo.list(AuditFilter()))
        assert audits.total == 1 and audits.items[0].plate_number == '00123'
        assert audits.items[0].audited_by_name == 'Fictional Backup Auditor'
        for mode in ('Dark', 'Light'):
            app.set_theme(mode)
            app.geometry('850x650')
            app.open_backup()
            app.update()
            assert app.screen.winfo_ismapped()
            assert app.screen.secret.winfo_width() > 100
            captures = os.getenv('DAMS_PHASE6E_CAPTURE_DIR')
            if captures:
                from tests.desktop.offline.native_capture import capture_owned_window
                folder = Path(captures)
                folder.mkdir(parents=True, exist_ok=True)
                app.update()
                capture_owned_window(app, folder / f'windows-backup-{mode.lower()}.png')
            app.navigate('Local profile', force=True)
    finally:
        app.close(force=True)
        pump(app, lambda: app.closed)
    reopened = OfflineApplication(db_path=path)
    try:
        pump(reopened, lambda: reopened.profile is not None)
        assert call(reopened, lambda repo: repo.list(AuditFilter())).total == 1
    finally:
        reopened.close(force=True)
        pump(reopened, lambda: reopened.closed)
