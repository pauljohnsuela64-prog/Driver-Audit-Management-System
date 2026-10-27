"""Composition and main-thread lifecycle. Network work is always delegated."""
from threading import Thread
import math
import time
import customtkinter as ctk

from desktop.api import ApiError
from desktop.components.common import StatePanel, destroy_view
from desktop.models import AuditQuery
from desktop.screens.login import LoginScreen
from desktop.screens.shell import Shell
from desktop.session import SessionState
from desktop.tasks import Tasks
from desktop.theme import color


class Application(ctk.CTk):
    def __init__(self,client):
        super().__init__()
        self.client=client
        self.session=SessionState()
        self.tasks=Tasks()
        self.revocations=Tasks(workers=1,capacity=8)
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
            remaining=max(0,math.ceil(self.retry_until-time.monotonic()))
            if self.shell and remaining!=self._retry_display:
                self.shell.notice.show(f'Too many requests. Retry available in {remaining}s.' if remaining else '',bool(remaining))
            self._retry_display=remaining
            if self.session.login and self.session.expired():
                self.logout('Your session expired. Please sign in again.')
        finally:
            # Report callback errors through Tk's handler, but keep completions and expiry alive.
            if not self.closing:
                self.after(30,self.poll)

    def show_login(self,message=''):
        if self.shell:
            destroy_view(self.shell)
            self.shell=None
        elif self.screen:
            destroy_view(self.screen)
        self.destination=''
        self.screen=LoginScreen(self,self,message)
        self.screen.pack(fill='both',expand=True)

    def sign_in(self,username,password,finished):
        client=self.client
        def accepted(result,error):
            if error:
                finished(None,error)
                return
            self.session.set(result)
            destroy_view(self.screen)
            self.shell=Shell(self,self)
            self.shell.pack(fill='both',expand=True)
            self.navigate('Dashboard')
        if not self.tasks.submit('login',lambda: client.sign_in(username,password),accepted,
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
                self.logout('Your session is no longer valid. Please sign in again.')
            else:
                if error and error.status==429:
                    self.retry_until=time.monotonic()+error.retry_after
                done(result,error)
        if not self.tasks.submit('screen',work,completed):
            done(None,ApiError(message='Requests are busy. Please try again shortly.'))

    def navigate(self,destination,audit_id=None):
        if not self.session.login:
            return
        if destination not in self.session.destinations and destination != 'Audit Details':
            return
        self.tasks.invalidate()
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

    def logout(self,message='Signed out. Please sign in to continue.'):
        old=self.session.clear()
        self.tasks.invalidate()
        self.query=AuditQuery()
        self.selected_id=None
        self.show_login(message)
        if old:
            self._revoke(old.token,notify=True)

    def set_theme(self,appearance):
        # CTk restores focus asynchronously after changing the Windows titlebar.
        # Capture the persistent root, never a screen that is about to be destroyed.
        self.focus_set()
        ctk.set_appearance_mode(appearance)
        if self.session.login:
            destination=self.destination
            audit_id=getattr(self.screen,'audit_id',None)
            self.tasks.invalidate()
            destroy_view(self.shell)
            self.screen=None
            self.shell=Shell(self,self)
            self.shell.pack(fill='both',expand=True)
            self.navigate(destination,audit_id)

    def escape(self,event=None):
        if self.shell and self.shell.menu.winfo_ismapped():
            self.shell.hide_menu()
        elif self.destination=='Audit Details':
            self.navigate('Driver Audits')

    def refresh(self):
        if hasattr(self.screen,'refresh'):
            self.screen.refresh()

    def focus_search(self):
        if hasattr(self.screen,'search'):
            self.screen.search.focus_set()
            return 'break'

    def close(self):
        if self.closing:
            return
        self.closing=True
        old=self.session.clear()
        self.tasks.close()
        self.revocations.close()
        if old:
            self._revoke(old.token)
        destroy_view(self)
