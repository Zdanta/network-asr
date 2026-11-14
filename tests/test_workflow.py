import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Config
from app.core.paths import tool
from app.repositories.history import History
from app.services.tasks import TaskService


class Workflow(unittest.TestCase):
    def test_audio_video_pipeline_and_failures(self):
        with tempfile.TemporaryDirectory(prefix="中文 空格 ") as d:
            p = Path(d)
            audio = p / "原始.wav"
            video = p / "视频.mp4"
            subprocess.run(
                [
                    tool("ffmpeg"),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    str(audio),
                ],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [
                    tool("ffmpeg"),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=size=128x128:duration=1",
                    "-i",
                    str(audio),
                    "-shortest",
                    str(video),
                ],
                capture_output=True,
                check=True,
            )
            h = History(p / "history.db")
            service = TaskService(h)
            config = Config(api_key="test", output_dir=d)
            for source in (audio, video):
                tid = h.create("local", str(source), d)
                with patch("app.services.tasks.VolcengineFlash.transcribe", return_value="测试稿"):
                    service.run(tid, config)
                    self.assertEqual(h.get(tid)["status"], "SUCCESS")
                    self.assertEqual(h.get(tid)["raw_text"], "测试稿")
                    self.assertTrue(source.exists())
            for error in ("ASR 请求超时", "ASR 密钥错误"):
                tid = h.create("local", str(audio), d)
                with patch(
                    "app.services.tasks.VolcengineFlash.transcribe", side_effect=RuntimeError(error)
                ):
                    service.run(tid, config)
                self.assertEqual(h.get(tid)["status"], "FAIL")
                self.assertEqual(h.get(tid)["error_message"], error)
            tid = h.create("douyin", "https://v.douyin.com/test/", d)
            with patch(
                "app.services.tasks.PlaywrightMediaDownloader.download",
                side_effect=RuntimeError("network"),
            ):
                service.run(tid, config)
            self.assertEqual(h.get(tid)["status"], "FAIL")
            self.assertIn("下载失败", h.get(tid)["error_message"])
