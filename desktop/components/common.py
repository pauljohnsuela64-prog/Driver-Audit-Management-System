import customtkinter as ctk
from desktop.theme import color, font


def label(parent, text, size=14, muted=False, **kwargs):
    return ctk.CTkLabel(parent, text=text, font=font(size), text_color=color('muted' if muted else 'text'), **kwargs)


def button(parent, text, command, primary=False, **kwargs):
    b = ctk.CTkButton(parent, text=text, command=command, height=40, corner_radius=8, font=font(),
                      fg_color=color('primary' if primary else 'raised'),
                      text_color=color('on_primary' if primary else 'text'),
                      hover_color=color('hover' if primary else 'bg'),
                      border_width=2, border_color=color('primary' if primary else 'border'), **kwargs)
    b._canvas.configure(takefocus=1)
    b.bind('<Return>', lambda event: b.invoke())
    b.bind('<space>', lambda event: b.invoke())
    b.bind('<FocusIn>', lambda event: b.configure(border_color=color('focus')))
    b.bind('<FocusOut>', lambda event: b.configure(border_color=color('primary' if primary else 'border')))
    return b


def entry(parent, placeholder='', show=None, **kwargs):
    return ctk.CTkEntry(parent, height=40, font=font(), corner_radius=8,
                        fg_color=color('surface'), text_color=color('text'),
                        border_color=color('border'), placeholder_text=placeholder,
                        show=show, **kwargs)


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
        widget.bind('<Enter>', self.show, add='+')
        widget.bind('<FocusIn>', self.show, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<FocusOut>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def show(self, event=None):
        if self.window is None and self.widget.winfo_exists():
            self.window = ctk.CTkToplevel(self.widget)
            self.window.overrideredirect(True)
            self.window.geometry(f'+{self.widget.winfo_rootx()+60}+{self.widget.winfo_rooty()+8}')
            label(self.window,self.text).pack(padx=10,pady=6)

    def hide(self, event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None
