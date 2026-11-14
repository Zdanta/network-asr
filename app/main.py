"""Desktop entry point. The release carries its own Qt WebEngine runtime."""

import base64
import ctypes
import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

from app.core.paths import data_root, resource_root, setup_browser


def page_html():
    ui = resource_root() / "resources" / "ui"
    icon = resource_root() / "resources" / "icons" / "app-icon.png"
    return (
        (ui / "index.html")
        .read_text(encoding="utf-8")
        .replace("/*__CSS__*/", (ui / "style.css").read_text(encoding="utf-8"))
        .replace("/*__JS__*/", (ui / "app.js").read_text(encoding="utf-8"))
        .replace("__APP_ICON__", base64.b64encode(icon.read_bytes()).decode("ascii"))
    )


def main():
    smoke_mode = "--smoke-test" in sys.argv
    smoke_data = None
    if smoke_mode:
        smoke_data = tempfile.TemporaryDirectory(prefix="network-asr-check-")
        os.environ["LOCALAPPDATA"] = smoke_data.name
    mutex_name = (
        "Local\\AiVideoDesktop.SmokeTest" if smoke_mode else "Local\\AiVideoDesktop.SingleInstance"
    )
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, "请使用已经打开的网络ASR窗口。", "应用已运行", 0x40)
        return
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AiVideoDesktop.NetworkASR")
    setup_browser()
    os.environ["QT_API"] = "pyside6"
    os.environ.setdefault("QT_OPENGL", "software")
    handler = RotatingFileHandler(
        data_root() / "logs" / "app.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(level=logging.ERROR, handlers=[handler])
    logging.getLogger("app.media.downloader").disabled = True
    import webview

    from app.ui.bridge import DesktopAPI

    api = DesktopAPI()
    window = webview.create_window(
        "网络ASR",
        html=page_html(),
        js_api=api,
        width=1260,
        height=920,
        min_size=(760, 620),
        background_color="#fffef9",
        text_select=True,
        zoomable=True,
    )
    api._window = window

    def closing():
        if api._service.active:
            return window.create_confirmation_dialog(
                "退出", "仍有任务在处理。退出会中断任务，下次启动可重试。"
            )

    window.events.closing += closing
    options = dict(
        gui="qt",
        private_mode=True,
        storage_path=str(data_root() / "cache" / "webview"),
        icon=str(resource_root() / "resources" / "icons" / "app.ico"),
    )
    try:
        if smoke_mode:
            from app.core.diagnostics import run_diagnostics

            report_path = sys.argv[sys.argv.index("--smoke-test") + 1]
            webview.start(run_diagnostics, (window, report_path), **options)
        else:
            webview.start(**options)
    finally:
        logging.shutdown()
        ctypes.windll.kernel32.CloseHandle(mutex)
        if smoke_data:
            smoke_data.cleanup()
