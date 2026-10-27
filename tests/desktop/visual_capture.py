"""Native fictional-data screenshots: python -m tests.desktop.visual_capture."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time
import traceback
from threading import Event

import customtkinter as ctk
from desktop.api import ApiClient
from desktop.app import Application
from desktop.config import Config
from tests.desktop.visual_support import DemoTransport
from tests.desktop.native_capture import capture as capture_hwnd


def main():
    output=Path('artifacts/desktop').resolve()
    output.mkdir(parents=True,exist_ok=True)
    transport=DemoTransport()
    app=Application(ApiClient(Config(),transport))
    callback_errors=[]
    app.tk.createcommand('bhli_test_bgerror',lambda message:callback_errors.append({'type':'TclError','message':message}))
    app.tk.eval('proc bgerror {message} {bhli_test_bgerror $message}')
    app.report_callback_exception=lambda exc,value,tb:callback_errors.append({'type':exc.__name__,'message':str(value),
        'frames':[(Path(f.filename).name,f.lineno,f.name) for f in traceback.extract_tb(tb)]})
    scale=app._get_window_scaling()
    width=min(1280,int(app.winfo_screenwidth()/scale)-40)
    height=min(760,int(app.winfo_screenheight()/scale)-80)
    app.geometry(f'{width}x{height}+10+10')
    def wait(predicate=lambda:True):
        end=time.monotonic()+5
        while time.monotonic()<end:
            app.update()
            if predicate():
                return
            time.sleep(.02)
        raise AssertionError('Visual state did not settle')
    def capture(name):
        app.lift()
        app.attributes('-topmost',True)
        for _ in range(8):
            app.update()
            time.sleep(.03)
        capture_hwnd(app.winfo_id(),output/(name+'.png'))
        app.attributes('-topmost',False)
    try:
        ctk.set_appearance_mode('Light')
        wait()
        capture('01-login-light')
        app.screen.username.insert(0,'admin')
        app.screen.password.insert(0,'fictional visual-test passphrase')
        app.screen.submit()
        wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        capture('02-dashboard-light')
        app.navigate('Driver Audits')
        wait(lambda:app.screen.loaded)
        app.screen.table.tree.selection_set('1')
        capture('03-audits-light')
        app.set_theme('Dark')
        wait(lambda:app.screen.loaded)
        capture('04-audits-dark')
        app.screen.table.tree.selection_set('1')
        app.screen.open_selected()
        wait(lambda:app.screen.loaded)
        capture('05-details-dark')
        app.screen.body._parent_canvas.yview_moveto(1)
        capture('05b-details-attribution-dark')
        app.set_theme('Light')
        app.navigate('Driver Audits')
        app.geometry('800x600+20+20')
        wait(lambda:app.screen.loaded)
        app.screen.toggle_filters()
        capture('06-compact-filters-light')
        transport.mode='offline'
        app.screen.refresh()
        wait(lambda:app.screen.last_error is not None)
        capture('07-offline-light')
        transport.mode='empty'
        app.screen.refresh()
        wait(lambda:app.screen.loaded)
        capture('08-empty-light')
        transport.mode='normal'
        transport.gate=Event()
        app.screen.refresh()
        capture('08b-loading-light')
        transport.gate.set()
        transport.gate=None
        wait(lambda:app.screen.loaded)
        for scale in (1.0,1.25,1.5):
            ctk.set_widget_scaling(scale)
            app.set_theme('Dark')
            app.geometry('1100x700+20+20')
            wait(lambda:app.screen.loaded)
            capture(f'09-widget-scale-{int(scale*100)}')
        ctk.set_widget_scaling(1.0)
        app.geometry(f'{width}x{height}+10+10')
        app.logout()
        app.screen.username.insert(0,'wrong')
        app.screen.password.insert(0,'fictional visual-test passphrase')
        app.screen.submit()
        wait(lambda:not app.screen.pending)
        capture('10-login-error-dark')
        app.screen.username.delete(0,'end')
        app.screen.username.insert(0,'admin2')
        app.screen.password.insert(0,'fictional visual-test passphrase')
        app.screen.submit()
        wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        capture('11-second-admin-dashboard-dark')
        metadata={'os_dpi':ctypes.windll.user32.GetDpiForWindow(app.winfo_id()),
                  'programmatic_widget_scales':[100,125,150],
                  'actual_display_scale_changed':False,'callback_errors':callback_errors,
                  'data':'fictional API transport; no database connections',
                  'screenshots':sorted(p.name for p in output.glob('*.png'))}
        (output/'verification.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        assert not callback_errors, callback_errors
        print(json.dumps(metadata))
    finally:
        app.close()


if __name__=='__main__':
    main()
