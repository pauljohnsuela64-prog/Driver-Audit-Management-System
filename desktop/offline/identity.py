"""Independent Windows identity and data location; never reads online settings."""
import os
from pathlib import Path
import sys

PRODUCT = 'BHLI Audit Offline'
VERSION = '1.0.0-offline-dev'
ARTIFACT_VERSION = '1.0.0-dev'
APP_ID = 'BHLI.Audit.Offline.Desktop'
MUTEX = r'Local\BHLI.Audit.Offline.Desktop.Running'
INSTALLER_GUID = '6C429C06-F81C-4C60-A5BC-C8A0E0987F5D'


def database_path(environ=None):
    env = os.environ if environ is None else environ
    value = env.get('LOCALAPPDATA', '')
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('The Windows local data folder is unavailable.')
    root = Path(value)
    if not root.is_absolute():
        raise ValueError('The Windows local data folder must be absolute.')
    return root / PRODUCT / 'bhli_offline.db'


def set_app_identity():
    if sys.platform == 'win32':
        import ctypes
        if ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID) < 0:
            raise RuntimeError('The offline application identity is unavailable.')


def running_mutex():
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, MUTEX)
    if not handle:
        raise RuntimeError('The offline application lifetime marker is unavailable.')
    if ctypes.get_last_error() == 183:
        release_mutex(handle)
        raise RuntimeError('BHLI Audit Offline is already running. Use the existing window.')
    return handle


def release_mutex(handle):
    if handle:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)
