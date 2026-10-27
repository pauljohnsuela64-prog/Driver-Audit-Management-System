"""Native Excel-export acceptance using the disposable fictional REST demo."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import ctypes
import json
import secrets
import time
import customtkinter as ctk

from desktop.api import ApiClient
from desktop.app import Application
from desktop.config import Config
from desktop.reports import Destination
from scripts.desktop_demo import demonstration
from tests.desktop.native_capture import capture


def main():
    output=Path('artifacts/desktop-phase3d').absolute();output.mkdir(parents=True,exist_ok=True)
    passwords=(secrets.token_urlsafe(24),secrets.token_urlsafe(24))
    with demonstration(*passwords) as demo:
        client=ApiClient(Config(demo.origin));app=Application(client);errors=[];screens=[]
        app.report_callback_exception=lambda kind,value,tb:errors.append(kind.__name__)
        app.tk.createcommand('export_bgerror',lambda message:errors.append('TclError'))
        app.tk.eval('proc bgerror {message} {export_bgerror $message}')
        def wait(predicate=lambda:True):
            end=time.monotonic()+12
            while time.monotonic()<end:
                app.update()
                if predicate():return
                time.sleep(.01)
            raise AssertionError('Native export did not settle')
        def shot(name,dialog=False):
            app.lift();app.attributes('-topmost',True)
            if dialog:app.dialog.lift()
            for _ in range(6):app.update();time.sleep(.04)
            capture((app.dialog if dialog else app).winfo_id(),output/(name+'.png'))
            app.attributes('-topmost',False);screens.append(name)
        def login(index):
            app.screen.username.insert(0,'demo_admin' if index==0 else 'demo_admin2')
            app.screen.password.insert(0,passwords[index]);app.screen.submit()
            wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        original=client.list_audits;release=Event()
        try:
            app.geometry('1280x800+10+10');app.set_theme('Light');login(0)
            app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            shot('01-export-light')
            app.screen.export_button.invoke();wait(lambda:app.dialog is not None)
            shot('02-filter-confirmation',True);app.dialog.cancel()
            entered=Event()
            def delayed(token,q):
                if q.page_size==100:entered.set();release.wait(20)
                return original(token,q)
            client.list_audits=delayed
            path=output/'fictional-audits.xlsx'
            # Acceptance reruns use unique names; never overwrite another workbook.
            if path.exists():path=output/f'fictional-audits-{time.time_ns()}.xlsx'
            app.export_job.start(app.query,Destination.capture(path));wait(entered.is_set)
            shot('03-background-progress')
            app.navigate('Dashboard');wait(lambda:app.screen.loaded);assert app.export_job.pending
            app.set_theme('Dark');app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            shot('04-navigation-and-dark-progress')
            release.set();wait(lambda:not app.export_job.pending)
            assert app.export_job.result.count==60 and path.exists()
            shot('05-export-saved-dark')
            app.geometry('800x600');wait();shot('06-compact-export')
            app.state('zoomed');wait();shot('07-maximized-export')
            app.state('normal');app.geometry('1100x760');app.set_theme('Light');wait(lambda:app.screen.loaded)
            app.screen.search.insert(0,'unapplied');app.screen.export_button.invoke()
            shot('08-unapplied-filter-warning')
            app.screen.clear();wait(lambda:app.screen.loaded)
            client.list_audits=original
            app.query=replace(app.query,include_deleted=True)
            app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            archived=output/f'fictional-with-archived-{time.time_ns()}.xlsx'
            app.export_job.start(app.query,Destination.capture(archived));wait(lambda:not app.export_job.pending)
            assert app.export_job.result.count==61
            shot('09-archived-export-saved')
            # Keyboard activation and cancellation use the real widget bindings.
            app.screen.export_button.focus_set();app.screen.export_button.event_generate('<Return>')
            wait(lambda:app.dialog is not None);app.dialog.event_generate('<Escape>');wait(lambda:app.dialog is None)
            app.logout(force=True);wait(lambda:app.session.login is None);login(1)
            app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            app.screen.toggle_filters();app.screen.mine.select();app.screen.apply();wait(lambda:app.screen.loaded)
            mine=output/f'second-admin-owned-{time.time_ns()}.xlsx'
            app.export_job.start(app.query,Destination.capture(mine));wait(lambda:not app.export_job.pending)
            assert app.export_job.result.count==40;shot('10-second-admin-owned-export')
            report=dict(screens=screens,callback_errors=errors,active_workbook=str(path),
                archived_workbook=str(archived),second_admin_workbook=str(mine),active_rows=60,archived_rows=61,
                second_admin_rows=40,dpi=ctypes.windll.user32.GetDpiForWindow(app.winfo_id()),
                widget_scale=app.screen._get_widget_scaling(),keyboard_activation_and_escape=True)
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            assert not errors
            print(json.dumps(report))
        finally:
            release.set();app.close(force=True)


if __name__=='__main__':main()
