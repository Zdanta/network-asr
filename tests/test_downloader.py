import unittest

from app.media.downloader import (
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


if __name__ == "__main__":
    unittest.main()
