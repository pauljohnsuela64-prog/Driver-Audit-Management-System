"""Approved semantic tokens and local monochrome navigation artwork."""
import tkinter as tk
import customtkinter as ctk

COLORS = {
    'bg': ('#F1F5F9', '#0B1220'), 'surface': ('#FFFFFF', '#111C2E'),
    'raised': ('#F8FAFC', '#17253B'), 'text': ('#0F172A', '#F1F5F9'),
    'muted': ('#475569', '#B8C5D6'), 'nav': ('#0F172A', '#080F1D'),
    'nav_text': ('#F1F5F9', '#F1F5F9'), 'primary': ('#0F766E', '#2DD4BF'),
    'on_primary': ('#FFFFFF', '#0B1220'), 'hover': ('#115E59', '#5EEAD4'),
    'border': ('#64748B', '#71839B'), 'focus': ('#0F766E', '#5EEAD4'),
    'error': ('#B91C1C', '#FCA5A5'), 'selected': ('#134E4A', '#134E4A'),
}


def color(name):
    return COLORS[name]


def resolved(name):
    return COLORS[name][ctk.get_appearance_mode() == 'Dark']


def font(size=14, weight='normal'):
    return ctk.CTkFont(family='Segoe UI', size=size, weight=weight)


def icon(master, name, ink='#F1F5F9'):
    """Pixel-rendered line artwork, with no font glyph or external asset dependency."""
    image = tk.PhotoImage(master=master, width=20, height=20)
    shapes = {
        'Dashboard': [(3,3,8,8),(12,3,17,8),(3,12,8,17),(12,12,17,17)],
        'Driver Audits': [(4,2,16,18),(7,6,13,6),(7,10,13,10),(7,14,13,14)],
        'Employee Accounts': [(7,2,13,8),(3,12,17,18)],
        'Administrator Activity': [(3,3,17,17),(6,10,9,13),(9,13,14,6)],
        'My Account': [(7,3,13,9),(4,13,16,17)],
    }
    def line(x0,y0,x1,y1):
        steps = max(abs(x1-x0),abs(y1-y0),1)
        for step in range(steps+1):
            x,y = round(x0+(x1-x0)*step/steps),round(y0+(y1-y0)*step/steps)
            image.put(ink, to=(x,y,min(x+2,20),min(y+2,20)))
    for x0,y0,x1,y1 in shapes[name]:
        if x0 != x1 and y0 != y1 and name != 'Administrator Activity':
            for coords in [(x0,y0,x1,y0),(x1,y0,x1,y1),(x1,y1,x0,y1),(x0,y1,x0,y0)]:
                line(*coords)
        else:
            line(x0,y0,x1,y1)
    return image
