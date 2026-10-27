"""Real disposable API/native Windows Phase 3B workflows and visual evidence.

Run: python -m tests.desktop.audit_acceptance_capture
Fictional credentials remain in memory. No production configuration is read.
"""
import ctypes
import json
from pathlib import Path
import secrets
import time

import customtkinter as ctk
from desktop.api import ApiClient
from desktop.app import Application
from desktop.config import Config
from desktop.models import AuditQuery
from scripts.desktop_demo import demonstration
from tests.desktop.native_capture import capture as capture_hwnd


def main():
    output=Path('artifacts/desktop-phase3b');output.mkdir(parents=True,exist_ok=True)
    passwords=[secrets.token_urlsafe(24),secrets.token_urlsafe(24)]
    with demonstration(*passwords) as demo:
        client=ApiClient(Config(demo.origin));app=Application(client)
        errors=[];screens=[]
        app.tk.createcommand('audit_acceptance_bgerror',lambda message:errors.append(('Tcl',message)))
        app.tk.eval('proc bgerror {message} {audit_acceptance_bgerror $message}')
        app.report_callback_exception=lambda kind,value,tb:errors.append(kind.__name__)
        def wait(predicate=lambda:True):
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                app.update()
                if predicate():return
                time.sleep(.01)
            raise AssertionError(f'Native audit workflow did not settle: screen={app.destination}, '
                f'pending={app.mutation_pending}, draft_errors={list(app.draft.errors) if app.draft else []}, '
                f'uncertain={app.draft.uncertain if app.draft else False}, callbacks={errors}')
        def capture(name,dialog=False):
            app.lift();app.attributes('-topmost',True)
            if dialog and app.dialog:app.dialog.lift()
            for _ in range(8):app.update();time.sleep(.03)
            target=app.dialog if dialog else app
            capture_hwnd(target.winfo_id(),output/(name+'.png'))
            app.attributes('-topmost',False);screens.append(name)
        def login(username,password):
            app.screen.username.insert(0,username);app.screen.password.insert(0,password)
            app.screen.submit();wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        def field(key,value):
            widget=app.screen.inputs[key]
            if key=='remarks':widget.delete('1.0','end');widget.insert('1.0',value)
            else:widget.delete(0,'end');widget.insert(0,value)
        def reachable(widget):
            assert widget.winfo_rootx()>=app.winfo_rootx()
            assert widget.winfo_rooty()>=app.winfo_rooty()
            assert widget.winfo_rootx()+widget.winfo_width()<=app.winfo_rootx()+app.winfo_width()
            assert widget.winfo_rooty()+widget.winfo_height()<=app.winfo_rooty()+app.winfo_height()
        try:
            app.geometry('1280x760+10+10');app.set_theme('Light');wait()
            login('demo_auditor',passwords[1]);auditor_id=app.session.login.user.id
            app.open_create();wait();capture('01-create-light')
            app.screen.save();wait();assert app.draft.errors;capture('02-validation')
            for key,value in dict(driver_name='Fictional Desktop Driver',helper_name='',audit_date='2026-10-27',
                                  station='Fictional Desktop Station',plate_number='DEMO-NEW',
                                  remarks='Fictional remarks — optional, readable, and preserved.').items():field(key,value)
            app.set_theme('Dark');wait();assert app.screen.inputs['driver_name'].get()=='Fictional Desktop Driver'
            capture('03-create-dark')
            app.geometry('800x600');wait();reachable(app.screen.save_button);capture('04-create-compact')
            app.screen.save();wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            created=app.screen.record;assert created.audited_by_user_id==auditor_id
            capture('05-created-details')
            app.open_edit(created);wait(lambda:hasattr(app.screen,'inputs'))
            field('driver_name','Fictional Revised Driver');app.screen.save()
            wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            assert app.screen.record.driver_name=='Fictional Revised Driver'
            assert app.screen.record.audited_by_name=='Demo Auditor'
            app.navigate('Audit History',created.id);wait(lambda:app.screen.loaded)
            assert [event.action for event in app.screen.events.items]==['CREATE','UPDATE']
            capture('06-auditor-history')
            app.logout(force=True);wait();login('demo_admin',passwords[0])
            app.geometry('1200x760');app.set_theme('Light');wait(lambda:app.screen.loaded)
            app.navigate('Audit Details',created.id);wait(lambda:app.screen.loaded)
            app.open_edit(app.screen.record);wait(lambda:hasattr(app.screen,'inputs'))
            field('station','Fictional local draft')
            # A second authenticated client changes the same record while the form is open.
            other=ApiClient(Config(demo.origin));other_login=other.sign_in('demo_admin',passwords[0])
            fresh=other.get_audit(other_login.token,created.id)
            other.update_audit(other_login.token,created.id,{'remarks':'Fictional concurrent edit'},fresh.etag)
            app.screen.save();wait(lambda:app.draft is not None and app.draft.latest is not None)
            app.screen.body._parent_canvas.yview_moveto(1);wait();capture('07-edit-conflict')
            app.screen.reapply();wait();app.screen.save()
            wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            assert app.screen.record.remarks=='Fictional concurrent edit'
            app.confirm_delete(app.screen.record);wait(lambda:app.dialog is not None);capture('08-delete-confirmation',True)
            app.dialog.cancel();wait();assert app.screen.record.deleted_at is None
            app.confirm_delete(app.screen.record);wait(lambda:app.dialog is not None);app.dialog.accept()
            wait(lambda:app.destination=='Driver Audits' and app.screen.loaded)
            app.screen.toggle_filters();app.screen.include_deleted.select();app.screen.apply()
            wait(lambda:app.screen.loaded);assert app.query.include_deleted
            capture('09-admin-including-deleted')
            app.navigate('Audit Details',created.id);wait(lambda:app.screen.loaded)
            assert app.screen.record.deleted_at;capture('10-deleted-details')
            app.navigate('Audit History',created.id);wait(lambda:app.screen.loaded)
            assert [event.action for event in app.screen.events.items]==['CREATE','UPDATE','UPDATE','UPDATE','DELETE']
            app.screen.select(app.screen.events.items[-1]);wait();capture('11-delete-history-light')
            app.set_theme('Dark');wait(lambda:app.screen.loaded)
            app.screen.select(app.screen.events.items[-1]);wait();capture('12-delete-history-dark')
            app.state('zoomed');wait();capture('13-history-maximized')
            for factor in (1.0,1.25,1.5):
                ctk.set_widget_scaling(factor);wait();reachable(app.screen.next)
            ctk.set_widget_scaling(1.0)
            other.logout(other_login.token)
            assert not errors,errors
            report={'screenshots':screens,'callback_errors':errors,'display_dpi':ctypes.windll.user32.GetDpiForWindow(app.winfo_id()),
                    'simulated_widget_scaling':[1.0,1.25,1.5],'actual_other_monitor_dpi':'not tested',
                    'workflows':'create, edit, conflict/reapply, cancel/delete, deleted history, both roles/themes, compact/maximized'}
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
        finally:
            if not app.closing:app.close(force=True)


if __name__=='__main__':main()
