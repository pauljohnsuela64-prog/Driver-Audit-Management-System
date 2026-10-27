"""Composition and main-thread lifecycle. Network work is always delegated."""
from threading import Thread
import math
import time
import customtkinter as ctk

from desktop.api import ApiError
from desktop.components.common import StatePanel, destroy_view
from desktop.models import AuditQuery
from desktop.lifecycle import UiCollector
from desktop.screens.login import LoginScreen
from desktop.screens.shell import Shell
from desktop.session import SessionState
from desktop.tasks import Tasks
from desktop.theme import color


class Application(ctk.CTk):
    def __init__(self,client):
        self.collector=UiCollector()
        try:
            super().__init__()
        except BaseException:
            self.collector.close()
            raise
        self.client=client
        self.session=SessionState()
        self.tasks=Tasks()
        self.revocations=Tasks(workers=1,capacity=8)
        self.mutations=Tasks(workers=1,capacity=1)
        self.mutation_pending=False
        self.draft=None
        self.account_action=None
        self.dialog=None
        self.revocation_serial=0
        self.retry_until=0
        self._retry_display=0
        self.closing=False
        self.shell=None
        self.screen=None
        self.destination=''
        self.query=AuditQuery()
        self.selected_id=None
        self.title('BHLI Audit')
        scale=self._get_window_scaling()
        width,height=min(1280,int(self.winfo_screenwidth()/scale)-40),min(800,int(self.winfo_screenheight()/scale)-80)
        self.geometry(f'{width}x{height}')
        self.minsize(min(800,width),min(600,height))
        self.configure(fg_color=color('bg'))
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Escape>',self.escape)
        self.bind('<F5>',lambda e=None: self.refresh())
        self.bind('<Control-f>',lambda e=None: self.focus_search())
        self.show_login()
        self.after(30,self.poll)

    def report_callback_exception(self,exc,val,tb):
        # Tk's default handler prints exception inputs and may leak private data.
        if self.shell:
            self.shell.notice.show('The interface could not complete this action. Try refreshing.')
        elif self.screen and hasattr(self.screen,'status'):
            self.screen.status.show('The interface could not complete this action. Please try again.')

    def poll(self):
        if self.closing:
            return
        try:
            self.tasks.drain()
            self.revocations.drain()
            self.mutations.drain()
            self.collector.poll()
            remaining=max(0,math.ceil(self.retry_until-time.monotonic()))
            if self.shell and remaining!=self._retry_display:
                self.shell.notice.show(f'Too many requests. Retry available in {remaining}s.' if remaining else '',bool(remaining))
            self._retry_display=remaining
            if self.session.login and self.session.expired():
                self.logout('Your session expired. Please sign in again.',force=True)
        finally:
            # Report callback errors through Tk's handler, but keep completions and expiry alive.
            if not self.closing:
                self.after(30,self.poll)

    def show_login(self,message=''):
        if self.screen and hasattr(self.screen,'on_leave'):self.screen.on_leave()
        if self.shell:
            destroy_view(self.shell)
            self.shell=None
        elif self.screen:
            destroy_view(self.screen)
        self.destination=''
        self.screen=LoginScreen(self,self,message)
        self.screen.pack(fill='both',expand=True)

    def sign_in(self,username,password,finished):
        from desktop.account_operations import desktop_sign_in
        client=self.client
        def accepted(result,error):
            if error:
                finished(None,error)
                return
            if result.user.role!='ADMIN':
                self._revoke(result.token)
                finished(None,ApiError(403,message='This Windows application requires an HR administrator account.'))
                return
            self.session.set(result)
            destroy_view(self.screen)
            self.shell=Shell(self,self)
            self.shell.pack(fill='both',expand=True)
            self.navigate('Dashboard',force=True)
        if not self.tasks.submit('login',lambda: desktop_sign_in(client,username,password),accepted,
                                 lambda result: client.logout(result.token)):
            finished(None,ApiError(message='Requests are busy. Please try again.'))

    def request(self,work,done):
        remaining=max(0,math.ceil(self.retry_until-time.monotonic()))
        if remaining:
            done(None,ApiError(429,retry_after=remaining))
            return
        generation=self.session.generation
        def completed(result,error):
            if generation != self.session.generation:
                return
            if error and error.status == 401:
                self.logout('Your session is no longer valid. Please sign in again.',force=True)
            else:
                if error and error.status==429:
                    self.retry_until=time.monotonic()+error.retry_after
                done(result,error)
        if not self.tasks.submit('screen',work,completed):
            done(None,ApiError(message='Requests are busy. Please try again shortly.'))

    def navigate(self,destination,audit_id=None,force=False):
        if not self.session.login:
            return
        if self.session.login.user.role!='ADMIN':
            self.logout('This Windows application requires an HR administrator account.',force=True)
            return
        if destination not in self.session.destinations and destination not in ('Audit Details','Create Audit','Edit Audit','Audit History'):
            return
        if not force and not self.leave_form(lambda:self.navigate(destination,audit_id,force=True)):
            return
        self.tasks.invalidate()
        if self.screen and hasattr(self.screen,'on_leave'):self.screen.on_leave()
        if self.screen and self.screen.winfo_exists():
            destroy_view(self.screen)
        self.destination=destination
        self.shell.select(destination)
        # Feature screens are imported lazily; the shell stays independent of their widgets.
        if destination == 'Dashboard':
            from desktop.screens.dashboard import Dashboard
            factory=lambda: Dashboard(self.shell.content,self)
        elif destination == 'Driver Audits':
            from desktop.screens.audits import Audits
            factory=lambda: Audits(self.shell.content,self)
        elif destination == 'Audit Details':
            from desktop.screens.details import Details
            factory=lambda: Details(self.shell.content,self,audit_id)
        elif destination in ('Create Audit','Edit Audit') and self.draft is not None:
            from desktop.screens.audit_form import AuditForm
            factory=lambda: AuditForm(self.shell.content,self,self.draft)
        elif destination == 'Audit History':
            from desktop.screens.audit_history import AuditHistory
            factory=lambda: AuditHistory(self.shell.content,self,audit_id)
        elif destination == 'My Account':
            from desktop.screens.account import Account
            factory=lambda: Account(self.shell.content,self)
        else:
            factory=lambda: StatePanel(self.shell.content,destination,'Coming in a later phase. This module is not implemented yet.')
        self.screen=factory()
        self.screen.pack(fill='both',expand=True)
        if hasattr(self.screen,'search'):
            self.screen.search.focus_set()
        else:
            self.screen.focus_set()

    def _revoke(self,token,notify=False):
        client=self.client
        def work():
            error=None
            try:
                client.logout(token)
            except Exception:
                error=ApiError(message='Signed out locally. Server revocation could not be confirmed; the session may remain until expiry.')
            if notify:
                # Worker touches only the completion queue, never Tk.
                return error
        if notify:
            self.revocation_serial+=1
            if not self.revocations.submit(str(self.revocation_serial),work,
                lambda error,_: self.screen.status.show(str(error)) if error and not self.session.login and hasattr(self.screen,'status') else None):
                self.screen.status.show('Signed out locally. Server revocation could not be queued; the session may remain until expiry.')
        else:
            Thread(target=work,daemon=True,name='bhli-signout').start()

    def logout(self,message='Signed out. Please sign in to continue.',force=False,revoke=True):
        if not force and not self.leave_form(lambda:self.logout(message,force=True),allow_pending=True):
            return
        if self.dialog:
            self.dialog.dismiss()
        old=self.session.clear()
        self.account_action=None
        self.draft=None
        self.tasks.invalidate()
        self.query=AuditQuery()
        self.selected_id=None
        self.show_login(message)
        if old and revoke:
            self._revoke(old.token,notify=True)

    def set_theme(self,appearance):
        # CTk restores focus asynchronously after changing the Windows titlebar.
        # Capture the persistent root, never a screen that is about to be destroyed.
        self.focus_set()
        ctk.set_appearance_mode(appearance)
        if self.session.login:
            if hasattr(self.screen,'capture'):
                self.screen.capture()
            destination=self.destination
            audit_id=getattr(self.screen,'audit_id',None)
            self.tasks.invalidate()
            if self.screen and hasattr(self.screen,'on_leave'):self.screen.on_leave()
            destroy_view(self.shell)
            self.screen=None
            self.shell=Shell(self,self)
            self.shell.pack(fill='both',expand=True)
            self.navigate(destination,audit_id,force=True)

    def escape(self,event=None):
        if self.shell and self.shell.menu.winfo_ismapped():
            self.shell.hide_menu()
        elif self.destination in ('Audit Details','Create Audit','Edit Audit','Audit History'):
            self.navigate('Driver Audits')

    def refresh(self):
        if hasattr(self.screen,'refresh'):
            self.screen.refresh()

    def focus_search(self):
        if hasattr(self.screen,'search'):
            self.screen.search.focus_set()
            return 'break'

    def close(self,force=False):
        if self.closing:
            return
        if not force and not self.leave_form(lambda:self.close(force=True),allow_pending=True):
            return
        if self.dialog:
            self.dialog.dismiss()
        self.closing=True
        if self.screen and hasattr(self.screen,'on_leave'):self.screen.on_leave()
        old=self.session.clear()
        self.tasks.close()
        self.revocations.close()
        self.mutations.close()
        self.draft=None
        if old:
            self._revoke(old.token)
        destroy_view(self)
        # Detached views contain widget/font/image cycles. Release and collect them
        # here, on Tk's owner thread, before a later API worker allocation runs GC.
        self.screen=None
        self.shell=None
        self.collector.close()

    def leave_form(self,accepted,allow_pending=False):
        from desktop.components.audit_dialogs import confirm
        if self.mutation_pending and not allow_pending:
            self.shell.notice.show('Wait for the submitted operation to finish before navigating.')
            return False
        if self.draft:
            if hasattr(self.screen,'capture'):
                self.screen.capture()
            if self.draft.dirty:
                def discard():
                    self.draft=None
                    accepted()
                message=('A request has been sent and may commit even after leaving. Its result cannot be undone by closing or signing out. '
                         if self.draft.pending else
                         'The last creation may already exist. Leaving loses its safe retry key. ' if self.draft.uncertain else '')
                confirm(self,'Leave this audit?',message+'Unsaved form data will be discarded.',discard,'Leave and discard')
                return False
            self.draft=None
        elif self.mutation_pending and allow_pending:
            confirm(self,'Leave a pending operation?',
                    'A request has been sent and may commit after leaving. Inspect the record after signing in again.',
                    accepted,'Leave anyway')
            return False
        return True

    def open_create(self):
        from datetime import date
        from desktop.audit_operations import AuditDraft,FIELDS
        def open_form():
            self.draft=AuditDraft({key:date.today().isoformat() if key=='audit_date' else '' for key in FIELDS})
            self.navigate('Create Audit',force=True)
        if self.leave_form(open_form):
            open_form()

    def open_edit(self,record):
        from desktop.audit_operations import AuditDraft,record_values,can_edit
        user=self.session.login.user
        if not can_edit(record,user.id,user.role):
            self.shell.notice.show('You may edit only your own active audits.')
            return
        def load():
            client,token,audit_id=self.client,self.session.login.token,record.id
            def loaded(latest,error):
                if error:
                    self.audit_unavailable(audit_id,error)
                    self.shell.notice.show(str(error));return
                if not can_edit(latest,self.session.login.user.id,self.session.login.user.role):
                    self.shell.notice.show('You no longer have permission to edit this audit.');return
                self.draft=AuditDraft(record_values(latest),baseline=latest)
                self.navigate('Edit Audit',force=True)
            self.request(lambda:client.get_audit(token,audit_id),loaded)
        if self.leave_form(load):
            load()

    def render_draft(self):
        if self.draft and getattr(self.screen,'draft',None) is self.draft:
            self.screen.render_state()

    def rebuild_form(self):
        self.navigate('Edit Audit' if self.draft.baseline else 'Create Audit',force=True)

    def mutate(self,work,done):
        remaining=max(0,math.ceil(self.retry_until-time.monotonic()))
        if self.mutation_pending or remaining:
            done(None,ApiError(429,retry_after=remaining) if remaining else ApiError(message='An operation is already in progress.'))
            return
        generation=self.session.generation
        self.mutation_pending=True
        def completed(result,error):
            self.mutation_pending=False
            if generation!=self.session.generation or not self.session.login:
                # Release current-view controls, without delivering any obsolete
                # operation result or data from another account's session.
                if self.session.login and self.destination=='My Account':
                    self.screen.render_action()
                    self.screen.refresh()
                return
            if error and error.status==401:
                self.logout('Your session is no longer valid. A submitted operation may have completed; inspect records after signing in.',force=True)
                return
            if error and error.status==429:
                self.retry_until=time.monotonic()+error.retry_after
            done(result,error)
        if not self.mutations.submit('mutation',work,completed):
            self.mutation_pending=False
            done(None,ApiError(message='Requests are busy. No new operation was queued.'))

    def confirm_delete(self,record):
        from desktop.audit_actions import confirm_delete
        confirm_delete(self,record)

    def audit_unavailable(self,audit_id,error):
        if error.status in (403,404) and self.destination=='Audit Details' and getattr(self.screen,'audit_id',None)==audit_id:
            self.screen.finished(None,error)
