from threading import Event, get_ident
from pathlib import Path

from tests.desktop.test_gui import app,sign_in,pump,pytestmark
from desktop.api import ApiError
from tests.desktop.test_reports import Client,row


def ready(app):
    sign_in(app);app.navigate('Driver Audits');pump(app,lambda:app.screen.loaded)


def accept_export(app,monkeypatch,path):
    monkeypatch.setattr('desktop.export_ui.filedialog.asksaveasfilename',lambda **kw:str(path))
    app.screen.export_button.invoke();pump(app)
    assert app.dialog is not None
    app.dialog.accept();pump(app)


def test_export_applied_filters_and_off_thread_generation(app,tmp_path,monkeypatch):
    ready(app);owner=get_ident();calls=[]
    client=Client([row()])
    def fetch(token,q):calls.append(get_ident());return client.list_audits(token,q)
    app.client.list_audits=fetch
    path=tmp_path/'all.xlsx';accept_export(app,monkeypatch,path)
    pump(app,lambda:not app.export_job.pending)
    assert path.exists() and calls[0]!=owner and 'saved' in app.export_job.message.lower()
    assert app.screen.export_button.cget('state')=='normal'


def test_unapplied_search_cannot_export_old_results(app,tmp_path,monkeypatch):
    ready(app);app.screen.search.insert(0,'unapplied')
    monkeypatch.setattr('desktop.export_ui.filedialog.asksaveasfilename',lambda **kw:(_ for _ in ()).throw(AssertionError()))
    app.screen.export_button.invoke()
    assert app.dialog is None and 'apply' in app.screen.notice.cget('text').lower()


def test_cancel_save_has_no_job(app,monkeypatch):
    ready(app)
    monkeypatch.setattr('desktop.export_ui.filedialog.asksaveasfilename',lambda **kw:'')
    app.screen.export_button.invoke();app.dialog.accept();pump(app)
    assert not app.export_job.pending


def test_navigation_theme_and_cancel_remain_responsive(app,tmp_path,monkeypatch):
    ready(app);entered=Event();release=Event();client=Client([row()])
    def fetch(token,q):entered.set();release.wait(8);return client.list_audits(token,q)
    app.client.list_audits=fetch
    path=tmp_path/'x.xlsx';accept_export(app,monkeypatch,path)
    pump(app,entered.is_set)
    try:
        app.navigate('Dashboard');assert app.destination=='Dashboard'
        app.set_theme('Dark');app.navigate('Driver Audits')
        assert app.export_job.pending
        app.screen.cancel_export.invoke();release.set()
        pump(app,lambda:not app.export_job.pending)
        assert not path.exists() and 'cancel' in app.export_job.message.lower()
    finally:release.set()


def test_export_401_logs_out_without_partial_file(app,tmp_path,monkeypatch):
    ready(app)
    def fail(*a):raise ApiError(401)
    app.client.list_audits=fail
    path=tmp_path/'x.xlsx';accept_export(app,monkeypatch,path)
    pump(app,lambda:app.session.login is None)
    assert not path.exists()


def test_logout_cancels_pending_export(app,tmp_path,monkeypatch):
    ready(app);entered=Event();release=Event();client=Client([row()])
    def fetch(token,q):entered.set();release.wait(8);return client.list_audits(token,q)
    app.client.list_audits=fetch
    path=tmp_path/'x.xlsx';accept_export(app,monkeypatch,path);pump(app,entered.is_set)
    app.logout(force=True);release.set();pump(app)
    assert not path.exists() and app.session.login is None


def test_confirmation_disclosure_can_be_read_with_keyboard(app):
    import customtkinter as ctk
    ready(app)
    try:
        for scaling in (2/3,1.0):
            ctk.set_widget_scaling(scaling);ctk.set_window_scaling(scaling)
            app.screen.export_button.invoke();pump(app)
            dialog=app.dialog
            # Device pixels vary with OS DPI. Use the dialog's own compact
            # minimum and verify overflow before asserting keyboard scrolling.
            width,height=dialog.minsize();dialog.geometry(f'{width}x{height}')
            pump(app,lambda:dialog.body._parent_canvas.yview()[1]<1)
            first=dialog.body._parent_canvas.yview()[0]
            dialog.cancel_button.focus_force();dialog.cancel_button.event_generate('<Next>')
            pump(app,lambda:dialog.body._parent_canvas.yview()[0]>first)
            dialog.cancel()
    finally:
        if app.dialog:app.dialog.cancel()
        ctk.set_widget_scaling(1.0);ctk.set_window_scaling(1.0)
