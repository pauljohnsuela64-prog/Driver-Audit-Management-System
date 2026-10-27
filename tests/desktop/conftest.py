"""One Tk interpreter per test process; separate transports per test."""
import pytest


@pytest.fixture(scope='session')
def native_app():
    from desktop.app import Application
    from desktop.api import ApiClient
    from desktop.config import Config
    from tests.desktop.visual_support import DemoTransport
    result=Application(ApiClient(Config(),DemoTransport()))
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
        result.close(force=True)
