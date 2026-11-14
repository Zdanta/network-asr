import tempfile
import unittest
from pathlib import Path

import httpx

from app.core.config import Config, load_config, save_config
from app.media.downloader import _same_item_audio
from app.media.links import extract_url
from app.providers.asr.volcengine import VolcengineFlash
from app.repositories.history import History
from app.services.tasks import TaskService


class Tests(unittest.TestCase):
    def test_config_dpapi(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            c = Config(api_key="private-test-key")
            save_config(c, p)
            self.assertNotIn(c.api_key, p.read_text())
            self.assertEqual(load_config(p), c)

    def test_history_recovery_delete_preserves_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source = p / "original.wav"
            source.write_bytes(b"original")
            h = History(p / "history.db")
            tid = h.create("local", str(source), d)
            h.update(tid, status="RUNNING")
            History(p / "history.db").recover()
            self.assertEqual(h.get(tid)["status"], "INTERRUPTED")
            h.delete(tid)
            self.assertTrue(source.exists())
            self.assertEqual(h.list(), [])

    def test_links(self):
        self.assertEqual(
            extract_url("分享 https://v.douyin.com/abc/， 复制打开"), "https://v.douyin.com/abc/"
        )
        for s in ["https://douyin.com.evil.com/a", "https://evil.com/a", "没有链接"]:
            with self.assertRaises(ValueError):
                extract_url(s)

    def test_companion_excludes_music(self):
        payload = {
            "aweme_id": "123",
            "video": {"audio": {"url_list": ["https://x.com/audio/a.m4a"]}},
            "music": {"url_list": ["https://x.com/music/b.mp3"]},
        }
        self.assertEqual(_same_item_audio(payload, "123"), ["https://x.com/audio/a.m4a"])
        self.assertEqual(_same_item_audio(payload, "456"), [])

    def test_asr_protocol_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            p.write_bytes(b"audio")
            c = Config(api_key="test")

            def success(req):
                self.assertEqual(req.headers["X-Api-Key"], "test")
                self.assertIn(b"YXVkaW8=", req.content)
                return httpx.Response(
                    200,
                    headers={"X-Api-Status-Code": "20000000"},
                    json={"result": {"text": "测试文字"}},
                )

            self.assertEqual(
                VolcengineFlash(c, httpx.MockTransport(success)).transcribe(p), "测试文字"
            )
            for response in [
                httpx.Response(401),
                httpx.Response(200, json={}),
                httpx.Response(200, headers={"X-Api-Status-Code": "45000001"}, json={}),
            ]:
                with self.assertRaises(RuntimeError):
                    VolcengineFlash(c, httpx.MockTransport(lambda req: response)).transcribe(p)

            def timeout(req):
                raise httpx.ReadTimeout("secret")

            with self.assertRaisesRegex(RuntimeError, "超时"):
                VolcengineFlash(c, httpx.MockTransport(timeout)).transcribe(p)

    def test_worker_failure_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            h = History(Path(d) / "history.db")
            tid = h.create("local", "missing.wav", d)
            s = TaskService(h)
            s.run(tid, Config())
            self.assertEqual(h.get(tid)["status"], "FAIL")
            self.assertIn("配置", h.get(tid)["error_message"])


if __name__ == "__main__":
    unittest.main()


class LimitTests(unittest.TestCase):
    def test_oversized_audio_never_reaches_network(self):
        from unittest.mock import Mock

        path = Mock()
        path.stat.return_value.st_size = 100 * 1024 * 1024 + 1
        with self.assertRaisesRegex(ValueError, "100MB"):
            VolcengineFlash(Config(api_key="test")).transcribe(path)

    def test_missing_history_is_readable_error(self):
        with tempfile.TemporaryDirectory() as d:
            history = History(Path(d) / "history.db")
            with self.assertRaisesRegex(ValueError, "不存在"):
                history.get("missing")
