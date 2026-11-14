import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Config
from app.repositories.history import History
from app.ui.bridge import DesktopAPI


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.history = History(self.path / "history.db")
        self.api = DesktopAPI(
            self.history, Config(api_key="secret-user-key", output_dir=str(self.path))
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_key_never_in_bootstrap_and_blank_preserves_key(self):
        data = self.api.bootstrap()["data"]
        self.assertNotIn("api_key", data["config"])
        self.assertTrue(data["config"]["has_key"])
        with patch("app.ui.bridge.save_config") as save:
            result = self.api.save_settings({"api_key": ""})
            self.assertTrue(result["ok"])
            self.assertEqual(save.call_args.args[0].api_key, "secret-user-key")
            self.assertNotIn("api_key", result["data"])

    def test_delete_preserves_input_and_active_is_protected(self):
        source = self.path / "原始.wav"
        source.write_bytes(b"media")
        tid = self.history.create("local", str(source), str(self.path))
        self.assertFalse(self.api.delete_record(tid)["ok"])
        self.history.update(tid, status="FAIL")
        self.assertTrue(self.api.delete_record(tid)["ok"])
        self.assertTrue(source.exists())

    def test_clean_cannot_delete_user_input_or_external_path(self):
        source = self.path / "input.wav"
        source.write_bytes(b"media")
        tid = self.history.create("local", str(source), str(self.path))
        self.history.update(tid, status="FAIL", downloaded_path=str(source))
        self.assertFalse(self.api.clean_download(tid)["ok"])
        self.assertTrue(source.exists())
        tid = self.history.create("douyin", "https://v.douyin.com/test", str(self.path))
        self.history.update(tid, status="FAIL", downloaded_path=str(source))
        self.assertFalse(self.api.clean_download(tid)["ok"])
        self.assertTrue(source.exists())

    def test_clean_only_owned_download(self):
        tid = self.history.create("douyin", "https://v.douyin.com/test", str(self.path))
        folder = self.path / "AiVideoDesktop下载" / tid
        folder.mkdir(parents=True)
        target = folder / "video.mp4"
        target.write_bytes(b"download")
        self.history.update(tid, status="SUCCESS", downloaded_path=str(target), raw_text="稿件")
        self.assertTrue(self.api.clean_download(tid)["ok"])
        self.assertFalse(target.exists())
        self.assertEqual(self.history.get(tid)["raw_text"], "稿件")

    def test_invalid_start_no_record(self):
        self.assertFalse(self.api.start_task("douyin", "https://evil.com/", str(self.path))["ok"])
        self.assertEqual(self.history.list(), [])

    def test_export_uses_native_dialog_and_unicode(self):
        tid = self.history.create("local", "x.wav", str(self.path))
        self.history.update(tid, status="SUCCESS", raw_text="完整文字稿")

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                return [str(target)]

        target = self.path / "导出.txt"
        self.api._window = FakeWindow()
        self.assertTrue(self.api.export_text(tid)["ok"])
        self.assertEqual(target.read_text(encoding="utf-8-sig"), "完整文字稿")
