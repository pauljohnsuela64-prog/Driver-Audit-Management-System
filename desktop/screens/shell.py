import customtkinter as ctk
import tkinter as tk
from desktop.components.common import button, label, Notice, Tip, option_menu
from desktop.theme import color, font, icon


class Shell(ctk.CTkFrame):
    def __init__(self,parent,app):
        super().__init__(parent,fg_color=color('bg'),corner_radius=0)
        self.app,self.collapsed = app,False
        self.columnconfigure(1,weight=1)
        self.rowconfigure(0,weight=1)
        self.sidebar = ctk.CTkFrame(self,width=232,fg_color=color('nav'),corner_radius=0)
        self.sidebar.grid(row=0,column=0,sticky='ns')
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0,weight=1)
        self.sidebar.rowconfigure(8,weight=1)
        self.brand = ctk.CTkLabel(self.sidebar,text='BHLI  /  AUDIT',text_color='#5EEAD4',font=font(18,'bold'))
        self.brand.grid(row=0,column=0,padx=16,pady=(24,16))
        self.toggle = button(self.sidebar,'Collapse navigation',self.collapse,width=200)
        self.toggle.grid(row=1,column=0,padx=12,pady=(0,24),sticky='ew')
        self.nav_buttons,self.images = {},[]
        for row,destination in enumerate(app.session.destinations,2):
            image=icon(self,destination)
            self.images.append(image)
            b=button(self.sidebar,destination,lambda d=destination: app.navigate(d),image=image,
                      anchor='w',width=200)
            b.configure(fg_color=color('nav'),text_color='#F1F5F9',hover_color='#1E293B',border_color=color('nav'))
            b.grid(row=row,column=0,padx=12,pady=4,sticky='ew')
            self.nav_buttons[destination]=b
            Tip(b,destination)
        self.footer = ctk.CTkLabel(self.sidebar,text='Phase 3B · Audit management',font=font(11),text_color='#B8C5D6',wraplength=190)
        self.footer.grid(row=9,column=0,padx=12,pady=20)
        main=ctk.CTkFrame(self,fg_color='transparent',corner_radius=0)
        main.grid(row=0,column=1,sticky='nsew')
        main.columnconfigure(0,weight=1)
        main.rowconfigure(2,weight=1)
        header=ctk.CTkFrame(main,fg_color=color('surface'),corner_radius=0)
        header.grid(row=0,column=0,sticky='ew')
        header.columnconfigure(0,weight=1)
        self.heading=label(header,'Dashboard',20)
        self.heading.grid(row=0,column=0,sticky='w',padx=24,pady=(12,0))
        user=app.session.login.user
        display_name=user.full_name if len(user.full_name)<=28 else user.full_name[:27]+'…'
        self.identity=label(header,f'{display_name} · {user.role}',12,True)
        self.identity.grid(row=1,column=0,sticky='w',padx=24,pady=(0,12))
        self.appearance=option_menu(header,values=['Light','Dark'],command=app.set_theme,width=88,
                                        font=font(12),fg_color=color('primary'),text_color=color('on_primary'))
        self.appearance.set(ctk.get_appearance_mode())
        self.appearance.grid(row=0,column=1,rowspan=2,padx=8)
        self.account=button(header,'Account',self.toggle_menu,width=100)
        self.account.grid(row=0,column=2,rowspan=2,padx=(0,16))
        self.menu=ctk.CTkFrame(main,fg_color=color('surface'))
        user=app.session.login.user
        label(self.menu,f'{user.full_name} · {user.role}',wraplength=450).pack(side='left',padx=16)
        button(self.menu,'My Account',lambda: app.navigate('My Account'),width=110).pack(side='left',padx=4,pady=8)
        button(self.menu,'Sign Out',app.logout,width=100).pack(side='left',padx=4,pady=8)
        self.content=ctk.CTkFrame(main,fg_color='transparent')
        self.content.grid(row=2,column=0,sticky='nsew',padx=24,pady=16)
        self.notice=Notice(main)
        self.notice.grid(row=3,column=0,sticky='ew',padx=24,pady=(0,12))
        tk.Misc.bind(self,'<Configure>',self.resize,add='+')

    def collapse(self):
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self,value):
        self.collapsed=value
        self.sidebar.configure(width=64 if value else 232)
        self.brand.configure(text='BH' if value else 'BHLI  /  AUDIT')
        self.toggle.configure(text='›' if value else 'Collapse navigation',width=40 if value else 200)
        for name,b in self.nav_buttons.items():
            b.configure(text='' if value else name,width=40 if value else 200,anchor='center' if value else 'w')
        self.footer.configure(text='' if value else 'Phase 3B · Audit management')

    def resize(self,event):
        if event.widget is self and event.width/self._get_widget_scaling() < 1050 and not self.collapsed:
            self.set_collapsed(True)

    def select(self,name):
        self.heading.configure(text=name)
        for destination,b in self.nav_buttons.items():
            selected = destination == name or (name=='Audit Details' and destination=='Driver Audits')
            b.configure(fg_color=color('selected') if selected else color('nav'),
                        border_color='#5EEAD4' if selected else color('nav'))
        self.menu.grid_remove()

    def toggle_menu(self):
        if self.menu.winfo_ismapped():
            self.hide_menu()
        else:
            self.menu.grid(row=1,column=0,sticky='ew')
            self.menu.winfo_children()[1].focus_set()

    def hide_menu(self):
        self.menu.grid_remove()
        self.account.focus_set()
