"""Source/frozen resource paths and Windows branding; no network or database."""
from pathlib import Path
import sys
from desktop.version import APP_ID


def resource_path(name):
    if name not in ('bhli.ico',):raise ValueError('Unknown application resource')
    return Path(__file__).resolve().parent/'assets'/name


def set_app_identity():
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def fatal_startup():
    message='BHLI Audit could not start (BHLI-START-01). Contact your administrator or reinstall the application. No credentials were displayed.'
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'BHLI Audit — startup error',0x10)
    else:
        print(message,file=sys.stderr)
