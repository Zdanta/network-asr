"""Narrow native bridge for trusted, bundled HTML. No HTTP business server."""

import functools
import os
import threading
from dataclasses import asdict
from pathlib import Path

from app import __version__
from app.core.config import Config, load_config, save_config
from app.core.paths import data_root
from app.repositories.history import History
from app.services.tasks import TaskService


def action(fn):
    @functools.wraps(fn)
    def wrapped(self, *args, **kwargs):
        try:
            with self._lock:
                return {"ok": True, "data": fn(self, *args, **kwargs)}
        except (ValueError, RuntimeError, OSError) as exc:
            message = str(exc)
            if self._config.api_key:
                message = message.replace(self._config.api_key, "[密钥]")
            return {
                "ok": False,
                "error": message
                if not isinstance(exc, OSError)
                else "文件读写失败，请检查目录权限及磁盘空间",
            }
        except Exception:
            return {"ok": False, "error": "操作失败，请检查素材、依赖与配置后重试"}

    return wrapped


class DesktopAPI:
    def __init__(self, history=None, config=None):
        self._window = None
        self._lock = threading.RLock()
        self._warning = ""
        self._history = history or History(data_root() / "history.db")
        self._history.recover()
        self._service = TaskService(self._history)
        try:
            self._config = config or load_config()
        except Exception:
            self._config = Config()
            self._warning = "配置无法读取或密钥无法解密，请在设置中重新填写并保存。"

    def _values(self):
        values = asdict(self._config)
        values.pop("api_key")
        values["has_key"] = bool(self._config.api_key)
        return values

    def _parse_config(self, values):
        base = asdict(self._config)
        for key in ("url", "resource_id", "model_name", "output_dir"):
            if key in values:
                base[key] = str(values[key]).strip()
        base["timeout"] = int(values.get("timeout", base["timeout"]))
        if values.get("api_key", "").strip():
            base["api_key"] = values["api_key"].strip()
        c = Config(**base)
        c.validate()
        return c

    def _task(self, tid):
        if not isinstance(tid, str) or len(tid) != 32:
            raise ValueError("无效记录")
        t = self._history.get(tid)
        if t["deleted_at"]:
            raise ValueError("记录已删除")
        return t

    @action
    def bootstrap(self):
        return {
            "config": self._values(),
            "warning": self._warning,
            "data_dir": str(data_root()),
            "version": __version__,
        }

    @action
    def snapshot(self):
        while not self._service.events.empty():
            self._service.events.get_nowait()
        return [
            {k: v for k, v in t.items() if k not in ("raw_text", "source_input")}
            for t in self._history.list()
        ]

    @action
    def detail(self, tid):
        return self._task(tid)

    @action
    def choose_file(self):
        import webview

        paths = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=(
                "音视频 (*.mp4;*.mov;*.m4v;*.avi;*.mkv;*.webm;*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg)",
            ),
        )
        return paths[0] if paths else None

    @action
    def choose_directory(self):
        import webview

        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return paths[0] if paths else None

    @action
    def save_settings(self, values):
        c = self._parse_config(values)
        save_config(c)
        self._config = c
        self._warning = ""
        return self._values()

    @action
    def start_task(self, kind, source, output_dir):
        if kind not in ("local", "douyin"):
            raise ValueError("请选择素材来源")
        source = str(source).strip()
        if not source:
            raise ValueError("请选择文件或粘贴抖音分享内容")
        if kind == "local":
            if not Path(source).is_absolute() or not Path(source).is_file():
                raise ValueError("原始文件不存在，请重新选择")
        else:
            from app.media.links import extract_url

            extract_url(source)
        c = self._parse_config({"output_dir": output_dir})
        tid = self._history.create(kind, source, c.output_dir)
        self._service.submit(tid, c)
        return tid

    @action
    def retry(self, tid):
        t = self._task(tid)
        if t["status"] not in ("FAIL", "INTERRUPTED"):
            raise ValueError("只能重试失败或中断的任务")
        c = self._parse_config({"output_dir": t["output_dir"]})
        self._service.submit(tid, c)

    @action
    def delete_record(self, tid):
        self._task(tid)
        self._history.delete(tid)

    @action
    def clean_download(self, tid):
        t = self._task(tid)
        if t["status"] in ("PENDING", "RUNNING"):
            raise ValueError("请等待任务结束后清理")
        if t["source_type"] != "douyin" or not t["downloaded_path"]:
            raise ValueError("此记录没有可清理的应用下载文件")
        target = Path(t["downloaded_path"])
        expected = (Path(t["output_dir"]) / "AiVideoDesktop下载" / tid).resolve()
        if target.is_symlink() or target.resolve().parent != expected:
            raise ValueError("文件路径校验失败，拒绝删除")
        target.unlink(missing_ok=True)
        self._history.update(tid, downloaded_path=None)

    @action
    def open_folder(self, tid):
        t = self._task(tid)
        if t["source_type"] == "douyin" and not t["downloaded_path"]:
            raise ValueError("此任务还没有下载文件")
        folder = Path(t["downloaded_path"] or t["source_path"] or t["source_input"]).parent
        if not folder.is_dir():
            raise ValueError("素材目录不存在")
        os.startfile(str(folder))

    @action
    def export_text(self, tid):
        import webview

        t = self._task(tid)
        if not t["raw_text"]:
            raise ValueError("此任务还没有文字稿")
        paths = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=tid + ".txt", file_types=("文字稿 (*.txt)",)
        )
        if not paths:
            return False
        path = paths[0] if isinstance(paths, (tuple, list)) else paths
        Path(path).write_text(t["raw_text"], encoding="utf-8-sig")
        return True

    @action
    def copy_text(self, tid):
        t = self._task(tid)
        if not t["raw_text"]:
            raise ValueError("此任务还没有文字稿")
        from app.core.clipboard import copy_text

        copy_text(t["raw_text"])
