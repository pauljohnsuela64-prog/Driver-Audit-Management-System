import customtkinter as ctk
from desktop.components.common import button, label, StatePanel, destroy_view
from desktop.theme import color, font


class Details(ctk.CTkFrame):
    def __init__(self,parent,app,audit_id):
        super().__init__(parent,fg_color='transparent')
        self.app,self.audit_id=app,audit_id
        self.loaded=False
        self.record=None
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=1)
        toolbar=ctk.CTkFrame(self,fg_color='transparent')
        toolbar.grid(row=0,column=0,sticky='ew',pady=(0,16))
        button(toolbar,'Back to audits',lambda:app.navigate('Driver Audits'),width=150).pack(side='left')
        button(toolbar,'Refresh',self.refresh,width=100).pack(side='right')
        self.actions=ctk.CTkFrame(self,fg_color='transparent')
        self.actions.grid(row=2,column=0,sticky='ew',pady=(12,0))
        self.body=ctk.CTkScrollableFrame(self,fg_color=color('surface'),corner_radius=12)
        self.body.grid(row=1,column=0,sticky='nsew')
        self.body.columnconfigure(0,weight=1)
        self.refresh()

    def refresh(self):
        self.loaded=False
        self.record=None
        for child in self.actions.winfo_children():
            destroy_view(child)
        for child in self.body.winfo_children():
            destroy_view(child)
        StatePanel(self.body,'Loading audit details').grid(row=0,column=0,sticky='ew')
        client,token,audit_id=self.app.client,self.app.session.login.token,self.audit_id
        include_deleted=self.app.session.login.user.role=='ADMIN' and self.app.query.include_deleted
        self.app.request(lambda:client.get_audit(token,audit_id,include_deleted=True) if include_deleted else client.get_audit(token,audit_id),self.finished)

    def finished(self,record,error):
        for child in self.body.winfo_children():
            destroy_view(child)
        if error:
            StatePanel(self.body,'Audit unavailable',str(error),self.refresh).grid(row=0,column=0,sticky='ew')
            return
        self.loaded=True
        self.record=record
        label(self.body,'Audit details',28).grid(row=0,column=0,sticky='w',padx=24,pady=(24,4))
        label(self.body,'Deleted audit · Read-only' if record.deleted_at else 'Original auditor attribution · Preserved',12,True).grid(row=1,column=0,sticky='w',padx=24,pady=(0,16))
        from desktop.audit_operations import can_edit
        user=self.app.session.login.user
        if can_edit(record,user.id,user.role):
            button(self.actions,'Edit audit',lambda:self.app.open_edit(record),True,width=140).pack(side='left',padx=(0,8))
        fields=[('Driver Name',record.driver_name),('Helper Name',record.helper_name),('Audit Date',record.audit_date),
                ('Station',record.station),('Plate Number',record.plate_number),('Remarks',record.remarks),('Audited By',record.audited_by_name)]
        for i,(title,value) in enumerate(fields):
            label(self.body,title,12,True).grid(row=2+i*2,column=0,sticky='w',padx=24,pady=(12,0))
            box=ctk.CTkTextbox(self.body,height=120 if title=='Remarks' else 48,wrap='word',font=font(16),
                fg_color=color('raised'),text_color=color('text'),border_width=1,border_color=color('border'))
            box.insert('1.0',value or 'Not provided')
            box.configure(state='disabled')
            box.grid(row=3+i*2,column=0,sticky='ew',padx=24,pady=(4,4))
        label(self.body,f'Record #{record.id} · Version {record.version}\nCreated {record.created_at:%Y-%m-%d %H:%M UTC} · Updated {record.updated_at:%Y-%m-%d %H:%M UTC}',
              12,True,justify='left',wraplength=500).grid(row=16,column=0,sticky='w',padx=24,pady=24)
