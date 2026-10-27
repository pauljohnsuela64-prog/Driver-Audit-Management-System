"""Capture only the test application HWND using Windows GDI and stdlib PNG encoding."""
import ctypes
from ctypes import wintypes
import struct
import zlib


def capture(hwnd,path):
    user,gdi=ctypes.windll.user32,ctypes.windll.gdi32
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
    user.GetAncestor.restype=wintypes.HWND
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes=[wintypes.HWND]
    user.GetDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC]
    gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HANDLE]
    gdi.SelectObject.restype=wintypes.HANDLE
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi.DeleteObject.argtypes=[wintypes.HANDLE]
    gdi.DeleteDC.argtypes=[wintypes.HDC]
    hwnd=user.GetAncestor(hwnd,2)
    rect=wintypes.RECT()
    if not user.GetWindowRect(hwnd,ctypes.byref(rect)):
        raise RuntimeError('Cannot locate native test window')
    width,height=rect.right-rect.left,rect.bottom-rect.top
    source=user.GetDC(hwnd)
    memory=gdi.CreateCompatibleDC(source)
    bitmap=gdi.CreateCompatibleBitmap(source,width,height)
    previous=gdi.SelectObject(memory,bitmap)
    try:
        if not user.PrintWindow(hwnd,memory,2):
            raise RuntimeError('Native application capture unavailable')
        gdi.SelectObject(memory,previous)
        header=struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,width*height*4,0,0,0,0)
        info=ctypes.create_string_buffer(header+b'\0'*16)
        pixels=ctypes.create_string_buffer(width*height*4)
        if not gdi.GetDIBits(memory,bitmap,0,height,pixels,info,0):
            raise RuntimeError('Native application pixels unavailable')
        raw=pixels.raw
        rows=[]
        for y in range(height):
            bgra=raw[y*width*4:(y+1)*width*4]
            rgb=bytearray(width*3)
            rgb[0::3],rgb[1::3],rgb[2::3]=bgra[2::4],bgra[1::4],bgra[0::4]
            rows.append(b'\0'+rgb)
        def chunk(kind,data):
            return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',width,height,8,2,0,0,0))+
                         chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))
    finally:
        gdi.SelectObject(memory,previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd,source)
