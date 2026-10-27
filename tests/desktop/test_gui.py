"""Opt-in native Tk checks; headless runs report these as skipped, not passed."""
import os
import sys
import time
import pytest

pytestmark = pytest.mark.skipif(os.getenv('DAMS_DESKTOP_GUI_TESTS') != '1' or sys.platform != 'win32',
                                reason='Native Windows GUI requires DAMS_DESKTOP_GUI_TESTS=1')


def pump(app, predicate=lambda: True):
    deadline = time.monotonic()+4
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), 'Native UI did not reach expected state'


@pytest.fixture(scope='module')
def native_app():
    from desktop.app import Application
    from desktop.api import ApiClient
    from desktop.config import Config
    from tests.desktop.visual_support import DemoTransport
    result = Application(ApiClient(Config(), DemoTransport()))
    result.callback_errors=[]
    result.tk.createcommand('bhli_test_bgerror',lambda message:result.callback_errors.append(('TclError',message)))
    result.tk.eval('proc bgerror {message} {bhli_test_bgerror $message}')
    original=result.report_callback_exception
    def capture_callback(exc,value,tb):
        import traceback
        result.callback_errors.append((exc.__name__,str(value),[(f.name,f.lineno) for f in traceback.extract_tb(tb)]))
        original(exc,value,tb)
    result.report_callback_exception=capture_callback
    result.update()
    yield result
    if result.winfo_exists():
        result.close()


@pytest.fixture
def app(native_app):
    native_app.logout('Native test setup')
    pump(native_app)
    native_app.callback_errors.clear()
    yield native_app
    assert native_app.callback_errors==[]


def sign_in(app, username='admin'):
    app.screen.username.insert(0, username)
    app.screen.password.insert(0, 'fictional test passphrase')
    app.screen.submit()
    pump(app, lambda: app.session.login is not None)


def test_native_login_shell_roles_theme_resize_logout(app):
    sign_in(app)
    assert 'Employee Accounts' in app.shell.nav_buttons
    initial_collapsed=app.shell.collapsed
    app.shell.collapse()
    assert app.shell.collapsed is not initial_collapsed
    app.shell.collapse()
    assert app.shell.collapsed is initial_collapsed
    app.set_theme('Dark')
    app.geometry('800x600')
    pump(app)
    app.navigate('My Account')
    pump(app)
    assert app.screen.winfo_exists()
    app.logout()
    pump(app, lambda: app.session.login is None)
    sign_in(app, 'auditor')
    assert 'Employee Accounts' not in app.shell.nav_buttons
    assert app.session.login.user.role == 'AUDITOR'


def test_native_login_failure_and_password_not_retained(app):
    app.screen.username.insert(0, 'wrong')
    app.screen.password.insert(0, 'secret only in memory')
    app.screen.submit()
    pump(app, lambda: app.screen.submit_button.cget('state') == 'normal')
    assert app.session.login is None
    assert app.screen.password.get() == ''
    assert 'secret only in memory' not in app.screen.status.cget('text')


def test_native_audits_filters_details_and_return_state(app):
    sign_in(app)
    pump(app, lambda: getattr(app.screen,'loaded',False))
    assert app.screen.total == 3
    app.navigate('Driver Audits')
    pump(app, lambda: getattr(app.screen,'loaded',False))
    assert len(app.screen.table.tree.get_children()) == 3
    app.screen.search.insert(0,'Example')
    app.screen.apply()
    pump(app, lambda: app.screen.loaded)
    assert app.query.driver_name == 'Example'
    app.screen.table.tree.selection_set('1')
    app.screen.open_selected()
    pump(app, lambda: getattr(app.screen,'loaded',False))
    assert app.destination == 'Audit Details'
    assert app.screen.record.audited_by_name == 'Original Reviewer'
    app.escape()
    pump(app, lambda: getattr(app.screen,'loaded',False))
    assert app.query.driver_name == 'Example'
    assert app.screen.table.tree.selection() == ('1',)


def test_native_offline_empty_and_retry(app):
    sign_in(app)
    transport=app.client.transport
    transport.mode='offline'
    app.navigate('Driver Audits')
    pump(app, lambda: getattr(app.screen,'last_error',None) is not None)
    assert 'private' not in app.screen.notice.cget('text')
    assert not app.screen.table.tree.get_children()
    transport.mode='empty'
    app.screen.refresh()
    pump(app, lambda: app.screen.loaded)
    assert not app.screen.table.tree.get_children()
    assert 'No matching' in app.screen.notice.cget('text')
    transport.mode='normal'


