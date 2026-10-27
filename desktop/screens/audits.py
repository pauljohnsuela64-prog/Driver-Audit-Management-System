from dataclasses import replace
import customtkinter as ctk
from desktop.components.common import button, entry, label, Notice, option_menu, checkbox
from desktop.components.table import AuditTable
from desktop.models import AuditQuery
from desktop.theme import color, font

SORTS={'Newest created':'-id','Oldest created':'id','Audit date ↓':'-audit_date','Audit date ↑':'audit_date'}


class Audits(ctk.CTkFrame):
    def __init__(self,parent,app):
        super().__init__(parent,fg_color='transparent')
        self.app=app
        self.loaded=False
        self.last_error=None
        self.total=0
        self.search_mode='Driver'
        self.columnconfigure(0,weight=1)
        self.rowconfigure(4,weight=1)
        toolbar=ctk.CTkFrame(self,fg_color='transparent')
        toolbar.grid(row=0,column=0,sticky='ew',pady=(0,12))
        toolbar.columnconfigure(1,weight=1)
        self.search_field=option_menu(toolbar,values=['Driver','Plate','Station'],width=110,font=font(),
            command=self.search_changed,fg_color=color('primary'),text_color=color('on_primary'))
        self.search_field.grid(row=0,column=0,padx=(0,8))
        self.search=entry(toolbar,'Search audits')
        self.search.grid(row=0,column=1,sticky='ew',padx=(0,8))
        self.search.bind('<Return>',lambda e=None: self.apply())
        self.apply_button=button(toolbar,'Search',self.apply,True,width=80)
        self.apply_button.grid(row=0,column=2,padx=(0,8))
        button(toolbar,'Filters',self.toggle_filters,width=80).grid(row=0,column=3)
        self.options=ctk.CTkFrame(self,fg_color=color('surface'),corner_radius=12)
        self.options.grid(row=1,column=0,sticky='ew',pady=(0,8))
        for col in range(3):
            self.options.columnconfigure(col,weight=1)
        self.station=self.field(self.options,'Station',0,0)
        self.date_from=self.field(self.options,'From · YYYY-MM-DD',0,1)
        self.date_to=self.field(self.options,'To · YYYY-MM-DD',0,2)
        self.mine=checkbox(self.options,text='My audits',font=font())
        self.mine.grid(row=2,column=0,sticky='w',padx=12,pady=12)
        button(self.options,'Apply filters',self.apply,True,width=120).grid(row=2,column=1,padx=8,pady=12,sticky='e')
        button(self.options,'Clear all',self.clear,width=100).grid(row=2,column=2,padx=12,pady=12,sticky='e')
        self.options.grid_remove()
        ordering=ctk.CTkFrame(self,fg_color='transparent')
        ordering.grid(row=2,column=0,sticky='ew',pady=(0,8))
        ordering.columnconfigure(1,weight=1)
        self.sort=option_menu(ordering,values=list(SORTS),command=lambda v: self.apply(),font=font(12),
            width=155,fg_color=color('primary'),text_color=color('on_primary'))
        self.sort.grid(row=0,column=0,sticky='w')
        self.refresh_button=button(ordering,'Refresh',self.refresh,width=95)
        self.refresh_button.grid(row=0,column=2,padx=(8,0))
        self.detail_button=button(ordering,'View Details',self.open_selected,width=120)
        self.detail_button.grid(row=0,column=3,padx=(8,0))
        self.notice=Notice(self)
        self.notice.grid(row=3,column=0,sticky='ew',pady=(0,8))
        self.table=AuditTable(self,self.open_selected)
        self.table.grid(row=4,column=0,sticky='nsew')
        pager=ctk.CTkFrame(self,fg_color='transparent')
        pager.grid(row=5,column=0,sticky='ew',pady=(12,0))
        pager.columnconfigure(0,weight=1)
        self.range=label(pager,'Loading…',12,True)
        self.range.grid(row=0,column=0,sticky='w')
        self.size=option_menu(pager,values=['25','50','100'],command=lambda v:self.apply(),width=70,
            font=font(12),fg_color=color('primary'),text_color=color('on_primary'))
        self.size.grid(row=0,column=1,padx=8)
        self.previous=button(pager,'Previous',lambda:self.page(-1),width=85)
        self.previous.grid(row=0,column=2,padx=4)
        self.next=button(pager,'Next',lambda:self.page(1),width=75)
        self.next.grid(row=0,column=3,padx=(4,0))
        self.restore_query()
        self.refresh()

    @staticmethod
    def field(parent,title,row,col):
        label(parent,title,12,True).grid(row=row,column=col,sticky='w',padx=12,pady=(12,0))
        widget=entry(parent,width=150)
        widget.grid(row=row+1,column=col,sticky='ew',padx=12,pady=(4,0))
        return widget

    def restore_query(self):
        q=self.app.query
        self.sort.set(next(k for k,v in SORTS.items() if v==q.sort))
        self.size.set(str(q.page_size))
        for field,widget in [('station',self.station),('date_from',self.date_from),('date_to',self.date_to)]:
            widget.insert(0,getattr(q,field))
        if q.audited_by_user_id:
            self.mine.select()
        if q.plate_number:
            self.search_field.set('Plate')
            self.search_mode='Plate'
            self.search.insert(0,q.plate_number)
        elif q.driver_name:
            self.search.insert(0,q.driver_name)

    def search_changed(self,value):
        if self.search_mode=='Station':
            self.station.configure(state='normal')
            self.station.delete(0,'end')
            self.station.insert(0,self.search.get())
        self.search_mode=value
        if value=='Station':
            self.search.delete(0,'end')
            self.search.insert(0,self.station.get())
            self.station.configure(state='disabled')
        else:
            self.station.configure(state='normal')
            self.search.delete(0,'end')

    def toggle_filters(self):
        if self.options.winfo_ismapped():
            self.options.grid_remove()
        else:
            self.options.grid()

    def apply(self):
        term=self.search.get().strip()
        if self.search_field.get()=='Station':
            self.station.configure(state='normal')
            self.station.delete(0,'end')
            self.station.insert(0,term)
            self.station.configure(state='disabled')
        values=dict(driver_name='',plate_number='',station=self.station.get().strip())
        values[{'Driver':'driver_name','Plate':'plate_number','Station':'station'}[self.search_field.get()]]=term
        try:
            query=AuditQuery(page_size=int(self.size.get()),sort=SORTS[self.sort.get()],
                date_from=self.date_from.get().strip(),date_to=self.date_to.get().strip(),
                audited_by_user_id=self.app.session.login.user.id if self.mine.get() else None,**values)
        except ValueError:
            self.notice.show('Check search length (200 maximum) and dates (YYYY-MM-DD, start before end).')
            return
        self.app.query=query
        self.app.selected_id=None
        self.refresh()

    def clear(self):
        self.app.query=AuditQuery()
        self.app.selected_id=None
        self.app.navigate('Driver Audits')

    def page(self,delta):
        if not self.loaded:
            return
        page=self.app.query.page+delta
        if not 1<=page<=10000:
            return
        self.app.query=replace(self.app.query,page=page)
        self.app.selected_id=None
        self.refresh()

    def refresh(self):
        self.loaded=False
        self.last_error=None
        self.table.set_rows(())
        self.range.configure(text='Loading…')
        self.notice.show('Loading driver audits…',False)
        for b in (self.previous,self.next,self.detail_button):
            b.configure(state='disabled')
        client,token,query=self.app.client,self.app.session.login.token,self.app.query
        self.app.request(lambda:client.list_audits(token,query),self.finished)

    def finished(self,page,error):
        self.last_error=error
        if error:
            self.notice.show(str(error)+' Use Refresh to retry.')
            self.range.configure(text='Records unavailable')
            return
        self.loaded=True
        self.total=page.total
        self.table.set_rows(page.items,self.app.selected_id)
        self.notice.show('No matching audits. Try clearing your filters.' if not page.items else 'Read-only · Open a record to see all seven audit fields.',False)
        start=(page.page-1)*page.page_size+1 if page.items else 0
        end=start+len(page.items)-1 if page.items else 0
        self.range.configure(text=f'{start}–{end} of {page.total:,} · Page {page.page}')
        self.previous.configure(state='normal' if page.page>1 else 'disabled')
        self.next.configure(state='normal' if page.page*page.page_size<page.total and page.page<10000 else 'disabled')
        self.detail_button.configure(state='normal' if page.items else 'disabled')

    def open_selected(self):
        audit_id=self.table.selected()
        if audit_id and self.loaded:
            self.app.selected_id=audit_id
            self.app.navigate('Audit Details',audit_id)
