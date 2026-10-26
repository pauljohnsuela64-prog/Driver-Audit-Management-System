import customtkinter as ctk
import tkinter as tk
from desktop.theme import color, font, resolved


def destroy_view(widget):
    """Cancel this subtree's Tcl timers before Tk deletes their command names.

    Tk does not cancel `after` on widget destruction. CTk uses those callbacks
    internally; stale names can be reused for unrelated commands on a new screen.
    Keep root polling and timers belonging to other screens untouched.
    """
    target=widget._parent_frame if isinstance(widget,ctk.CTkScrollableFrame) else widget
    commands={}
    def collect(current):
        commands.update({name:current for name in (getattr(current,'_tclCommands',None) or ())})
        for child in current.winfo_children():
            collect(child)
    collect(target)
    for timer in target.tk.call('after','info'):
        script,_=target.tk.call('after','info',timer)
        parts=target.tk.splitlist(script)
        if parts and parts[0] in commands:
            commands[parts[0]].after_cancel(timer)
    widget.destroy()


def label(parent, text, size=14, muted=False, **kwargs):
    return ctk.CTkLabel(parent, text=text, font=font(size), text_color=color('muted' if muted else 'text'), **kwargs)


def button(parent, text, command, primary=False, **kwargs):
    b = ctk.CTkButton(parent, text=text, command=command, height=40, corner_radius=8, font=font(),
                      fg_color=color('primary' if primary else 'raised'),
                      text_color=color('on_primary' if primary else 'text'),
                      hover_color=color('hover' if primary else 'bg'),
                      border_width=2, border_color=color('primary' if primary else 'border'), **kwargs)
    b._canvas.configure(takefocus=1)
    b.bind('<Return>', lambda event=None: b.invoke())
    b.bind('<space>', lambda event=None: b.invoke())
    b.bind('<FocusIn>', lambda event=None: b.configure(border_color=color('focus')))
    b.bind('<FocusOut>', lambda event=None: b.configure(border_color=color('primary' if primary else 'border')))
    return b


def entry(parent, placeholder='', show=None, **kwargs):
    widget = ctk.CTkEntry(parent, height=40, font=font(), corner_radius=8,
                        fg_color=color('surface'), text_color=color('text'),
                        border_color=color('border'), placeholder_text=placeholder,
                        show=show, **kwargs)
    widget.bind('<FocusIn>',lambda e=None:widget.configure(border_color=color('focus')),add='+')
    widget.bind('<FocusOut>',lambda e=None:widget.configure(border_color=color('border')),add='+')
    return widget


def option_menu(parent,**kwargs):
    widget=ctk.CTkOptionMenu(parent,**kwargs)
    widget.configure(button_color=color('primary'),button_hover_color=color('hover'),
                     dropdown_fg_color=color('surface'),dropdown_text_color=color('text'),
                     dropdown_hover_color=color('raised'))
    widget._canvas.configure(takefocus=1)
    widget.bind('<Return>',lambda e=None:widget._open_dropdown_menu())
    widget.bind('<space>',lambda e=None:widget._open_dropdown_menu())
    widget.bind('<FocusIn>',lambda e=None:widget.configure(button_color=color('focus')))
    widget.bind('<FocusOut>',lambda e=None:widget.configure(button_color=color('primary')))
    return widget


def checkbox(parent,**kwargs):
    widget=ctk.CTkCheckBox(parent,**kwargs,fg_color=color('primary'),hover_color=color('hover'),
                           text_color=color('text'),checkmark_color=color('on_primary'),border_color=color('border'))
    widget._canvas.configure(takefocus=1)
    widget.bind('<space>',lambda e=None:widget.toggle())
    widget.bind('<Return>',lambda e=None:widget.toggle())
    widget.bind('<FocusIn>',lambda e=None:widget.configure(border_color=color('focus')))
    widget.bind('<FocusOut>',lambda e=None:widget.configure(border_color=color('border')))
    return widget


class Notice(ctk.CTkLabel):
    def __init__(self, parent):
        super().__init__(parent, text='', font=font(), anchor='w', justify='left',
                         text_color=color('error'), wraplength=600)

    def show(self, message, error=True):
        self.configure(text=message, text_color=color('error' if error else 'muted'))


class StatePanel(ctk.CTkFrame):
    def __init__(self, parent, title, message='', retry=None):
        super().__init__(parent, fg_color=color('surface'), corner_radius=12)
        label(self, title, 20).pack(padx=24,pady=(32,8))
        label(self, message, muted=True, wraplength=450, justify='center').pack(padx=24,pady=(0,16))
        if retry:
            button(self,'Retry',retry).pack(pady=(0,24))


class Tip:
    def __init__(self, widget, text):
        self.widget, self.text, self.window = widget, text, None
        # Bind the persistent button frame, not CTk's replaceable text/image labels.
        for event,handler in [('<Enter>',self.show),('<FocusIn>',self.show),('<Leave>',self.hide),
                              ('<FocusOut>',self.hide),('<Destroy>',self.hide)]:
            tk.Misc.bind(widget,event,handler,add='+')

    def show(self, event=None):
        if self.window is None and self.widget.winfo_exists():
            # Tooltips must not trigger CTkToplevel's delayed focus restoration.
            self.window = tk.Toplevel(self.widget,takefocus=False,bg=resolved('surface'))
            self.window.overrideredirect(True)
            self.window.geometry(f'+{self.widget.winfo_rootx()+60}+{self.widget.winfo_rooty()+8}')
            tk.Label(self.window,text=self.text,bg=resolved('surface'),fg=resolved('text'),
                     font=('Segoe UI',-14)).pack(padx=10,pady=6)

    def hide(self, event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None
