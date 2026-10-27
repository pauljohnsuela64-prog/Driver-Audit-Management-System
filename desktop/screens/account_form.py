"""Small password forms; secrets never enter application draft/state objects."""
import customtkinter as ctk
from desktop.components.common import button,entry,label,Notice
from desktop.theme import color

FORMS={
    'add':('Add Administrator',(('username','Username'),('full_name','Full name'),('password','Password'),('confirm_password','Confirm password'))),
    'reset':('Reset Password',(('admin_password','Your current password'),('new_password','New password'),('confirm_password','Confirm new password'))),
    'change':('Change My Password',(('current_password','Current password'),('new_password','New password'),('confirm_password','Confirm new password'))),
}


class AccountForm(ctk.CTkFrame):
    def __init__(self,parent,owner,kind,target=None):
        super().__init__(parent,fg_color=color('raised'),corner_radius=8)
        self.owner,self.kind,self.target=owner,kind,target
        self.columnconfigure(0,weight=1)
        title,fields=FORMS[kind]
        label(self,title,20).grid(row=0,column=0,sticky='w',padx=16,pady=(16,8))
        label(self,'New passwords require 15–128 characters.'+(f'\nTarget: {target.full_name} · {target.username} (#{target.id})' if target else ''),
              12,True,justify='left',wraplength=500).grid(row=1,column=0,sticky='w',padx=16,pady=(0,12))
        self.fields,self.errors={},{}
        for index,(key,text) in enumerate(fields):
            row=2+index*3
            label(self,text).grid(row=row,column=0,sticky='w',padx=16,pady=(6,4))
            widget=entry(self,show='•' if 'password' in key else None)
            widget.grid(row=row+1,column=0,sticky='ew',padx=16)
            widget.bind('<FocusIn>',lambda event,w=widget:owner.reveal(w),add='+')
            self.fields[key]=widget
            error=label(self,'',12,anchor='w',justify='left',wraplength=500)
            error.configure(text_color=color('error'));error.grid(row=row+2,column=0,sticky='ew',padx=16)
            self.errors[key]=error
        self.status=Notice(self);self.status.grid(row=20,column=0,sticky='ew',padx=16,pady=(8,0))
        controls=ctk.CTkFrame(self,fg_color='transparent');controls.grid(row=21,column=0,sticky='ew',padx=16,pady=(8,16))
        button(controls,'Cancel',owner.clear_form,width=110).pack(side='left')
        self.submit_button=button(controls,FORMS[kind][0],self.submit,True,width=190)
        self.submit_button.pack(side='right')

    def clear_secrets(self):
        for key,widget in self.fields.items():
            if 'password' in key:widget.configure(state='normal');widget.delete(0,'end')

    def submit(self):
        if self.owner.busy():return
        values={key:widget.get() for key,widget in self.fields.items()};errors={}
        for key,maximum in (('username',100),('full_name',200)):
            if key in values and not 1<=len(values[key].strip())<=maximum:errors[key]=f'Required; use at most {maximum} characters.'
        for key in ('current_password','admin_password'):
            if key in values and not 1<=len(values[key])<=128:errors[key]='Your current password is required (up to 128 characters).'
        new_key='password' if self.kind=='add' else 'new_password'
        if not 15<=len(values[new_key])<=128 or not values[new_key].strip():errors[new_key]='Use a nonblank password of 15–128 characters.'
        if values[new_key]!=values['confirm_password']:errors['confirm_password']='The passwords must match exactly.'
        if self.kind=='change' and values.get('current_password')==values[new_key]:errors[new_key]='Choose a different password.'
        for key,widget in self.errors.items():widget.configure(text=errors.get(key,''))
        if errors:
            self.status.show('Correct the required fields and password values above.')
            self.fields[next(iter(errors))].focus_set();return
        self.clear_secrets();values.pop('confirm_password')
        self.owner.start_action(self.kind,self.target,values)
