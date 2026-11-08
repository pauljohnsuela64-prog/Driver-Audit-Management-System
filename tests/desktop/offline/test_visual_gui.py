"""Native offline geometry checks using fictional temporary stores only."""
import os
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
    reason='Native Windows visual verification requires explicit GUI mode')


def test_centered_columns_and_backup_actions_reflow(tmp_path):
    import customtkinter as ctk
    from desktop.offline.app import OfflineApplication
    from tests.desktop.offline.test_backup_gui import pump, call
    from tests.desktop.offline.native_capture import capture_owned_window
    ctk.set_appearance_mode('Light')
    app = OfflineApplication(db_path=tmp_path / 'fictional-ui.db')
    callback_errors = []
    metrics = []
    app.report_callback_exception = lambda exc, value, tb: callback_errors.append((exc.__name__, str(value)))
    try:
        pump(app, lambda: hasattr(app.screen, 'name'))
        capture_dir = os.getenv('DAMS_PHASE6G_CAPTURE_DIR')
        if capture_dir:
            Path(capture_dir).mkdir(parents=True, exist_ok=True)
            capture_owned_window(app, Path(capture_dir) / 'welcome-light.png')
        app.screen.name.insert(0, 'Fictional Visual Auditor')
        app.screen.save()
        pump(app, lambda: callback_errors or
             (app.destination == 'Dashboard' and getattr(app.screen, 'loaded', False)))
        assert not callback_errors, callback_errors
        call(app, lambda repo: repo.create(str(uuid4()), dict(
            driver_name='Fictional Driver 日本語', helper_name='Fictional Helper',
            audit_date='2026-11-08', station='Fictional Station', plate_number='00123',
            remarks='Fictional layout verification')))
        app.navigate('Driver Audits')
        pump(app, lambda: app.screen.loaded)
        for field in ('driver_name', 'helper_name', 'station', 'plate_number', 'audited_by_name'):
            assert str(app.screen.table.tree.column(field, 'anchor')) == 'center'
        app.shell.set_collapsed(True)
        app.update()
        assert not str(app.shell.brand._label.cget('image')), 'Collapsed sidebar must not clip the full logo'
        app.shell.set_collapsed(False)
        app.update()
        assert str(app.shell.brand._label.cget('image'))
        if capture_dir:
            Path(capture_dir).mkdir(parents=True, exist_ok=True)
            capture_owned_window(app, Path(capture_dir) / 'audits-light.png')
        for theme in ('Light', 'Dark'):
            app.set_theme(theme)
            app.open_backup()
            for width, height, scale in ((800, 650, 1), (800, 650, 1.5), (800, 650, 2),
                                         (1200, 700, 1), (1200, 700, 2)):
                ctk.set_widget_scaling(scale)
                app.geometry(f'{width}x{height}')
                for _ in range(8):
                    app.update()
                view = app.screen
                actions = [child for child in view.winfo_children() if isinstance(child, ctk.CTkButton)]
                assert len(actions) == 6
                assert len({b.winfo_width() for b in actions}) == 1
                for b in actions:
                    assert b.winfo_x() >= 0
                    assert b.winfo_x() + b.winfo_width() <= view.winfo_width() + 2
                    assert b._text_label.winfo_reqwidth() <= b.winfo_width() - 12
                    assert b._text_label.winfo_reqheight() <= b.winfo_height() - 8
                for first, second in zip(actions, actions[1:]):
                    assert first.winfo_rooty() + first.winfo_height() < second.winfo_rooty()
                metrics.append(dict(theme=theme, logical_geometry=f'{width}x{height}',
                                    widget_multiplier=scale, effective_widget_scale=view._get_widget_scaling(),
                                    window_scale=app._get_window_scaling(), button_widths=[b.winfo_width() for b in actions]))
                if capture_dir:
                    suffix = '-wide' if width > 800 else ''
                    capture_owned_window(app, Path(capture_dir) / f'backup-{theme.lower()}-{scale}{suffix}.png')
                    view._parent_canvas.yview_moveto(1)
                    app.update()
                    capture_owned_window(app, Path(capture_dir) / f'backup-bottom-{theme.lower()}-{scale}{suffix}.png')
                    view._parent_canvas.yview_moveto(0)
            ctk.set_widget_scaling(1)
            app.navigate('Local profile', force=True)
        assert not callback_errors, callback_errors
        if capture_dir:
            (Path(capture_dir) / 'layout-metrics.json').write_text(json.dumps(metrics, indent=2))
    finally:
        app.close(force=True)
        pump(app, lambda: app.closed)
        ctk.set_widget_scaling(1)
