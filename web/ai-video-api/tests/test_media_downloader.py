import json
import unittest
from itertools import count
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.media_import.downloader import (
    PlaywrightMediaDownloader,
    _douyin_media_candidates,
    _find_douyin_video,
    _decode_router_data,
    _extract_media_urls_from_payload,
    _looks_like_audio_candidate,
    _payload_title,
    _rank_media_urls,
    _to_no_watermark_url,
)


class MediaDownloaderTest(unittest.TestCase):
    def test_static_assets_are_not_media_candidates(self) -> None:
        urls = [
            "https://example.com/pre-build-player.js",
            "https://example.com/static-style.css",
            "https://example.com/video.mp4",
        ]

        self.assertEqual(_rank_media_urls(urls), ["https://example.com/video.mp4"])

    def test_extracts_douyin_payload_media_urls(self) -> None:
        payload = {
            "aweme_detail": {
                "video": {
                    "play_addr": {
                        "url_list": [
                            "https://v3.douyinvod.com/video/tos/example?mime_type=video_mp4",
                        ]
                    },
                    "bit_rate": [
                        {
                            "play_addr": {
                                "url_list": [
                                    "https://v9.bytevod.com/video/example?mime_type=video_mp4",
                                ]
                            }
                        }
                    ],
                }
            }
        }

        self.assertEqual(
            _extract_media_urls_from_payload(payload),
            [
                "https://v3.douyinvod.com/video/tos/example?mime_type=video_mp4",
                "https://v9.bytevod.com/video/example?mime_type=video_mp4",
            ],
        )

    def test_decodes_douyin_share_router_data(self) -> None:
        html = """
        <script>
        window._ROUTER_DATA = {"loaderData":{"page":{"item_list":[{"desc":"测试视频","video":{"play_addr":{"url_list":["https://aweme.snssdk.com/aweme/v1/playwm/?video_id=123"]}}}]}}};
        </script>
        """

        payload = _decode_router_data(html)

        self.assertEqual(_payload_title([payload]), "测试视频")
        self.assertEqual(
            _rank_media_urls(_extract_media_urls_from_payload(payload)),
            [
                "https://aweme.snssdk.com/aweme/v1/play/?video_id=123",
                "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=123",
            ],
        )

    def test_converts_and_prioritizes_no_watermark_url(self) -> None:
        watermarked = "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=123&watermark=1"
        clean = "https://aweme.snssdk.com/aweme/v1/play/?video_id=123"

        self.assertEqual(_to_no_watermark_url(watermarked), clean)
        self.assertEqual(_rank_media_urls([watermarked, clean]), [clean, watermarked])

    def test_video_candidates_are_ranked_before_separate_audio(self) -> None:
        audio_url = "https://v3.douyinvod.com/audio/tos/example?mime_type=audio"
        video_url = "https://v3.douyinvod.com/video/tos/example?mime_type=video_mp4"

        self.assertTrue(_looks_like_audio_candidate(audio_url))
        self.assertEqual(_rank_media_urls([audio_url, video_url]), [video_url, audio_url])


    def test_only_target_video_urls_are_selected(self):
        target = {"aweme_id": "123", "desc": "目标", "video": {
            "play_addr": {"url_list": ["https://example.com/target.mp4"]},
            "audio": {"url_list": ["https://example.com/target.m4a"]}},
            "music": {"play_url": "https://example.com/background.mp3"}}
        payload = {"item_list": [
            {"aweme_id": "999", "video": {"play_addr": {"url_list": [
                "https://aweme.snssdk.com/aweme/v1/play/?video_id=wrong"]}}}, target],
            "demo": "https://example.com/73a925431aac3cf511e0fb73158c9be8.mp4"}
        self.assertEqual(_douyin_media_candidates([payload], "123"),
                         ["https://example.com/target.mp4", "https://example.com/target.m4a"])
        self.assertEqual(_find_douyin_video(payload, "123"), target)
        self.assertEqual(_douyin_media_candidates([payload], "555"), [])
        self.assertEqual(_douyin_media_candidates([payload], None), [])

    def test_video_without_identity_is_rejected(self):
        payload = {"aweme_detail": {"video": {"play_addr": {
            "url_list": ["https://example.com/unknown.mp4"]}}}}
        self.assertEqual(_douyin_media_candidates([payload], "123"), [])

    def test_share_page_and_api_wrappers_match_numeric_identity(self):
        target = {"aweme_id": 123, "video": {"play_addr": {
            "url_list": ["https://example.com/target.mp4"]}}}
        for payload in [{"aweme_detail": target},
                        {"loaderData": {"page": {"item_list": [target]}}}]:
            self.assertEqual(_douyin_media_candidates([payload], "123"),
                             ["https://example.com/target.mp4"])

    def _browser_fixture(self, payloads):
        runtime = MagicMock()
        page = runtime.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
        page.url = "https://www.douyin.com/video/123"
        page.evaluate.return_value = payloads
        response = MagicMock()
        response.url = "https://example.com/73a925431aac3cf511e0fb73158c9be8.mp4"
        response.headers = {"content-type": "video/mp4"}
        response.request.resource_type = "media"
        page.on.side_effect = lambda event, callback: callback(response)
        settings = SimpleNamespace(playwright_timeout_seconds=1, playwright_user_agent=None,
                                   playwright_headless=True, playwright_chromium_executable_path=None)
        return runtime, settings

    def test_browser_rejects_unverified_player_demo_even_when_it_has_audio(self):
        runtime, settings = self._browser_fixture([])
        downloader = PlaywrightMediaDownloader()
        with patch("playwright.sync_api.sync_playwright", return_value=runtime), \
             patch("app.modules.media_import.downloader.get_settings", return_value=settings), \
             patch("app.modules.media_import.downloader.perf_counter", side_effect=count()), \
             patch.object(downloader, "_download_direct") as download:
            with self.assertRaisesRegex(Exception, "未能验证目标视频"):
                downloader._download_with_playwright("https://v.douyin.com/example/", "test")
            download.assert_not_called()

    def test_browser_downloads_verified_target_instead_of_demo(self):
        payload = {"aweme_detail": {"aweme_id": "123", "desc": "目标视频",
                   "video": {"play_addr": {"url_list": ["https://example.com/target.mp4"]}}}}
        runtime, settings = self._browser_fixture([payload])
        downloader = PlaywrightMediaDownloader()
        with patch("playwright.sync_api.sync_playwright", return_value=runtime), \
             patch("app.modules.media_import.downloader.get_settings", return_value=settings), \
             patch("app.modules.media_import.downloader.perf_counter", side_effect=count()), \
             patch.object(downloader, "_download_direct", return_value="verified") as download:
            self.assertEqual(downloader._download_with_playwright("https://v.douyin.com/example/", "test"), "verified")
            self.assertEqual(download.call_args.args[0], "https://example.com/target.mp4")
            self.assertEqual(download.call_args.args[3], "目标视频")



    def test_resolved_short_link_identity_survives_share_failure(self):
        downloader = PlaywrightMediaDownloader()
        client = MagicMock()
        client.__enter__.return_value.get.return_value.url = "https://www.douyin.com/video/123"
        with patch("app.modules.media_import.downloader.httpx.Client", return_value=client), \
             patch.object(downloader, "_download_from_douyin_share_page", side_effect=ValueError("no data")), \
             patch.object(downloader, "_download_with_playwright", return_value="verified") as browser:
            self.assertEqual(downloader.download("https://v.douyin.com/example/", "test"), "verified")
            browser.assert_called_once_with("https://v.douyin.com/example/", "test", "123")

    def test_browser_cannot_replace_known_target_with_redirected_video(self):
        payload = {"aweme_detail": {"aweme_id": "123", "video": {
            "play_addr": {"url_list": ["https://example.com/wrong.mp4"]}}}}
        runtime, settings = self._browser_fixture([payload])
        downloader = PlaywrightMediaDownloader()
        with patch("playwright.sync_api.sync_playwright", return_value=runtime), \
             patch("app.modules.media_import.downloader.get_settings", return_value=settings), \
             patch("app.modules.media_import.downloader.perf_counter", side_effect=count()), \
             patch.object(downloader, "_download_direct") as download:
            with self.assertRaisesRegex(Exception, "未能验证目标视频"):
                downloader._download_with_playwright("https://v.douyin.com/example/", "test", "999")
            download.assert_not_called()

    def test_share_page_never_downloads_recommendation(self):
        payload = {"item_list": [{"aweme_id": "999", "video": {
            "play_addr": {"url_list": ["https://example.com/wrong.mp4"]}}}]}
        runtime = MagicMock()
        runtime.__enter__.return_value.get.return_value.text = "window._ROUTER_DATA = " + json.dumps(payload)
        downloader = PlaywrightMediaDownloader()
        with patch("app.modules.media_import.downloader.httpx.Client", return_value=runtime), \
             patch.object(downloader, "_download_direct") as download:
            with self.assertRaisesRegex(Exception, "没有可下载的视频"):
                downloader._download_from_douyin_share_page("https://www.douyin.com/video/123", "test", "123")
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
