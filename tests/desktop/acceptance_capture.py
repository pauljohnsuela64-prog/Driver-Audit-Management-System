"""Repeatable Windows acceptance using the real disposable API, no auth bypass.

Run: python -m tests.desktop.acceptance_capture
Passwords are generated in memory, never printed or saved.
"""
import ctypes
import json
from pathlib import Path
import secrets
import socket
from threading import Event
import time

import customtkinter as ctk
from desktop.api import ApiClient
from desktop.app import Application
from desktop.config import Config
from scripts.desktop_demo import demonstration
from tests.desktop.native_capture import capture as capture_hwnd


def main():
    output=Path('artifacts/desktop-acceptance')
    output.mkdir(parents=True,exist_ok=True)
    admin_password,auditor_password=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
    with demonstration(admin_password,auditor_password) as demo:
        client=ApiClient(Config(demo.origin))
        app=Application(client)
        errors=[]
        app.tk.createcommand('acceptance_bgerror',lambda message:errors.append(('Tcl',message)))
        app.tk.eval('proc bgerror {message} {acceptance_bgerror $message}')
        app.report_callback_exception=lambda kind,value,tb:errors.append((kind.__name__,str(value)))
        scale=app._get_window_scaling()
        width=min(1280,int(app.winfo_screenwidth()/scale)-40)
        height=min(760,int(app.winfo_screenheight()/scale)-80)
        def wait(predicate=lambda:True):
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                app.update()
                if predicate():
                    return
                time.sleep(.01)
            raise AssertionError('Acceptance screen did not settle')
        def capture(name):
            app.lift()
            app.attributes('-topmost',True)
            for _ in range(8):
                app.update()
                time.sleep(.03)
            capture_hwnd(app.winfo_id(),output/(name+'.png'))
            app.attributes('-topmost',False)
        def login(username,password):
            app.screen.username.delete(0,'end')
            app.screen.username.insert(0,username)
            app.screen.password.insert(0,password)
            app.screen.submit()
            wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        def reachable(widget):
            assert widget.winfo_rootx()>=app.winfo_rootx()
            assert widget.winfo_rooty()>=app.winfo_rooty()
            assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+app.winfo_width()
            assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+app.winfo_height()
        try:
            app.geometry(f'{width}x{height}+10+10')
            app.set_theme('Light')
            wait()
            capture('01-login-light')
            app.screen.username.insert(0,'demo_admin')
            app.screen.password.insert(0,'intentionally incorrect fictional password')
            app.screen.submit()
            wait(lambda:not app.screen.pending)
            assert app.session.login is None
            capture('02-incorrect-login')
            login('demo_admin',admin_password)
            assert app.screen.total==60
            capture('03-admin-dashboard')
            app.navigate('Driver Audits')
            wait(lambda:app.screen.loaded)
            app.shell.set_collapsed(False)
            capture('04-audits-expanded')
            assert len(app.screen.table.tree.get_children())==25
            app.screen.page(1)
            wait(lambda:app.screen.loaded)
            assert app.query.page==2
            capture('05-second-page')
            app.screen.sort.set('Audit date ↑')
            app.screen.apply()
            wait(lambda:app.screen.loaded)
            assert app.query.page==1 and app.query.sort=='audit_date'
            tree=app.screen.table.tree
            selected=tree.get_children()[0]
            tree.selection_set(selected)
            tree.focus(selected)
            app.focus_force()
            tree.focus_set()
            tree.event_generate('<Return>')
            wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            assert app.screen.record.audited_by_name=='Fictional Auditor (original)'
            capture('06-details-top')
            app.screen.body._parent_canvas.yview_moveto(1)
            capture('07-details-original-attribution')
            app.event_generate('<Escape>')
            wait(lambda:app.destination=='Driver Audits' and app.screen.loaded)
            assert app.focus_get() is app.screen.table.tree
            app.set_theme('Dark')
            wait(lambda:app.screen.loaded)
            capture('08-audits-dark')
            app.shell.set_collapsed(True)
            capture('09-collapsed-dark')
            app.geometry('800x600+10+10')
            app.screen.toggle_filters()
            wait()
            for widget in (app.screen.apply_button,app.screen.previous,app.screen.next,app.screen.detail_button):
                reachable(widget)
            capture('10-compact-filters')
            app.state('zoomed')
            wait()
            for _ in range(10):
                app.update()
                time.sleep(.03)
            assert app.state()=='zoomed'
            capture('11-maximized')
            app.state('normal')
            app.geometry(f'{width}x{height}+10+10')
            app.navigate('Driver Audits')
            wait(lambda:app.screen.loaded)
            gate=Event()
            base_transport=client.transport
            def delayed(method,path,headers,body):
                if path.startswith('/audits?'):
                    gate.wait(5)
                return base_transport(method,path,headers,body)
            client.transport=delayed
            app.screen.refresh()
            capture('12-loading-real-api')
            gate.set()
            wait(lambda:app.screen.loaded)
            client.transport=base_transport
            with socket.socket() as offline:
                offline.bind(('127.0.0.1',0))  # Bound, never listening: no other process can receive this request.
                app.client=ApiClient(Config(f'http://127.0.0.1:{offline.getsockname()[1]}'))
                app.screen.refresh()
                wait(lambda:app.screen.last_error is not None)
                capture('13-offline')
            app.client=client
            app.screen.search.insert(0,'NO-FICTIONAL-RECORD-MATCHES')
            app.screen.apply()
            wait(lambda:app.screen.loaded)
            assert app.screen.total==0
            capture('14-empty-real-api')
            app.logout()
            login('demo_auditor',auditor_password)
            assert 'Employee Accounts' not in app.shell.nav_buttons
            capture('15-auditor-dashboard')
            app.navigate('Driver Audits')
            wait(lambda:app.screen.loaded)
            app.screen.mine.select()
            app.screen.apply()
            wait(lambda:app.screen.loaded)
            assert app.screen.total==40
            capture('16-auditor-own-records')
            for factor in (1.0,1.25,1.5):
                ctk.set_widget_scaling(factor)
                app.set_theme('Dark')
                app.geometry('1100x650+10+10')
                wait(lambda:app.screen.loaded)
                capture(f'17-widget-factor-{int(factor*100)}')
            metadata={'actual_dpi':ctypes.windll.user32.GetDpiForWindow(app.winfo_id()),
                'data':'Real FastAPI HTTP + disposable SQLite; 60 fictional audits, 40 auditor-owned',
                'authentication':'Normal API authentication; generated passwords never saved',
                'maximized_checked':True,'keyboard_back_focus_checked':True,
                'widget_factors':[100,125,150],'os_display_scale_changed':False,'callback_errors':errors,
                'screenshots':sorted(p.name for p in output.glob('*.png'))}
            assert not errors,errors
            (output/'verification.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
            print(json.dumps(metadata))
        finally:
            app.close()
    assert not demo.database_file.parent.exists()


if __name__=='__main__':
    main()
