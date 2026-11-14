import base64
import ctypes
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]


def crypt(value, decrypt=False):
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    src = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dst = Blob()
    api = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    if not api(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise RuntimeError("密钥解密失败，请在设置中重新输入并保存" if decrypt else "密钥加密失败")
    try:
        result = ctypes.string_at(dst.data, dst.size)
        return result.decode("utf-8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)
