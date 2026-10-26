"""Composition and main-thread lifecycle. Network work is always delegated."""
from threading import Thread
import customtkinter as ctk

from desktop.api import ApiError
from desktop.components.common import StatePanel, label
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
        self.state=SessionState()
        self.tasks=Tasks()
        self.closing=False
        self.shell=None
        self.screen=None
        self.destination=''
        self.query=AuditQuery()
        self.selected_id=None
        self.title('BHLI Audit')
        width,height=min(1280,self.winfo_screenwidth()-40),min(800,self.winfo_screenheight()-80)
        self.geometry(f'{width}x{height}')
        self.minsize(min(800,width),min(600,height))
        self.configure(fg_color=color('bg'))
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Escape>',self.escape)
        self.bind('<F5>',lambda e: self.refresh())
        self.bind('<Control-f>',lambda e: self.focus_search())
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
        self.tasks.drain()
        if self.state.login and self.state.expired():
            self.logout('Your session expired. Please sign in again.')
        self.after(30,self.poll)

    def show_login(self,message=''):
        if self.shell:
            self.shell.destroy()
            self.shell=None
        elif self.screen:
            self.screen.destroy()
        self.destination=''
        self.screen=LoginScreen(self,self,message)
        self.screen.pack(fill='both',expand=True)

    def sign_in(self,username,password,finished):
        client=self.client
        def accepted(result,error):
            if error:
                finished(None,error)
                return
            self.state.set(result)
            self.screen.destroy()
            self.shell=Shell(self,self)
            self.shell.pack(fill='both',expand=True)
            self.navigate('Dashboard')
        if not self.tasks.submit('login',lambda: client.sign_in(username,password),accepted,
                                 lambda result: client.logout(result.token)):
            finished(None,ApiError(message='Requests are busy. Please try again.'))

    def request(self,work,done):
        generation=self.state.generation
        def completed(result,error):
            if generation != self.state.generation:
                return
            if error and error.status == 401:
                self.logout('Your session is no longer valid. Please sign in again.')
            else:
                done(result,error)
        if not self.tasks.submit('screen',work,completed):
            done(None,ApiError(message='Requests are busy. Please try again shortly.'))

    def navigate(self,destination,audit_id=None):
        if not self.state.login:
            return
        if destination not in self.state.destinations and destination != 'Audit Details':
            return
        self.tasks.invalidate()
        if self.screen and self.screen.winfo_exists():
            self.screen.destroy()
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
            self.tasks.submit('logout',work,lambda error,_: self.screen.status.show(str(error)) if error and not self.state.login and hasattr(self.screen,'status') else None)
        else:
            Thread(target=work,daemon=True,name='bhli-signout').start()

    def logout(self,message='Signed out. Please sign in to continue.'):
        old=self.state.clear()
        self.tasks.invalidate()
        self.query=AuditQuery()
        self.selected_id=None
        self.show_login(message)
        if old:
            self._revoke(old.token,notify=True)

    def set_theme(self,appearance):
        ctk.set_appearance_mode(appearance)
        if self.state.login:
            destination=self.destination
            audit_id=getattr(self.screen,'audit_id',None)
            self.tasks.invalidate()
            self.shell.destroy()
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
        old=self.state.clear()
        self.tasks.close()
        if old:
            self._revoke(old.token)
        self.destroy()