def test_native_invalid_date_is_local_and_does_not_request(app):
    sign_in(app)
    app.navigate('Driver Audits')
    pump(app, lambda: getattr(app.screen,'loaded',False))
    before=len(app.client.transport.requests)
    app.screen.date_from.insert(0,'2026-02-30')
    app.screen.apply()
    pump(app)
    assert len(app.client.transport.requests) == before
    assert app.screen.notice.cget('text')


def test_native_station_search_keeps_single_filter_value(app):
    sign_in(app)
    app.navigate('Driver Audits')
    pump(app,lambda:app.screen.loaded)
    s=app.screen
    s.search_field.set('Station')
    s.search_changed('Station')
    s.search.insert(0,'North')
    s.apply()
    pump(app,lambda:s.loaded)
    s.search_field.set('Driver')
    s.search_changed('Driver')
    s.search.delete(0,'end')
    s.search.insert(0,'Example')
    s.apply()
    assert app.query.station=='North'


def test_native_read_requests_honor_rate_limit(app):
    from desktop.api import ApiError
    sign_in(app)
    pump(app,lambda:app.screen.loaded)
    app.request(lambda: (_ for _ in ()).throw(ApiError(429,retry_after=60)),lambda *_:None)
    pump(app,lambda:app.retry_until>0)
    calls=[]
    app.request(lambda:calls.append('sent'),lambda *_:None)
    pump(app)
    assert calls==[]
    app.retry_until=0


def test_native_logout_survives_saturated_screen_queue(app,monkeypatch):
    sign_in(app)
    pump(app,lambda:app.screen.loaded)
    # Allow any previous session's asynchronous logout to settle first.
    for _ in range(10):
        app.update()
        time.sleep(.01)
    monkeypatch.setattr(app.tasks,'submit',lambda *args,**kwargs:False)
    before=sum(path=='/auth/logout' for _,path in app.client.transport.requests)
    app.logout()
    pump(app,lambda:sum(path=='/auth/logout' for _,path in app.client.transport.requests)>before)


def test_native_window_state_method_remains_available_for_dpi_tracker(app):
    assert callable(app.state)
    assert app.state() in ('normal','zoomed','iconic','withdrawn')


def test_native_compact_window_auto_collapses_sidebar(app):
    sign_in(app)
    app.geometry('1200x650')
    for _ in range(5):
        app.update()
        time.sleep(.02)
    app.shell.set_collapsed(False)
    app.geometry('800x600')
    for _ in range(12):
        app.update()
        time.sleep(.02)
    assert app.shell.collapsed


def test_native_destroy_cancels_widget_owned_timers(app):
    import customtkinter as ctk
    from desktop.components.common import destroy_view
    frame=ctk.CTkFrame(app)
    fired=[]
    timer=frame.after(100,lambda:fired.append('obsolete screen'))
    destroy_view(frame)
    assert timer not in app.tk.call('after','info')
    for _ in range(8):
        app.update()
        time.sleep(.02)
    assert fired==[]


def test_native_primary_action_has_distinct_keyboard_focus(app):
    app.set_theme('Light')
    target=app.screen.submit_button
    before=target.cget('border_color')[0]
    target._canvas.event_generate('<FocusIn>')
    app.update()
    assert target.cget('border_color')[0]!=before


def test_native_back_restores_keyboard_row_navigation(app):
    sign_in(app)
    app.focus_force()
    app.navigate('Driver Audits')
    pump(app,lambda:app.screen.loaded)
    tree=app.screen.table.tree
    tree.selection_set('3')
    tree.focus('3')
    tree.focus_set()
    tree.event_generate('<Return>')
    pump(app,lambda:app.destination=='Audit Details' and app.screen.loaded)
    app.escape()
    pump(app,lambda:app.destination=='Driver Audits' and app.screen.loaded)
    assert app.focus_get() is app.screen.table.tree
    app.screen.table.tree.event_generate('<Down>')
    app.update()
    assert app.screen.table.tree.selection()==('2',)


def test_native_callback_failure_does_not_stop_polling_or_expiry(app):
    from dataclasses import replace
    from datetime import datetime,timedelta,timezone
    sign_in(app)
    pump(app,lambda:app.screen.loaded)
    def failed_callback(result,error):
        raise RuntimeError('intentional regression fault')
    app.request(lambda:True,failed_callback)
    pump(app,lambda:bool(app.callback_errors))
    assert app.callback_errors[0][0]=='RuntimeError'
    app.callback_errors.clear()  # This one callback error is intentional and asserted above.
    seen=[]
    app.request(lambda:True,lambda *_:seen.append(True))
    pump(app,lambda:bool(seen))
    app.session.login=replace(app.session.login,expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    pump(app,lambda:app.session.login is None)
