import customtkinter as ctk
import tkinter as tk
from desktop.components.common import button, label, Notice, Tip, option_menu
from desktop.theme import color, font, icon


class Shell(ctk.CTkFrame):
    def __init__(self,parent,app,local_profile=None,destinations=None):
        super().__init__(parent,fg_color=color('bg'),corner_radius=0)
        self.app,self.collapsed = app,False
        self.offline = local_profile is not None
        self._compact_band = None
        self._resize_job = None
        self._restored_state = getattr(app, "_sidebar_collapsed", None) if self.offline else None
        self.columnconfigure(1,weight=1)
        self.rowconfigure(0,weight=1)
        self.sidebar = ctk.CTkFrame(self,width=232,fg_color=color('nav'),corner_radius=0)
        self.sidebar.grid(row=0,column=0,sticky='ns')
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0,weight=1)
        self.sidebar.rowconfigure(8,weight=1)
        self.brand_image = None
        if local_profile is not None:
            from desktop.resources import company_logo
            self.brand_image = company_logo(184)
        self.brand = ctk.CTkLabel(self.sidebar,text='' if self.brand_image else 'BHLI  /  AUDIT',
                                image=self.brand_image,text_color=color('nav_accent'),font=font(18,'bold'))
        self.brand.grid(row=0,column=0,padx=16,pady=(24,16))
        self.toggle = button(self.sidebar,'Collapse navigation',self.collapse,width=200)
        self.toggle.grid(row=1,column=0,padx=12,pady=(0,24),sticky='ew')
        self.nav_buttons,self.images,self.tips = {},[],{}
        for row,destination in enumerate(destinations if destinations is not None else app.session.destinations,2):
            image=icon(self,'My Account' if destination in ('Local profile', 'Settings & Tools') else destination)
            self.images.append(image)
            b=button(self.sidebar,destination,lambda d=destination: app.navigate(d),image=image,
                      anchor='w',width=200)
            b.configure(fg_color=color('nav'),text_color='#F1F5F9',hover_color='#1E293B',border_color=color('nav'))
            b.grid(row=row,column=0,padx=12,pady=4,sticky='ew')
            self.nav_buttons[destination]=b
            self.tips[destination] = Tip(b, destination, delay=350 if self.offline else 0,
                                         enabled=(lambda: self.collapsed) if self.offline else None,
                                         outside=self.offline)
        self.footer = ctk.CTkLabel(self.sidebar,text='',font=font(11),text_color='#B8C5D6',wraplength=190)
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
        if local_profile is not None:
            name,identity_suffix=local_profile.name,'Local · self-declared'
        else:
            user=app.session.login.user
            name,identity_suffix=user.full_name,user.role
        display_name=name if len(name)<=28 else name[:27]+'…'
        self.identity=label(header,f'{display_name} · {identity_suffix}',12,True)
        self.identity.grid(row=1,column=0,sticky='w',padx=24,pady=(0,12))
        self.appearance = self.account = None
        self.menu = ctk.CTkFrame(main, fg_color=color('surface'))
        if not self.offline:
            self.appearance=option_menu(header,values=['Light','Dark'],command=app.set_theme,width=88,
                                       font=font(12),fg_color=color('primary'),text_color=color('on_primary'))
            self.appearance.set(ctk.get_appearance_mode())
            self.appearance.grid(row=0,column=1,rowspan=2,padx=8)
            self.account=button(header,'Account',self.toggle_menu,width=100)
            self.account.grid(row=0,column=2,rowspan=2,padx=(0,16))
            label(self.menu,f'{name} · {identity_suffix}',wraplength=450).pack(side='left',padx=16)
            button(self.menu,'My Account',lambda: app.navigate('My Account'),width=110).pack(side='left',padx=4,pady=8)
            button(self.menu,'Sign Out',app.logout,width=100).pack(side='left',padx=4,pady=8)
        self.content=ctk.CTkFrame(main,fg_color='transparent')
        self.content.grid(row=2,column=0,sticky='nsew',padx=24,pady=16)
        self.notice=Notice(main)
        self.notice.grid(row=3,column=0,sticky='ew',padx=24,pady=(0,12))
        tk.Misc.bind(self,'<Configure>',self.resize,add='+')
        if self._restored_state is not None:
            self.set_collapsed(self._restored_state)

    def collapse(self):
        if self.offline:
            self.app._sidebar_manual = True
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self,value):
        if self.offline:
            for tip in self.tips.values():
                tip.hide()
        if self.offline:
            self.app._sidebar_collapsed = bool(value)
        if self.offline and self.collapsed == value:
            return
        self.collapsed=value
        self.sidebar.configure(width=64 if value else 232)
        self.brand.configure(text='BH' if value else '' if self.brand_image else 'BHLI  /  AUDIT',
                             image=None if value else self.brand_image)
        if value and self.brand_image:
            # CTkLabel leaves its native photo set when configured with image=None.
            # Clear it explicitly so compact initials never crop the full artwork.
            self.brand._label.configure(image='')
        self.toggle.configure(text='›' if value else 'Collapse navigation',width=40 if value else 200)
        for name,b in self.nav_buttons.items():
            b.configure(text='' if value else name,width=40 if value else 200,anchor='center' if value else 'w')
        self.footer.configure(text='')

    def resize(self,event):
        if event.widget is not self:
            return
        if self.offline:
            if self._resize_job is not None:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after_idle(self._settle_resize)
        elif event.width/self._get_widget_scaling() < 1050 and not self.collapsed:
            self.set_collapsed(True)

    def _settle_resize(self):
        self._resize_job = None
        compact = self.winfo_width()/self._get_widget_scaling() < 1050
        previous = self._compact_band
        self._compact_band = compact
        if (not getattr(self.app, "_sidebar_manual", False) and compact
                and (previous is False or previous is None and self._restored_state is None)):
            self.set_collapsed(True)

    def select(self,name):
        if self.offline:
            for tip in self.tips.values():
                tip.hide()
        self.heading.configure(text=name)
        for destination,b in self.nav_buttons.items():
            selected = destination == name or (name in (('Audit Details', 'Audit History', 'Create Audit', 'Edit Audit') if self.offline else ('Audit Details',)) and destination=='Driver Audits')
            b.configure(fg_color=color('selected') if selected else color('nav'),
                        border_color=color('nav_accent') if selected else color('nav'))
        self.menu.grid_remove()

    def toggle_menu(self):
        if self.account is None:
            return
        if self.menu.winfo_ismapped():
            self.hide_menu()
        else:
            self.menu.grid(row=1,column=0,sticky='ew')
            self.menu.winfo_children()[1].focus_set()

    def hide_menu(self):
        self.menu.grid_remove()
        if self.account is not None:
            self.account.focus_set()
