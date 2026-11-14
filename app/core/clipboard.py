"""Unicode clipboard with explicit pointer types for 64-bit Windows."""

import ctypes
from ctypes import wintypes


def copy_text(text):
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = ctypes.c_void_p
    kernel.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel.GlobalFree.argtypes = [ctypes.c_void_p]
    user.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user.SetClipboardData.restype = ctypes.c_void_p
    raw = (text + "\0").encode("utf-16-le")
    handle = kernel.GlobalAlloc(0x42, len(raw))
    if not handle:
        raise RuntimeError("剪贴板内存分配失败")
    transferred = False
    try:
        ptr = kernel.GlobalLock(handle)
        if not ptr:
            raise RuntimeError("剪贴板暂不可用")
        ctypes.memmove(ptr, raw, len(raw))
        kernel.GlobalUnlock(handle)
        if not user.OpenClipboard(None):
            raise RuntimeError("剪贴板正被占用，请重试")
        try:
            if not user.EmptyClipboard() or not user.SetClipboardData(13, handle):
                raise RuntimeError("复制失败，请重试")
            transferred = True
        finally:
            user.CloseClipboard()
    finally:
        if not transferred:
            kernel.GlobalFree(handle)
