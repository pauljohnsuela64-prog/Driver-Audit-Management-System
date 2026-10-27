"""Native keyboard-accessible read-only table."""
from tkinter import ttk
import customtkinter as ctk
from desktop.theme import resolved

COLUMNS = ('audit_date','driver_name','helper_name','station','plate_number','audited_by_name')
HEADINGS = ('Audit Date','Driver Name','Helper Name','Station','Plate Number','Audited By')


class AuditTable(ctk.CTkFrame):
    def __init__(self,parent,on_open,height=10):
        super().__init__(parent,fg_color='transparent',corner_radius=0)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(0,weight=1)
        scale=self._get_widget_scaling()
        style=ttk.Style(self)
        style.theme_use('clam')
        style.configure('BHLI.Treeview',background=resolved('surface'),fieldbackground=resolved('surface'),
            foreground=resolved('text'),rowheight=int(44*scale),font=('Segoe UI',-int(14*scale)),
            borderwidth=1,bordercolor=resolved('border'))
        style.configure('BHLI.Treeview.Heading',background=resolved('raised'),foreground=resolved('muted'),
            font=('Segoe UI',-int(12*scale),'bold'),padding=int(12*scale),relief='flat')
        style.map('BHLI.Treeview',background=[('selected',resolved('primary'))],
                  foreground=[('selected',resolved('on_primary'))])
        style.map('BHLI.Treeview.Heading',background=[('active',resolved('bg'))])
        self.tree=ttk.Treeview(self,columns=COLUMNS,show='headings',style='BHLI.Treeview',
                               selectmode='browse',height=height,takefocus=True)
        for key,title,width in zip(COLUMNS,HEADINGS,(120,190,170,170,130,190)):
            self.tree.heading(key,text=title)
            self.tree.column(key,width=int(width*scale),minwidth=int(width*scale),stretch=True)
        self.tree.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(self,orient='vertical',command=self.tree.yview)
        horizontal=ttk.Scrollbar(self,orient='horizontal',command=self.tree.xview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        def open_record(event=None):
            on_open()
            # Navigation destroys this widget; do not run its remaining class bindings.
            return 'break'
        self.tree.bind('<Double-1>',open_record)
        self.tree.bind('<Return>',open_record)
        self.tree.bind('<Home>',lambda e=None: self.select_edge(False))
        self.tree.bind('<End>',lambda e=None: self.select_edge(True))

    def select_edge(self,last):
        children=self.tree.get_children()
        if children:
            row=children[-1] if last else children[0]
            self.tree.selection_set(row)
            self.tree.focus(row)
            self.tree.see(row)
        return 'break'

    def set_rows(self,records,selected=None):
        self.tree.delete(*self.tree.get_children())
        for record in records:
            self.tree.insert('', 'end',iid=str(record.id),values=[getattr(record,k) or '—' for k in COLUMNS])
        if selected is not None and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))
            self.tree.focus(str(selected))
            self.tree.see(str(selected))
            self.tree.focus_set()

    def selected(self):
        selection=self.tree.selection()
        return int(selection[0]) if selection else None
