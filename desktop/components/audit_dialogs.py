"""Small native confirmations with explicit focus and owned-widget cleanup."""
import customtkinter as ctk
import tkinter as tk
from desktop.components.common import button, label, destroy_view
from desktop.theme import color,resolved


class Confirmation(tk.Toplevel):
    def __init__(self,app,title,message,accepted,confirm_text='Discard changes',destructive=False):
        super().__init__(app)
        self.app,self.accepted=app,accepted
        self.origin=app.focus_get()
        app.dialog=self
        self.title(title)
        # CTkToplevel installs bind_all focus callbacks and delayed Windows
        # titlebar work. Native Toplevel avoids those cross-dialog lifetimes.
        self.configure(bg=resolved('surface'))
        self.geometry('520x310')
        self.minsize(440,280)
        self.transient(app)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=1)
        label(self,title,22).grid(row=0,column=0,sticky='w',padx=24,pady=(24,12))
        self.message=label(self,message,justify='left',anchor='nw',wraplength=450)
        self.message.grid(row=1,column=0,sticky='nsew',padx=24,pady=(0,16))
        controls=ctk.CTkFrame(self,fg_color='transparent')
        controls.grid(row=2,column=0,sticky='ew',padx=24,pady=(0,24))
        self.cancel_button=button(controls,'Cancel',self.cancel,width=110)
        self.cancel_button.pack(side='left')
        self.confirm_button=button(controls,confirm_text,self.accept,True,width=210)
        self.confirm_button.pack(side='right')
        if destructive:
            self.confirm_button.configure(fg_color=('#B91C1C','#991B1B'),text_color='#FFFFFF',
                                          hover_color=('#991B1B','#7F1D1D'),border_color=color('error'))
        self.bind('<Escape>',lambda e:self.cancel() or 'break')
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.bind('<Configure>',self.resize,add='+')
        self.after_idle(self.activate)

    def resize(self,event):
        if event.widget is self:
            self.message.configure(wraplength=max(280,int(event.width/self.app._get_widget_scaling())-48))

    def activate(self):
        if self.winfo_exists():
            self.grab_set()
            self.cancel_button.focus_set()
            self.cancel_button.bind('<Tab>',lambda e:self._focus(self.confirm_button))
            self.confirm_button.bind('<Tab>',lambda e:self._focus(self.cancel_button))
            self.cancel_button.bind('<Shift-Tab>',lambda e:self._focus(self.confirm_button))
            self.confirm_button.bind('<Shift-Tab>',lambda e:self._focus(self.cancel_button))

    @staticmethod
    def _focus(widget):
        widget.focus_set()
        return 'break'

    def dismiss(self):
        self.grab_release()
        self.app.dialog=None
        destroy_view(self)
        if self.origin and self.origin.winfo_exists():
            self.origin.focus_set()
        else:
            self.app.focus_set()

    def cancel(self):
        self.dismiss()

    def accept(self):
        callback=self.accepted
        self.dismiss()
        callback()


def confirm(app,title,message,accepted,confirm_text='Discard changes',destructive=False):
    if not app.dialog:
        return Confirmation(app,title,message,accepted,confirm_text,destructive)
