"""Chronological server history; updater identity is separate from attribution."""
import customtkinter as ctk
from desktop.audit_operations import FIELDS,LABELS
from desktop.components.common import button,label,Notice,destroy_view
from desktop.theme import color,font


class AuditHistory(ctk.CTkFrame):
    def __init__(self,parent,app,audit_id):
        super().__init__(parent,fg_color='transparent')
        self.app,self.audit_id=app,audit_id
        self.page=1
        self.loaded=False
        self.events=None
        self.selected=None
        self.columnconfigure(0,weight=1)
        self.rowconfigure(2,weight=1)
        header=ctk.CTkFrame(self,fg_color='transparent')
        header.grid(row=0,column=0,sticky='ew',pady=(0,12))
        label(header,f'Audit #{audit_id} · History',24).pack(side='left')
        button(header,'Back to details',lambda:app.navigate('Audit Details',audit_id),width=140).pack(side='right')
        self.notice=Notice(self)
        self.notice.grid(row=1,column=0,sticky='ew',pady=(0,8))
        self.body=ctk.CTkScrollableFrame(self,fg_color=color('surface'),corner_radius=12)
        self.body.grid(row=2,column=0,sticky='nsew')
        self.body.columnconfigure(0,weight=1)
        footer=ctk.CTkFrame(self,fg_color='transparent')
        footer.grid(row=3,column=0,sticky='ew',pady=(12,0))
        self.count=label(footer,'Loading history…',12,True)
        self.count.pack(side='left')
        self.next=button(footer,'Next',lambda:self.change_page(1),width=80)
        self.next.pack(side='right')
        self.previous=button(footer,'Previous',lambda:self.change_page(-1),width=90)
        self.previous.pack(side='right',padx=8)
        button(footer,'Refresh',self.refresh,width=90).pack(side='right',padx=8)
        self.refresh()

    def change_page(self,delta):
        if self.loaded and 1<=self.page+delta<=10000:
            self.page+=delta
            self.refresh()

    def refresh(self):
        self.loaded=False
        self.notice.show('Loading audit history…',False)
        self.previous.configure(state='disabled');self.next.configure(state='disabled')
        for child in self.body.winfo_children():
            destroy_view(child)
        client,token,audit_id,page=self.app.client,self.app.session.login.token,self.audit_id,self.page
        include_deleted=self.app.session.login.user.role=='ADMIN'
        self.app.request(lambda:client.audit_history(token,audit_id,page,include_deleted=include_deleted),self.finished)

    def finished(self,page,error):
        if error:
            self.notice.show(str(error)+' Use Refresh to retry.')
            self.count.configure(text='History unavailable')
            return
        self.loaded=True
        self.events=page
        self.notice.show('No history events.' if not page.items else 'Oldest events first · Actor IDs identify who performed each action.',False)
        self.count.configure(text=f'{page.total:,} events · Page {page.page}')
        self.previous.configure(state='normal' if page.page>1 else 'disabled')
        self.next.configure(state='normal' if page.page*25<page.total and page.page<10000 else 'disabled')
        for i,event in enumerate(page.items):
            card=ctk.CTkFrame(self.body,fg_color=color('raised'),corner_radius=8)
            card.grid(row=i,column=0,sticky='ew',padx=12,pady=8)
            card.columnconfigure(0,weight=1)
            title=f'{event.action} · {event.created_at:%Y-%m-%d %H:%M:%S UTC} · User #{event.actor_user_id}'
            button(card,title,lambda event=event:self.select(event)).grid(row=0,column=0,sticky='ew',padx=12,pady=12)
            if self.selected==event.id or self.selected is None and i==0:
                self.render_event(card,event)

    def select(self,event):
        self.selected=event.id
        page=self.events
        for child in self.body.winfo_children():
            destroy_view(child)
        self.finished(page,None)

    def render_event(self,parent,event):
        before,after=event.before_data,event.after_data
        lines=[f'Original auditor: {after.audited_by_name} · Owner user #{after.audited_by_user_id}']
        for key in (*FIELDS,'audited_by_name'):
            old=getattr(before,key) if before else None
            new=getattr(after,key)
            if before is None or old!=new:
                lines.extend(['',LABELS.get(key,'Audited By'),
                              'Before: '+(old or 'Not provided') if before else 'Before: No record',
                              'After: '+(new or 'Not provided')])
        lines.extend(['',f'Technical metadata · Event #{event.id} · Record #{after.id} · Version {after.version}',
                      f'Deleted at: {after.deleted_at:%Y-%m-%d %H:%M:%S UTC}' if after.deleted_at else 'Deleted at: Not deleted'])
        box=ctk.CTkTextbox(parent,height=300,wrap='word',font=font(),fg_color=color('surface'),text_color=color('text'),
                          border_width=1,border_color=color('border'))
        box.insert('1.0','\n'.join(lines));box.configure(state='disabled')
        box.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,12))
