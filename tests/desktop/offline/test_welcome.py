"""Every process launch confirms the existing stable local identity."""
from types import SimpleNamespace
import os
import sys

import pytest

from desktop.offline.app import OfflineApplication


def test_returning_user_sees_prefilled_welcome_instead_of_dashboard(monkeypatch):
    from desktop.offline import views
    calls = []
    profile = SimpleNamespace(id='stable-fictional-id', name='Fictional Auditor')
    monkeypatch.setattr(views, 'ProfileView',
                        lambda parent, app, **kw: calls.append(kw) or 'welcome')
    app = SimpleNamespace(closing=False, profile=None, recovery_blocked=False,
                          _replace_root_view=lambda view: calls.append(view),
                          rebuild_shell=lambda destination: calls.append(destination))
    OfflineApplication._bootstrapped(app, (profile, None), None)
    assert app.profile is profile
    assert calls == [{'welcome': True}, 'welcome']


@pytest.mark.skipif(os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
                    reason='Native Windows welcome acceptance requires explicit GUI mode')
def test_native_first_use_and_restart_preserve_records_and_original_identity(tmp_path):
    from tests.desktop.offline.test_backup_gui import pump, call
    from uuid import uuid4
    path = tmp_path / 'fictional-welcome.db'
    identity = None
    audit_id = str(uuid4())
    for launch in range(2):
        app = OfflineApplication(db_path=path)
        try:
            pump(app, lambda: hasattr(app.screen, 'name'))
            assert app.screen.welcome
            assert app.screen.save_button.cget('text') == 'Continue'
            assert app.screen.name.get() == ('' if launch == 0 else 'Fictional Original')
            if launch == 0:
                app.screen.save()
                assert not app.screen.pending and app.profile is None
                app.screen.name.insert(0, 'Fictional Original')
            else:
                assert app.profile.id == identity
                app.screen.name.delete(0, 'end')
                app.screen.name.insert(0, 'Fictional Renamed')
            for theme in ('Light', 'Dark'):
                import customtkinter as ctk
                ctk.set_appearance_mode(theme)
                app.geometry('800x600')
                app.update()
                assert app.screen.save_button.winfo_width() >= 100
                assert app.screen.name.winfo_width() > 200
            app.screen.save()
            pump(app, lambda: app.destination == 'Driver Audits' and app.screen.loaded)
            if launch == 0:
                identity = app.profile.id
                call(app, lambda repo: repo.create(audit_id, dict(
                    driver_name='Fictional Driver', helper_name=None, audit_date='2026-11-08',
                    station='Fictional Station', plate_number='00123', remarks=None)))
            else:
                assert app.profile.id == identity
                audit = call(app, lambda repo: repo.read(audit_id))
                assert audit.audited_by_name == 'Fictional Original'
                assert len(call(app, lambda repo: repo.history(audit_id)).items) == 1
        finally:
            app.close(force=True)
            pump(app, lambda: app.closed)
