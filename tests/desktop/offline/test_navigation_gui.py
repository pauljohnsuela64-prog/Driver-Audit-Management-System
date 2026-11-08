"""Offline navigation uses fictional temporary stores; never installed data."""
import os
from pathlib import Path
import sys
import time
import tkinter as tk
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
    reason='Native Windows GUI requires explicit test mode')


def settle(app, seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(.01)


@pytest.fixture
def app(tmp_path):
    import customtkinter as ctk
    from desktop.offline.app import OfflineApplication
    from tests.desktop.offline.test_backup_gui import pump
    ctk.set_widget_scaling(1)
    ctk.set_appearance_mode('Light')
    value = OfflineApplication(db_path=tmp_path / 'fictional-navigation.db')
    value.callback_errors = []
    value.report_callback_exception = lambda e, v, tb: value.callback_errors.append((e.__name__, str(v)))
    try:
        pump(value, lambda: hasattr(value.screen, 'name'))
        value.screen.name.insert(0, 'Fictional Navigation Auditor')
        value.screen.save()
        pump(value, lambda: value.shell is not None and getattr(value.screen, 'loaded', False))
        value.geometry('1200x700')
        settle(value)
        yield value
    finally:
        value.close(force=True)
        pump(value, lambda: value.closed)
        ctk.set_widget_scaling(1)
        assert not value.callback_errors


@pytest.mark.parametrize('multiplier', (1, 1.5, 2))
def test_compact_resize_respects_manual_choice_and_logo(app, multiplier):
    import customtkinter as ctk
    ctk.set_widget_scaling(multiplier)
    app.geometry('800x650')
    settle(app)
    app.shell.set_collapsed(True)
    app.shell.toggle.invoke()
    settle(app)
    assert not app.shell.collapsed
    app.geometry('801x650')
    settle(app)
    assert not app.shell.collapsed
    for _ in range(10):
        app.shell.collapse()
        settle(app, .02)
        assert app.shell.collapsed
        assert not str(app.shell.brand._label.cget('image'))
        app.shell.collapse()
        settle(app, .02)
        assert not app.shell.collapsed
        assert str(app.shell.brand._label.cget('image'))
    assert all(b.winfo_ismapped() for b in app.shell.nav_buttons.values())


@pytest.mark.parametrize('collapsed', (True, False))
def test_theme_rebuild_preserves_sidebar_and_unsent_audit(app, collapsed):
    from tests.desktop.offline.test_gui import fill
    app.open_create()
    fill(app.screen)
    app.shell.set_collapsed(collapsed)
    for theme in ('Dark', 'Light'):
        app.set_theme(theme)
        settle(app)
        assert app.destination == 'Create Audit'
        assert app.screen.inputs['driver_name'].get() == 'Fictional Offline Driver'
        assert app.shell.collapsed is collapsed
        if collapsed:
            assert app.shell.footer.cget('text') == ''


def test_history_highlights_audit_parent(app):
    from tests.desktop.offline.test_backup_gui import pump, call
    from desktop.theme import color
    identity = call(app, lambda repo: repo.create(str(uuid4()), dict(
        driver_name='Fictional Driver', helper_name=None, audit_date='2026-11-08',
        station='Fictional Station', plate_number='0007', remarks=None))).id
    app.navigate('Audit History', identity)
    pump(app, lambda: app.screen.loaded)
    assert app.shell.nav_buttons['Driver Audits'].cget('fg_color') == color('selected')


def test_offline_tooltips_delayed_outside_and_cancelled(app):
    shell = app.shell
    shell.set_collapsed(False)
    tip = shell.tips['Driver Audits']
    button = shell.nav_buttons['Driver Audits']
    assert button.cget('cursor') == 'hand2'
    tip.show()
    settle(app, .45)
    assert tip.window is None
    shell.set_collapsed(True)
    tip.show()
    assert tip.window is None
    settle(app, .45)
    assert tip.window is not None
    window = tip.window
    left, top = window.winfo_rootx(), window.winfo_rooty()
    right, bottom = left + window.winfo_width(), top + window.winfo_height()
    bx, by = button.winfo_rootx(), button.winfo_rooty()
    assert right <= bx or left >= bx + button.winfo_width() or bottom <= by or top >= by + button.winfo_height()
    tip.hide()
    tip.show()
    tip.hide()
    settle(app, .45)
    assert tip.window is None
    tip.show()
    shell.set_collapsed(False)
    settle(app, .45)
    assert tip.window is None
    shell.set_collapsed(True)
    tip.show()
    app.navigate('Driver Audits')
    settle(app, .45)
    assert tip.window is None
    tip.show()
    app.set_theme('Dark')
    settle(app, .45)
    assert tip.window is None
