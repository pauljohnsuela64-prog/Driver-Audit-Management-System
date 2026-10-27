"""Signed-out connection setup; no authentication tokens enter health requests."""
from desktop.api import ApiClient
from desktop.settings import validated,save_settings,SettingsError,Endpoint
from desktop.components.audit_dialogs import Confirmation
from desktop.components.common import entry,label,button,Notice


class Connection(Confirmation):
    def __init__(self,app):
        super().__init__(app,'API connection',
            'Use the service address supplied by your administrator. Remote services require trusted HTTPS. HTTP is allowed only on this computer (loopback).',None,'Save connection')
        self.alive=True;self.pending=False
        label(self.body,'API origin',12,True).grid(row=1,column=0,sticky='w',padx=8,pady=(12,4))
        self.origin_field=entry(self.body,placeholder='https://audit.example.com')
        self.origin_field.grid(row=2,column=0,sticky='ew',padx=8)
        if app.endpoint.config:self.origin_field.insert(0,app.endpoint.config.base_url)
        self.status=Notice(self.body);self.status.configure(wraplength=390)
        self.status.grid(row=3,column=0,sticky='ew',padx=8,pady=8)
        self.test_button=button(self.body,'Test connection',self.test,width=160)
        self.test_button.grid(row=4,column=0,sticky='w',padx=8,pady=(0,8))
        self.confirm_button.configure(command=self.save)
        if app.endpoint.locked:
            self.origin_field.configure(state='disabled');self.confirm_button.configure(state='disabled')
            self.status.show(f'{app.endpoint.source} override is active. Your administrator must change that override.')
        elif not app.settings_file:
            self.confirm_button.configure(state='disabled')
            self.status.show('Windows settings storage is unavailable. Contact your administrator.')
        elif app.endpoint.error:self.status.show(app.endpoint.error)

    def activate(self):
        if not self.winfo_exists():return
        self.grab_set()
        widgets=[self.origin_field,self.test_button,self.cancel_button,self.confirm_button]
        widgets=[w for w in widgets if w.cget('state')!='disabled']
        for i,widget in enumerate(widgets):
            widget.bind('<Tab>',lambda e,w=widgets[(i+1)%len(widgets)]:self._focus(w))
            widget.bind('<Shift-Tab>',lambda e,w=widgets[(i-1)%len(widgets)]:self._focus(w))
            widget.bind('<FocusIn>',lambda e:self.body._parent_canvas.yview_moveto(.5),add='+')
        widgets[0].focus_set()

    def test(self):
        if self.pending:return
        try:config=validated(self.origin_field.get())
        except SettingsError as error:self.status.show(str(error));return
        self.pending=True;self.test_button.configure(state='disabled')
        self.origin_field.configure(state='disabled');self.confirm_button.configure(state='disabled')
        self.status.show('Checking the API connection…',False)
        client=ApiClient(config)
        def done(result,error):
            if not self.alive:return
            self.pending=False;self.test_button.configure(state='normal')
            if not self.app.endpoint.locked:
                self.origin_field.configure(state='normal')
                if self.app.settings_file:self.confirm_button.configure(state='normal')
            self.status.show(str(error) if error else 'API reachable. Database readiness is not verified; sign in after your administrator approves server deployment.',bool(error))
        if not self.app.tasks.submit('connection',client.health,done):
            done(None,SettingsFailure())

    def save(self):
        if self.pending or self.app.endpoint.locked or self.app.session.login or not self.app.settings_file:return
        try:config=save_settings(self.app.settings_file,self.origin_field.get())
        except SettingsError as error:self.status.show(str(error));return
        self.app.tasks.invalidate()
        self.app.endpoint=Endpoint(config,'Saved settings');self.app.client=ApiClient(config)
        self.dismiss();self.app.show_login('Connection saved. Sign in with your HR administrator account.',error=False)

    def dismiss(self):
        self.alive=False
        super().dismiss()


class SettingsFailure:
    def __str__(self):return 'The connection check is busy. Please try again.'
