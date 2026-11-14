import logging
import queue
import shutil
import threading
from pathlib import Path

from app.core.paths import data_root, setup_browser, tool
from app.media.downloader import PlaywrightMediaDownloader
from app.media.ffmpeg import extract_audio, probe_duration_seconds
from app.media.links import extract_url
from app.providers.asr.base import ASRProvider
from app.providers.asr.volcengine import VolcengineFlash
from app.repositories.history import now


class TaskService:
    def __init__(self, history):
        self.history = history
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.active = set()
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, tid, config):
        with self.lock:
            if tid in self.active:
                raise ValueError("任务已在队列中")
            self.active.add(tid)
        try:
            self._prepare(tid, config)
        except Exception:
            with self.lock:
                self.active.discard(tid)
            raise

    def _prepare(self, tid, config):
        self.history.update(
            tid,
            status="PENDING",
            stage="等待处理",
            error_message=None,
            raw_text=None,
            finished_at=None,
        )
        self.jobs.put((tid, config))

    def _loop(self):
        while True:
            tid, config = self.jobs.get()
            try:
                self.run(tid, config)
            except Exception:
                logging.error("任务状态无法写入，task=%s", tid)
            finally:
                with self.lock:
                    self.active.discard(tid)
                self.jobs.task_done()

    def stage(self, tid, text, **values):
        self.history.update(tid, stage=text, **values)
        self.events.put(tid)

    def run(self, tid, config):
        temp = data_root() / "cache" / tid
        try:
            self.stage(tid, "检查配置与素材", status="RUNNING", started_at=now(), progress=None)
            config.validate()
            tool("ffmpeg")
            tool("ffprobe")
            task = self.history.get(tid)
            temp.mkdir(parents=True, exist_ok=True)
            if task["source_type"] == "local":
                source = Path(task["source_input"])
                if not source.is_file():
                    raise ValueError("文件读写失败：原始文件不存在")
                if source.suffix.lower() not in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".avi",
                    ".mkv",
                    ".webm",
                    ".mp3",
                    ".wav",
                    ".m4a",
                    ".aac",
                    ".flac",
                    ".ogg",
                }:
                    raise ValueError("文件格式不支持")
            else:
                url = extract_url(task["source_input"])
                self.stage(tid, "解析分享页并下载（可能需要等待浏览器）")
                setup_browser()
                try:
                    media = PlaywrightMediaDownloader().download(url, tid)
                except Exception as exc:
                    if "音轨" in str(exc):
                        raise RuntimeError("视频无音轨，未找到可确认的原声") from None
                    raise RuntimeError(
                        "抖音解析或下载失败：视频可能不可访问、需要登录，或网络受限"
                    ) from None
                cached = data_root() / "cache" / media.relative_path
                out = Path(task["output_dir"]) / "AiVideoDesktop下载" / tid
                out.mkdir(parents=True, exist_ok=True)
                source = out / media.storage_file_name
                shutil.move(str(cached), str(source))
                self.stage(
                    tid, "下载完成", downloaded_path=str(source), source_title=media.title or tid
                )
            duration = probe_duration_seconds(source)
            if duration is not None and duration > 7200:
                raise ValueError("音频超过 2 小时，请分段后重试")
            self.stage(
                tid,
                "探测音轨并提取 16kHz 单声道音频",
                source_path=str(source),
                duration_seconds=duration,
            )
            audio = temp / "audio.wav"
            extract_audio(source, audio)
            self.stage(
                tid, "等待 ASR 返回识别结果", audio_path=str(audio), duration_seconds=duration
            )
            provider: ASRProvider = VolcengineFlash(config)
            text = provider.transcribe(audio)
            self.stage(
                tid, "完成", status="SUCCESS", progress=100, raw_text=text, finished_at=now()
            )
        except (RuntimeError, ValueError) as exc:
            self.stage(
                tid,
                "处理失败",
                status="FAIL",
                error_message=str(exc).replace(config.api_key, "[密钥]")
                if config.api_key
                else str(exc),
                finished_at=now(),
            )
        except OSError:
            self.stage(
                tid,
                "处理失败",
                status="FAIL",
                error_message="文件读写失败，请检查磁盘空间及目录权限",
                finished_at=now(),
            )
        except Exception:
            self.stage(
                tid,
                "处理失败",
                status="FAIL",
                error_message="处理异常，请检查素材、依赖及配置后重试",
                finished_at=now(),
            )
        finally:
            shutil.rmtree(temp, ignore_errors=True)
