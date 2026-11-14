"""Offline smoke checks for the exact runtime shipped in the release."""

import json
import subprocess
import time
from pathlib import Path

from app import __version__
from app.core.paths import browser_executable, tool


def run_diagnostics(window, report_path):
    report = {"version": __version__, "renderer": "qtwebengine"}
    try:
        import webview
        from playwright.sync_api import sync_playwright

        report["renderer"] = webview.guilib.renderer

        from app.core.paths import data_root
        from app.media.ffmpeg import extract_audio, probe_duration_seconds

        if not window.events.loaded.wait(40):
            raise RuntimeError("UI load timeout")
        for _ in range(100):
            if window.evaluate_js("typeof window.pywebview?.api?.bootstrap === 'function'"):
                break
            time.sleep(0.1)
        report["html"] = window.evaluate_js(
            "document.querySelector('h1').textContent === '网络ASR'"
        )
        window.run_js(
            "pywebview.api.bootstrap().then(r=>{window.__bridgeCheck=r.ok && !('api_key' in r.data.config)})"
        )
        for _ in range(100):
            if window.evaluate_js("window.__bridgeCheck === true"):
                break
            time.sleep(0.1)
        report["bridge"] = bool(window.evaluate_js("window.__bridgeCheck === true"))
        report["icon"] = window.evaluate_js(
            "document.querySelector('.brand-icon').complete && document.querySelector('.brand-icon').naturalWidth > 0"
        )
        report["navigation"] = window.evaluate_js(
            "document.querySelector('[data-page=settings]').click(); !document.querySelector('#page-settings').hidden"
        )
        for name in ("ffmpeg", "ffprobe"):
            result = subprocess.run(
                [tool(name), "-version"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=30,
            )
            report[name] = result.returncode == 0
        source = data_root() / "cache" / "中文 空格测试.wav"
        target = source.with_name("提取.wav")
        subprocess.run(
            [
                tool("ffmpeg"),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                str(source),
            ],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=True,
            timeout=30,
        )
        extract_audio(source, target)
        report["media"] = target.is_file() and probe_duration_seconds(target) > 0
        with sync_playwright() as pw:
            options = {"headless": True}
            if browser_executable():
                options["executable_path"] = browser_executable()
            browser = pw.chromium.launch(**options)
            page = browser.new_page()
            page.set_content("<title>runtime</title>")
            report["chromium"] = page.title() == "runtime"
            browser.close()
    except Exception as exc:
        report["error"] = type(exc).__name__
    finally:
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        window.destroy()
    return report
