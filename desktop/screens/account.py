import customtkinter as ctk
from desktop.components.common import label
from desktop.theme import color


class Account(ctk.CTkScrollableFrame):
    def __init__(self,parent,app):
        super().__init__(parent,fg_color=color('surface'),corner_radius=12)
        user=app.session.login.user
        label(self,'My Account',28).pack(anchor='w',padx=24,pady=(24,16))
        for title,value in [('Full name',user.full_name),('Username',user.username),('Role',user.role),
                            ('Session expires (UTC)',app.session.login.expires_at.strftime('%Y-%m-%d %H:%M UTC'))]:
            label(self,title,12,True).pack(anchor='w',padx=24,pady=(16,0))
            label(self,value,16,wraplength=500,justify='left').pack(anchor='w',padx=24,pady=(0,8))
        label(self,'Account editing is not part of this desktop phase.',muted=True).pack(anchor='w',padx=24,pady=24)
