import time
import customtkinter as ctk
import tkinter as tk
from desktop.components.common import button, entry, label, Notice, checkbox
from desktop.theme import color, font


class LoginScreen(ctk.CTkFrame):
    def __init__(self, parent, app, message='',message_error=True):
        super().__init__(parent, fg_color=color('bg'), corner_radius=0)
        self.app = app
        self.blocked_until = 0
        self.pending = False
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.brand = ctk.CTkFrame(self, fg_color=color('nav'), corner_radius=0)
        self.brand.grid(row=0,column=0,sticky='nsew')
        self.brand.columnconfigure(0,weight=1)
        self.brand.rowconfigure(0,weight=1)
        copy = ctk.CTkFrame(self.brand,fg_color='transparent')
        copy.grid(row=0,column=0,sticky='ew',padx=40,pady=32)
        ctk.CTkLabel(copy,text='BHLI  /  AUDIT',text_color='#5EEAD4',font=font(16,'bold')).pack(anchor='w')
        ctk.CTkLabel(copy,text='Clarity for every\ndriver audit.',justify='left',text_color='#F1F5F9',
                     font=font(36,'bold')).pack(anchor='w',pady=(24,16))
        ctk.CTkLabel(copy,text='A secure workspace for your audit operations.\nSign in with your HR administrator account.',
                     justify='left',text_color='#B8C5D6',font=font(14),wraplength=350).pack(anchor='w')
        self.right = ctk.CTkFrame(self,fg_color='transparent')
        self.right.grid(row=0,column=1,sticky='nsew',padx=32,pady=32)
        self.right.columnconfigure(0,weight=1)
        self.right.rowconfigure(0,weight=1)
        self.right.rowconfigure(2,weight=1)
        self.card = ctk.CTkFrame(self.right,fg_color=color('surface'),corner_radius=12)
        self.card.grid(row=1,column=0,sticky='ew')
        self.card.columnconfigure(0,weight=1)
        label(self.card,'Welcome back',28).grid(row=0,column=0,sticky='w',padx=28,pady=(28,4))
        label(self.card,'Sign in to BHLI Audit',muted=True).grid(row=1,column=0,sticky='w',padx=28,pady=(0,24))
        label(self.card,'Username').grid(row=2,column=0,sticky='w',padx=28)
        self.username = entry(self.card)
        self.username.grid(row=3,column=0,sticky='ew',padx=28,pady=(4,16))
        label(self.card,'Password').grid(row=4,column=0,sticky='w',padx=28)
        self.password = entry(self.card,show='•')
        self.password.grid(row=5,column=0,sticky='ew',padx=28,pady=(4,8))
        self.reveal = checkbox(self.card,text='Show password',font=font(12),
                                     command=lambda: self.password.configure(show='' if self.reveal.get() else '•'))
        self.reveal.grid(row=6,column=0,sticky='w',padx=28,pady=(0,16))
        self.status = Notice(self.card)
        self.status.configure(wraplength=310)
        self.status.grid(row=7,column=0,sticky='ew',padx=28,pady=(0,12))
        self.status.show(message,message_error)
        self.submit_button = button(self.card,'Sign In',self.submit,primary=True)
        self.submit_button.grid(row=8,column=0,sticky='ew',padx=28,pady=(0,16))
        from urllib.parse import urlsplit
        endpoint=app.endpoint
        host=urlsplit(endpoint.config.base_url).netloc if endpoint.config else 'Not configured'
        label(self.card,f'Service: {host}\n{endpoint.source}',12,True,wraplength=300).grid(
            row=9,column=0,padx=20,pady=(0,8))
        self.connection_button=button(self.card,'Connection settings',app.open_connection,width=180)
        self.connection_button.grid(row=10,column=0,padx=28,pady=(0,20))
        if endpoint.config is None:
            self.submit_button.configure(state='disabled')
            self.status.show(endpoint.error or 'Configure the API connection before signing in.')
        self.username.bind('<Return>',lambda e=None: self.submit())
        self.password.bind('<Return>',lambda e=None: self.submit())
        tk.Misc.bind(self,'<Configure>',self.resize,add='+')
        self.username.focus_set()

    def resize(self, event):
        if event.widget is self:
            if event.width/self._get_widget_scaling() < 950:
                self.brand.grid_remove()
                self.right.grid_configure(column=0,columnspan=2,padx=32)
            else:
                self.brand.grid()
                self.right.grid_configure(column=1,columnspan=1,padx=32)

    def submit(self):
        if self.app.endpoint.config is None or self.pending or time.monotonic() < self.blocked_until:
            return
        username,password = self.username.get().strip(),self.password.get()
        if not 1 <= len(username) <= 100 or not 1 <= len(password) <= 128:
            self.status.show('Enter your username and password (up to 128 characters).')
            return
        self.password.delete(0,'end')
        self.pending = True
        self.submit_button.configure(state='disabled',text='Signing in…')
        self.username.configure(state='disabled')
        self.password.configure(state='disabled')
        self.status.show('Connecting to the service…',False)
        self.app.sign_in(username,password,self.finished)

    def finished(self, result, error):
        self.pending = False
        self.username.configure(state='normal')
        self.password.configure(state='normal')
        self.submit_button.configure(state='normal',text='Sign In')
        if error:
            self.status.show(str(error))
            if error.status == 429:
                self.blocked_until = time.monotonic()+error.retry_after
                self.countdown()
            self.password.focus_set()

    def countdown(self):
        if not self.winfo_exists():
            return
        seconds = max(0,int(self.blocked_until-time.monotonic())+1)
        if seconds:
            self.submit_button.configure(state='disabled',text=f'Try again in {seconds}s')
            self.after(500,self.countdown)
        else:
            self.submit_button.configure(state='normal',text='Sign In')
