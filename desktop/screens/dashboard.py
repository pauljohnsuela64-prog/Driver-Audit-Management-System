import customtkinter as ctk
from desktop.components.common import button, label, StatePanel
from desktop.components.table import AuditTable
from desktop.models import AuditQuery
from desktop.theme import color


class Dashboard(ctk.CTkScrollableFrame):
    def __init__(self,parent,app):
        super().__init__(parent,fg_color='transparent')
        self.app=app
        self.loaded=False
        self.total=None
        self.columnconfigure(0,weight=1)
        label(self,'Your audit workspace',28).grid(row=0,column=0,sticky='w',pady=(0,4))
        description=('Administrator workspace · View all active driver audits.' if app.state.login.user.role=='ADMIN'
                     else 'Auditor workspace · Browse active audits across your team.')
        label(self,description,muted=True,wraplength=600,justify='left').grid(row=1,column=0,sticky='w',pady=(0,24))
        self.body=ctk.CTkFrame(self,fg_color='transparent')
        self.body.grid(row=2,column=0,sticky='nsew')
        self.body.columnconfigure(0,weight=1)
        self.refresh()

    def refresh(self):
        self.loaded=False
        for child in self.body.winfo_children():
            child.destroy()
        StatePanel(self.body,'Loading dashboard','Retrieving the latest audit overview…').grid(row=0,column=0,sticky='ew')
        client,token=self.app.client,self.app.state.login.token
        self.app.request(lambda: client.list_audits(token,AuditQuery(page_size=5)),self.finished)

    def finished(self,page,error):
        for child in self.body.winfo_children():
            child.destroy()
        if error:
            StatePanel(self.body,'Overview unavailable',str(error),self.refresh).grid(row=0,column=0,sticky='ew')
            return
        self.loaded=True
        self.total=page.total
        summary=ctk.CTkFrame(self.body,fg_color=color('surface'),corner_radius=12)
        summary.grid(row=0,column=0,sticky='ew',pady=(0,24))
        label(summary,'ACTIVE DRIVER AUDITS',12,True).pack(anchor='w',padx=24,pady=(20,0))
        label(summary,f'{page.total:,}',36).pack(anchor='w',padx=24,pady=(0,4))
        label(summary,'All active records visible to your account',12,True).pack(anchor='w',padx=24,pady=(0,16))
        button(summary,'Open Driver Audits',lambda: self.app.navigate('Driver Audits'),True,width=190).pack(anchor='w',padx=24,pady=(0,20))
        label(self.body,'Most recently created',20).grid(row=1,column=0,sticky='w',pady=(0,12))
        if page.items:
            table=AuditTable(self.body,lambda: self.open_selected(table),height=5)
            table.grid(row=2,column=0,sticky='ew')
            table.set_rows(page.items)
            button(self.body,'View selected audit',lambda: self.open_selected(table),width=180).grid(row=3,column=0,sticky='w',pady=12)
        else:
            StatePanel(self.body,'No active audits yet','New records will appear here when available.').grid(row=2,column=0,sticky='ew')
        if self.app.state.login.user.role=='ADMIN':
            label(self.body,'Administration',20).grid(row=4,column=0,sticky='w',pady=(20,4))
            label(self.body,'Employee Accounts and Administrator Activity desktop modules are coming in a later phase.',
                  muted=True,wraplength=560,justify='left').grid(row=5,column=0,sticky='w')

    def open_selected(self,table):
        audit_id=table.selected()
        if audit_id:
            self.app.navigate('Audit Details',audit_id)
