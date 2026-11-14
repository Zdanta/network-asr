import os
import shutil
import sys
from pathlib import Path


def data_root():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AiVideoDesktop"
    for name in ("logs", "cache"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def tool(name):
    bundled = resource_root() / "resources" / "bin" / (name + ".exe")
    found = str(bundled) if bundled.exists() else shutil.which(name)
    if not found:
        raise RuntimeError("FFmpeg 不可用：缺少 " + name)
    return found


def setup_browser():
    browser = resource_root() / "resources" / "browsers"
    if browser.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser)


def browser_executable():
    custom = resource_root() / "resources" / "chromium-custom" / "chrome-win64" / "chrome.exe"
    return str(custom) if custom.exists() else None
