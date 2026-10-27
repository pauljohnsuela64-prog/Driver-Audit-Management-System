"""One application lifetime per process for the pending-login native close check."""
import secrets
from threading import Event
import time

from desktop.api import ApiClient
from desktop.app import Application
from desktop.config import Config
from tests.desktop.visual_support import DemoTransport


def main():
    client=ApiClient(Config(),DemoTransport())
    app=Application(client)
    errors=[]
    app.report_callback_exception=lambda kind,value,tb:errors.append(kind.__name__)
    app.tk.createcommand('close_bgerror',lambda value:errors.append('TclError'))
    app.tk.eval('proc bgerror {message} {close_bgerror $message}')
    started,gate,disposed=Event(),Event(),Event()
    sign_in,logout=client.sign_in,client.logout
    def held_login(username,password):
        result=sign_in(username,password)
        started.set()
        gate.wait(5)
        return result
    def revoke(token):
        logout(token)
        disposed.set()
    client.sign_in=held_login
    client.logout=revoke
    try:
        app.update()
        app.screen.username.insert(0,'admin')
        app.screen.password.insert(0,secrets.token_urlsafe(24))
        app.screen.submit()
        deadline=time.monotonic()+3
        while not started.is_set() and time.monotonic()<deadline:
            app.update()
            time.sleep(.01)
        assert started.is_set()
        before=time.monotonic()
        app.close()
        assert time.monotonic()-before<2
        assert app.session.login is None and app.closing
        gate.set()
        assert disposed.wait(3),'Abandoned login was not revoked after native window close'
        assert not errors,errors
        print('Native pending-login close: prompt return, local cleanup, late-session revocation, zero callback errors')
    finally:
        gate.set()
        if not app.closing:
            app.close()


if __name__=='__main__':
    main()
