"""Phase 3C native Windows acceptance against the real disposable API.

Run python -m tests.desktop.admin_acceptance_capture. All credentials are
generated in memory; screenshots contain fictional data and empty password forms.
"""
import ctypes
import json
from pathlib import Path
import secrets
import time
from dataclasses import replace
from tkinter import ttk
import customtkinter as ctk

from desktop.api import ApiClient,ApiError
from desktop.app import Application
from desktop.config import Config
from desktop.components.table import AuditTable
from scripts.desktop_demo import demonstration
from tests.desktop.native_capture import capture as capture_hwnd


def main():
    output=Path('artifacts/desktop-phase3c');output.mkdir(parents=True,exist_ok=True)
    first_password,second_password=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
    with demonstration(first_password,second_password) as demo:
        client=ApiClient(Config(demo.origin));app=Application(client);screens=[];errors=[]
        app.tk.createcommand('phase3c_bgerror',lambda message:errors.append('TclError'))
        app.tk.eval('proc bgerror {message} {phase3c_bgerror $message}')
        app.report_callback_exception=lambda kind,value,tb:errors.append(kind.__name__)
        def wait(predicate=lambda:True):
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                app.update()
                if predicate():return
                time.sleep(.01)
            raise AssertionError(f'Native acceptance did not settle: {app.destination}; callbacks={errors}')
        def capture(name,dialog=False):
            app.lift();app.attributes('-topmost',True)
            if dialog:app.dialog.lift()
            for _ in range(8):app.update();time.sleep(.03)
            capture_hwnd((app.dialog if dialog else app).winfo_id(),output/(name+'.png'))
            app.attributes('-topmost',False);screens.append(name)
        def login(name,password):
            app.screen.username.insert(0,name);app.screen.password.insert(0,password);app.screen.submit()
            wait(lambda:app.session.login is not None and getattr(app.screen,'loaded',False))
        def ready_account():return app.destination=='My Account' and app.screen.loaded and not app.screen.busy()
        def accounts():
            app.navigate('My Account');wait(ready_account)
            app.screen.toggle_manage();wait(ready_account)
        def fill_account(values):
            for key,value in values.items():app.screen.form.fields[key].insert(0,value)
        def table(widget):
            if isinstance(widget,AuditTable):return widget
            for child in widget.winfo_children():
                result=table(child)
                if result:return result
        try:
            app.geometry('1280x760+10+10');app.set_theme('Light');wait()
            app.screen.username.insert(0,'demo_auditor');app.screen.password.insert(0,demo.legacy_password)
            app.screen.submit();wait(lambda:not app.screen.pending)
            assert app.session.login is None and app.shell is None
            capture('01-legacy-auditor-rejected')
            app.screen.username.delete(0,'end');login('demo_admin',first_password)
            assert tuple(app.shell.nav_buttons)==('Dashboard','Driver Audits','My Account')
            capture('02-dashboard-light')
            app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            assert not app.screen.options.winfo_ismapped()
            audit_table=table(app.screen);style=ttk.Style(app)
            density={'rowheight_device_px':int(style.lookup('BHLI.Treeview','rowheight')),
                     'heading_padding_device_px':str(style.lookup('BHLI.Treeview.Heading','padding')),
                     'widget_scale':audit_table._get_widget_scaling()}
            assert density['rowheight_device_px']==round(38*density['widget_scale'])
            capture('03-audits-light-compact-rows')
            app.set_theme('Dark');wait(lambda:app.screen.loaded);capture('04-audits-dark')
            app.geometry('800x600')
            for _ in range(8):app.update();time.sleep(.03)
            assert app.shell.collapsed;capture('05-compact-navigation')
            app.state('zoomed');wait();capture('06-maximized-audits')
            app.state('normal');app.geometry('1100x760');app.set_theme('Light');wait(lambda:app.screen.loaded)
            accounts();assert len(app.screen.admins)==2;capture('07-minimal-admin-accounts')
            app.screen.open_form('add');wait();capture('08-add-admin-empty-form')
            third_password=secrets.token_urlsafe(24)
            fill_account(dict(username='demo_third',full_name='Fictional Third Administrator',password=third_password,confirm_password=third_password))
            app.screen.form.submit();wait(ready_account)
            assert len(app.screen.admins)==3
            target=next(user for user in app.screen.admins if user.username=='demo_third')
            capture('09-third-admin-added-no-account-limit')
            probe=ApiClient(Config(demo.origin));old_session=probe.sign_in('demo_third',third_password)
            app.screen.open_target('reset',target);wait(lambda:app.screen.form is not None)
            capture('10-reset-empty-reauthentication-form')
            replacement=secrets.token_urlsafe(24)
            fill_account(dict(admin_password=first_password,new_password=replacement,confirm_password=replacement))
            app.screen.form.submit();wait(ready_account)
            try:probe.me(old_session.token);raise AssertionError('Old session survived reset')
            except ApiError as error:assert error.status==401
            renewed=probe.sign_in('demo_third',replacement);probe.logout(renewed.token)
            app.screen.open_target('disable',target);wait(lambda:app.dialog is not None)
            capture('11-disable-confirmation',True);app.dialog.accept();wait(ready_account)
            assert not next(user for user in app.screen.admins if user.id==target.id).is_active
            capture('12-disabled-admin-status')
            app.screen.open_form('change');wait()
            changed_password=secrets.token_urlsafe(24)
            fill_account(dict(current_password=first_password,new_password=changed_password,confirm_password=changed_password))
            app.screen.form.submit();wait(lambda:app.session.login is None)
            capture('13-own-change-requires-login')
            login('demo_admin2',second_password);second_id=app.session.login.user.id;capture('14-second-admin-dashboard')
            app.open_create();wait()
            for key,value in dict(driver_name='Fictional Phase 3C Driver',audit_date='2026-10-27',
                                  station='Fictional HR Station',plate_number='DEMO-HR').items():
                app.screen.inputs[key].delete(0,'end');app.screen.inputs[key].insert(0,value)
            app.screen.save();wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            record=app.screen.record;assert record.audited_by_user_id==second_id
            app.open_edit(record);wait(lambda:hasattr(app.screen,'inputs'))
            app.screen.inputs['remarks'].insert('1.0','Fictional edited notes. Original owner is preserved.')
            app.screen.save();wait(lambda:app.destination=='Audit Details' and app.screen.loaded)
            assert app.screen.record.audited_by_name=='Demo Administrator Two'
            app.navigate('Audit History',record.id);wait(lambda:app.screen.loaded)
            assert app.screen.events.total==2;capture('15-separate-admin-audit-history')
            app.navigate('Audit Details',record.id);wait(lambda:app.screen.loaded)
            app.confirm_delete(app.screen.record);wait(lambda:app.dialog is not None);app.dialog.accept()
            wait(lambda:app.destination=='Driver Audits' and app.screen.loaded)
            app.query=replace(app.query,include_deleted=True);app.navigate('Audit Details',record.id)
            wait(lambda:app.screen.loaded);app.navigate('Audit History',record.id);wait(lambda:app.screen.loaded)
            assert app.screen.events.total==3
            app.screen.select(app.screen.events.items[-1]);wait();app.screen.body._parent_canvas.yview_moveto(1)
            capture('16-deleted-history-preserved')
            app.set_theme('Dark');wait(lambda:app.screen.loaded);accounts();capture('17-my-account-dark')
            app.navigate('Driver Audits');wait(lambda:app.screen.loaded)
            for factor in (1.0,1.25,1.5):
                ctk.set_widget_scaling(factor)
                for _ in range(6):app.update();time.sleep(.03)
                current=table(app.screen)
                assert int(ttk.Style(app).lookup('BHLI.Treeview','rowheight'))==round(38*current._get_widget_scaling())
            ctk.set_widget_scaling(1.0)
            assert not errors,errors
            report={'screenshots':screens,'callback_errors':errors,'actual_dpi':ctypes.windll.user32.GetDpiForWindow(app.winfo_id()),
                    'density':density,'simulated_widget_factors':[1.0,1.25,1.5],
                    'other_OS_DPI_and_mixed_monitors':'not tested','accounts':'two individual ADMINs plus hidden legacy test account; third admin added/reset/disabled',
                    'workflow':'ADMIN admission, legacy rejection, separate attribution, create/edit/delete/history, account safeguards, theme/resize/keyboard metrics'}
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
        finally:
            if not app.closing:app.close(force=True)


if __name__=='__main__':main()
