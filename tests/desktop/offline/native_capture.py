"""Capture only an owned native window; never sample the user's desktop."""
import ctypes
from ctypes import wintypes
import os


def capture_owned_window(app, destination):
    from PIL import Image
    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.GetBitmapBits.argtypes = [wintypes.HBITMAP, wintypes.LONG, ctypes.c_void_p]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    hwnd = user.GetAncestor(app.winfo_id(), 2)
    owner = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    assert owner.value == os.getpid(), 'Refusing to capture an unowned window'
    rect = wintypes.RECT()
    assert user.GetClientRect(hwnd, ctypes.byref(rect))
    width, height = rect.right, rect.bottom
    assert 100 < width <= 6000 and 100 < height <= 6000
    source = user.GetDC(hwnd)
    memory = bitmap = previous = None
    try:
        memory = gdi.CreateCompatibleDC(source)
        bitmap = gdi.CreateCompatibleBitmap(source, width, height)
        assert memory and bitmap
        previous = gdi.SelectObject(memory, bitmap)
        assert user.PrintWindow(hwnd, memory, 3), 'Owned-window rendering unavailable'
        raw = ctypes.create_string_buffer(width * height * 4)
        assert gdi.GetBitmapBits(bitmap, len(raw), raw) == len(raw)
        image = Image.frombuffer('RGB', (width, height), raw.raw, 'raw', 'BGRX', 0, 1)
        assert any(low != high for low, high in image.getextrema()), 'Owned capture is blank'
        image.save(destination)
    finally:
        if previous:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        if source:
            user.ReleaseDC(hwnd, source)
