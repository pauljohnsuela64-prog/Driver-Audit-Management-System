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
    result.update()
    yield result
    if result.winfo_exists():
        result.close()


@pytest.fixture
def app(native_app):
    native_app.logout('Native test setup')
    pump(native_app)
    return native_app


def sign_in(app, username='admin'):
    app.screen.username.insert(0, username)
    app.screen.password.insert(0, 'fictional test passphrase')
    app.screen.submit()
    pump(app, lambda: app.state.login is not None)


def test_native_login_shell_roles_theme_resize_logout(app):
    sign_in(app)
    assert 'Employee Accounts' in app.shell.nav_buttons
    app.shell.collapse()
    assert app.shell.collapsed
    app.set_theme('Dark')
    app.geometry('800x600')
    pump(app)
    app.navigate('My Account')
    pump(app)
    assert app.screen.winfo_exists()
    app.logout()
    pump(app, lambda: app.state.login is None)
    sign_in(app, 'auditor')
    assert 'Employee Accounts' not in app.shell.nav_buttons
    assert app.state.login.user.role == 'AUDITOR'


def test_native_login_failure_and_password_not_retained(app):
    app.screen.username.insert(0, 'wrong')
    app.screen.password.insert(0, 'secret only in memory')
    app.screen.submit()
    pump(app, lambda: app.screen.submit_button.cget('state') == 'normal')
    assert app.state.login is None
    assert app.screen.password.get() == ''
    assert 'secret only in memory' not in app.screen.status.cget('text')
