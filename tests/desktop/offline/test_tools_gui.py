"""Option A navigation retains local identity and existing safety workflows."""
import os
import sys
from uuid import uuid4

import pytest

from tests.desktop.offline.test_navigation_gui import app, settle
from tests.desktop.offline.test_backup_gui import pump, call

pytestmark = pytest.mark.skipif(
    os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
    reason='Native Windows GUI requires explicit test mode')


def test_two_destinations_and_existing_tools_are_discoverable(app):
    assert app.destination == 'Driver Audits'
    assert tuple(app.shell.nav_buttons) == ('Driver Audits', 'Settings & Tools')
    assert app.shell.account is None and app.shell.appearance is None
    assert app.screen.create_button.winfo_exists()
    assert app.screen.export_button.winfo_exists()
    assert not hasattr(app.screen, 'transfer_button')
    app.navigate('Settings & Tools')
    settle(app)
    assert app.screen.name.get() == app.profile.name
    for control in (app.screen.save_button, app.screen.backup_button, app.screen.transfer_button, app.screen.appearance):
        assert control.winfo_exists()
    assert app.screen.appearance.get() in ('Light', 'Dark')
    assert app.screen.save_button._canvas.cget('takefocus') == '1'


def test_profile_draft_survives_theme_and_save_preserves_attribution(app):
    identity = call(app, lambda repo: repo.create(str(uuid4()), dict(
        driver_name='Fictional Profile Driver', helper_name=None, audit_date='2026-11-08',
        station='Fictional Station', plate_number='0007', remarks=None))).id
    original_name, original_id = app.profile.name, app.profile.id
    app.navigate('Settings & Tools')
    app.screen.name.delete(0, 'end')
    app.screen.name.insert(0, 'Renamed Fictional Auditor')
    for theme in ('Dark', 'Light'):
        app.set_theme(theme)
        settle(app)
        assert app.destination == 'Settings & Tools'
        assert app.screen.name.get() == 'Renamed Fictional Auditor'
        assert app.profile.name == original_name
    app.screen.save()
    pump(app, lambda: app.profile.name == 'Renamed Fictional Auditor')
    assert app.profile.id == original_id
    assert app.destination == 'Settings & Tools'
    assert call(app, lambda repo: repo.read(identity)).audited_by_name == original_name


def test_unsaved_profile_navigation_requires_explicit_discard(app):
    app.navigate('Settings & Tools')
    app.screen.name.insert('end', ' unsaved')
    app.navigate('Driver Audits')
    assert app.destination == 'Settings & Tools' and app.dialog is not None
    app.dialog.cancel()
    assert app.screen.name.get().endswith(' unsaved')
    app.navigate('Driver Audits')
    app.dialog.accept()
    pump(app, lambda: app.destination == 'Driver Audits' and app.screen.loaded)
    assert not app.profile.name.endswith(' unsaved')


def test_backup_transfer_returns_and_highlighting(app):
    from desktop.theme import color
    app.navigate('Settings & Tools')
    app.screen.backup_button.invoke()
    assert app.destination == 'Backup & restore'
    assert app.shell.nav_buttons['Settings & Tools'].cget('fg_color') == color('selected')
    app.screen.back_button.invoke()
    assert app.destination == 'Settings & Tools'
    app.screen.transfer_button.invoke()
    assert app.destination == 'Transfer audits'
    assert app.shell.nav_buttons['Settings & Tools'].cget('fg_color') == color('selected')
    app.escape()
    assert app.destination == 'Settings & Tools'


def test_backup_available_before_any_profile_and_returns_to_welcome(tmp_path):
    from desktop.offline.app import OfflineApplication
    value = OfflineApplication(db_path=tmp_path / 'empty-fictional.db')
    try:
        pump(value, lambda: hasattr(value.screen, 'name'))
        assert value.profile is None and value.screen.welcome
        value.open_backup()
        assert value.destination == 'Backup & restore'
        value.screen.back_button.invoke()
        assert value.profile is None and value.screen.welcome
        assert value.screen.save_button.cget('text') == 'Continue'
        assert call(value, lambda repo: repo.profile()) is None
    finally:
        value.close(force=True)
        pump(value, lambda: value.closed)


def test_settings_controls_fit_compact_and_scaled_windows(app):
    import customtkinter as ctk
    from pathlib import Path
    from tests.desktop.offline.native_capture import capture_owned_window
    app.navigate('Settings & Tools')
    for theme in ('Light', 'Dark'):
        app.set_theme(theme)
        for multiplier in (1, 1.5, 2):
            ctk.set_widget_scaling(multiplier)
            for width in (800, 1200):
                app.geometry(f'{width}x650')
                app.shell.set_collapsed(True)
                settle(app)
                view = app.screen
                assert view.winfo_width() <= view._parent_canvas.winfo_width() + 2
                for control in (view.backup_button, view.transfer_button, view.appearance):
                    assert control.winfo_x() >= 0
                    assert control.winfo_x() + control.winfo_width() <= view.winfo_width() + 2
                capture_dir = os.getenv('DAMS_NAV_CAPTURE_DIR')
                if capture_dir and multiplier == 1:
                    output = Path(capture_dir)
                    output.mkdir(parents=True, exist_ok=True)
                    capture_owned_window(app, output / f'settings-{theme.lower()}-{width}.png')
                    view._parent_canvas.yview_moveto(1)
                    settle(app, .05)
                    capture_owned_window(app, output / f'settings-bottom-{theme.lower()}-{width}.png')
                    view._parent_canvas.yview_moveto(0)


def test_keyboard_focus_reveals_tools_below_fold(app):
    app.navigate('Settings & Tools')
    app.geometry('800x600')
    settle(app)
    view = app.screen
    view._parent_canvas.yview_moveto(0)
    view.transfer_button._canvas.event_generate('<FocusIn>')
    settle(app)
    assert view.transfer_button.winfo_rooty() >= view._parent_canvas.winfo_rooty()
    assert (view.transfer_button.winfo_rooty() + view.transfer_button.winfo_height()
            <= view._parent_canvas.winfo_rooty() + view._parent_canvas.winfo_height())
