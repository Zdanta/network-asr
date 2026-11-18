import json
import logging
import math
import mimetypes
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

import httpx

from app.common.media import has_audio_stream, merge_video_audio
from app.core.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
AUDIO_EXTENSIONS = MEDIA_EXTENSIONS - VIDEO_EXTENSIONS
MEDIA_CONTENT_PREFIXES = ("video/", "audio/")
DOUYIN_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class DownloadedMedia:
    source_url: str
    relative_path: str
    source_file_name: str
    storage_file_name: str
    file_type: str
    content_type: str | None
    file_size: int
    duration_seconds: int | None
    title: str | None
    cookie_source: str | None
    download_engine: str


class PlaywrightMediaDownloader:
    def __init__(self, max_bytes=None):
        self.max_bytes = max_bytes

    def download(self, source_url: str, job_id: str) -> DownloadedMedia:
        if _looks_like_direct_media(source_url):
            return self._download_direct(source_url, job_id, "direct-http", None)
        item_id = _extract_douyin_item_id(source_url)
        if _is_douyin_url(source_url):
            try:
                if not item_id:
                    settings = get_settings()
                    with httpx.Client(headers={"user-agent": DOUYIN_MOBILE_USER_AGENT},
                                      follow_redirects=True,
                                      timeout=float(settings.media_download_timeout_seconds)) as client:
                        resolved = client.get(source_url)
                        resolved.raise_for_status()
                        item_id = _extract_douyin_item_id(str(resolved.url))
                return self._download_from_douyin_share_page(source_url, job_id, item_id)
            except Exception as exc:
                logger.warning("douyin share page download failed, jobId=%s, error=%s", job_id, exc)
        return self._download_with_playwright(source_url, job_id, item_id)

    def _download_from_douyin_share_page(self, source_url: str, job_id: str, item_id: str | None = None) -> DownloadedMedia:
        settings = get_settings()
        timeout = httpx.Timeout(float(settings.media_download_timeout_seconds))
        headers = {"user-agent": DOUYIN_MOBILE_USER_AGENT}
        with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
            if not item_id:
                resolved = client.get(source_url)
                resolved.raise_for_status()
                item_id = _extract_douyin_item_id(source_url) or _extract_douyin_item_id(str(resolved.url))
            if not item_id:
                raise AppException(code=4004, message="没有从抖音链接中识别到视频编号", status_code=404)

            share_url = f"https://www.iesdouyin.com/share/video/{item_id}/"
            share_response = client.get(share_url)
            share_response.raise_for_status()
            payload = _decode_router_data(share_response.text)

        target = _find_douyin_video(payload, item_id)
        title = _payload_title([target]) if target else None
        candidates = _douyin_media_candidates([payload], item_id)
        if not candidates:
            raise AppException(code=4004, message="抖音分享页中没有可下载的视频", status_code=404)

        download_headers = {"referer": share_url, "user-agent": DOUYIN_MOBILE_USER_AGENT}
        last_error: Exception | None = None
        for candidate in [url for url in candidates if not _looks_like_audio_candidate(url)][:16]:
            try:
                media = self._download_direct(
                    candidate,
                    job_id,
                    "douyin-share",
                    title,
                    headers=download_headers,
                    audio_candidates=candidates,
                )
                logger.info(
                    "douyin share page download finished, jobId=%s, itemId=%s, mediaUrl=%s",
                    job_id,
                    item_id,
                    candidate,
                )
                return media
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "douyin share candidate failed, jobId=%s, itemId=%s, mediaUrl=%s, error=%s",
                    job_id,
                    item_id,
                    candidate,
                    exc,
                )
        raise AppException(code=5000, message="抖音视频下载失败，请稍后重试", status_code=500) from last_error

    def _download_with_playwright(self, source_url: str, job_id: str, item_id: str | None = None) -> DownloadedMedia:
        started_at = perf_counter()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AppException(code=5000, message="链接下载组件未安装，请联系管理员", status_code=500) from exc

        settings = get_settings()
        timeout_ms = max(5, settings.playwright_timeout_seconds) * 1000
        is_douyin = _is_douyin_url(source_url)
        item_id = item_id or _extract_douyin_item_id(source_url)
        captured_urls: list[str] = []
        detail_payloads: list[dict[str, Any]] = []
        title: str | None = None
        user_agent = settings.playwright_user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )

        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, object] = {"headless": settings.playwright_headless}
                if settings.playwright_chromium_executable_path:
                    launch_options["executable_path"] = settings.playwright_chromium_executable_path
                launch_options["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(
                    user_agent=user_agent,
                    viewport={"width": 1365, "height": 900},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                page.set_default_navigation_timeout(timeout_ms)

                def collect_response(response) -> None:
                    try:
                        response_url = response.url
                        content_type = response.headers.get("content-type", "")
                        if _is_detail_api_url(response_url):
                            try:
                                payload = response.json()
                                if isinstance(payload, dict):
                                    detail_payloads.append(payload)
                                    if not is_douyin:
                                        captured_urls.extend(_extract_media_urls_from_payload(payload))
                            except Exception as exc:
                                logger.debug("douyin detail response parse failed, url=%s, error=%s", response_url, exc)
                            return
                        if not is_douyin and (
                            response.request.resource_type == "media"
                            or _is_media_content_type(content_type)
                            or _is_media_candidate_url(response_url)
                        ):
                            captured_urls.append(response_url)
                    except Exception as exc:
                        logger.debug("playwright response capture ignored, error=%s", exc)

                page.on("response", collect_response)
                page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
                first_media_at: float | None = None
                deadline = perf_counter() + max(8, settings.playwright_timeout_seconds)
                while perf_counter() < deadline:
                    if is_douyin:
                        item_id = item_id or _extract_douyin_item_id(page.url)
                        detail_payloads.extend(page.evaluate(_DOUYIN_PAYLOAD_DISCOVERY_SCRIPT))
                        candidates = _douyin_media_candidates(detail_payloads, item_id)
                    else:
                        discovered = page.evaluate(_MEDIA_DISCOVERY_SCRIPT)
                        captured_urls.extend(url for url in discovered if _is_media_candidate_url(url))
                        candidates = _rank_media_urls(captured_urls)
                    try:
                        page.eval_on_selector_all(
                            "video",
                            "nodes => nodes.forEach(node => { node.muted = true; node.play().catch(() => {}); })",
                        )
                    except Exception:
                        pass

                    if candidates:
                        first_media_at = first_media_at or perf_counter()
                        if perf_counter() - first_media_at >= 10:
                            break
                    page.wait_for_timeout(2000)

                if is_douyin:
                    targets = [target for payload in detail_payloads
                               if (target := _find_douyin_video(payload, item_id)) is not None]
                    title = _payload_title(targets)
                else:
                    title = _safe_title(page.title()) or _payload_title(detail_payloads)
                cookies = context.cookies()
                cookie_header = _cookie_header(cookies)
                logger.info(
                    "playwright discovery finished, jobId=%s, pageUrl=%s, targetItemId=%s, capturedCount=%s, detailPayloadCount=%s",
                    job_id,
                    page.url,
                    item_id,
                    len(candidates),
                    len(detail_payloads),
                )
                browser.close()
        except Exception as exc:
            raise AppException(code=5000, message="没有成功解析到视频内容，请确认链接可访问", status_code=500) from exc

        candidates = (_douyin_media_candidates(detail_payloads, item_id)
                      if is_douyin else _rank_media_urls(captured_urls))
        if not candidates:
            raise AppException(code=4004, message="未能验证目标视频，请重试或上传原视频" if is_douyin else "没有找到可下载的视频内容", status_code=404)

        headers = {"referer": source_url, "user-agent": user_agent}
        if cookie_header:
            headers["cookie"] = cookie_header

        last_error: Exception | None = None
        video_candidates = [url for url in candidates if not _looks_like_audio_candidate(url)] if is_douyin else candidates
        for candidate in video_candidates[:16]:
            try:
                media = self._download_direct(
                    candidate,
                    job_id,
                    "playwright",
                    title,
                    headers=headers,
                    audio_candidates=candidates,
                )
                logger.info(
                    "playwright media download finished, jobId=%s, elapsedMs=%.2f, mediaUrl=%s",
                    job_id,
                    (perf_counter() - started_at) * 1000,
                    candidate,
                )
                return media
            except Exception as exc:
                last_error = exc
                logger.warning("candidate media download failed, jobId=%s, mediaUrl=%s, error=%s", job_id, candidate, exc)

        raise AppException(code=5000, message="视频下载失败，请稍后重试或更换链接", status_code=500)

    def _download_direct(
        self,
        media_url: str,
        job_id: str,
        engine: str,
        title: str | None,
        headers: dict[str, str] | None = None,
        audio_candidates: list[str] | None = None,
    ) -> DownloadedMedia:
        settings = get_settings()
        timeout = httpx.Timeout(float(settings.media_download_timeout_seconds))
        with httpx.stream("GET", media_url, headers=headers, follow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            suffix = _guess_suffix(media_url, content_type)
            file_type = _resolve_file_type(suffix, content_type)
            storage_file_name = f"{job_id}{suffix}"
            relative_path = Path(settings.import_subdir) / datetime.now().strftime("%Y%m%d") / storage_file_name
            absolute_path = Path(settings.storage_root) / relative_path
            absolute_path.parent.mkdir(parents=True, exist_ok=True)

            file_size = 0
            max_size = min(settings.max_upload_size_bytes, self.max_bytes) if self.max_bytes else settings.max_upload_size_bytes
            with absolute_path.open("wb") as target:
                for chunk in response.iter_bytes(1024 * 1024):
                    if not chunk:
                        continue
                    file_size += len(chunk)
                    if file_size > max_size:
                        target.close()
                        absolute_path.unlink(missing_ok=True)
                        raise AppException(code=1001, message="下载的视频过大，暂时无法处理")
                    target.write(chunk)

        if file_type == "VIDEO" and not has_audio_stream(absolute_path):
            merged = self._merge_companion_audio(
                absolute_path,
                media_url,
                audio_candidates or [],
                headers,
            )
            if not merged:
                absolute_path.unlink(missing_ok=True)
                raise AppException(code=1001, message="下载的视频没有可用音轨，也没有找到可合并的音频")
            file_size = absolute_path.stat().st_size
            content_type = "video/mp4"

        return DownloadedMedia(
            source_url=media_url,
            relative_path=relative_path.as_posix(),
            source_file_name=_source_file_name(media_url, suffix, title),
            storage_file_name=storage_file_name,
            file_type=file_type,
            content_type=content_type,
            file_size=file_size,
            duration_seconds=_probe_duration_seconds(absolute_path),
            title=title,
            cookie_source="browser" if headers and headers.get("cookie") else None,
            download_engine=engine,
        )

    def _merge_companion_audio(
        self,
        video_path: Path,
        video_url: str,
        candidates: list[str],
        headers: dict[str, str] | None,
    ) -> bool:
        audio_urls = [
            url
            for url in candidates
            if url != video_url and _looks_like_audio_candidate(url)
        ]
        if not audio_urls:
            return False

        settings = get_settings()
        timeout = httpx.Timeout(float(settings.media_download_timeout_seconds))
        for index, audio_url in enumerate(audio_urls[:8]):
            audio_path = video_path.with_name(f"{video_path.stem}.audio-{index}{_guess_suffix(audio_url, None)}")
            merged_path = video_path.with_name(f"{video_path.stem}.merged.mp4")
            try:
                file_size = 0
                with httpx.stream(
                    "GET",
                    audio_url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    with audio_path.open("wb") as target:
                        for chunk in response.iter_bytes(1024 * 1024):
                            if not chunk:
                                continue
                            file_size += len(chunk)
                            if file_size > (min(settings.max_upload_size_bytes, self.max_bytes) if self.max_bytes else settings.max_upload_size_bytes):
                                raise AppException(code=1001, message="配套音频文件过大，暂时无法处理")
                            target.write(chunk)

                if not has_audio_stream(audio_path):
                    continue

                merge_video_audio(video_path, audio_path, merged_path)
                merged_path.replace(video_path)
                logger.info("video and audio merged, video=%s, audioUrl=%s", video_path, audio_url)
                return True
            except Exception as exc:
                logger.warning("companion audio merge failed, audioUrl=%s, error=%s", audio_url, exc)
            finally:
                audio_path.unlink(missing_ok=True)
                merged_path.unlink(missing_ok=True)
        return False


# Douyin pages also load recommendations and player demo clips. Only structured
# video data carrying the requested aweme ID can authorize a download.
_DOUYIN_PAYLOAD_DISCOVERY_SCRIPT = """
() => {
  const payloads = [];
  if (window._ROUTER_DATA && typeof window._ROUTER_DATA === 'object') {
    payloads.push(window._ROUTER_DATA);
  }
  document.querySelectorAll('script#RENDER_DATA, script[type="application/json"]').forEach(node => {
    const value = node.textContent || '';
    try { payloads.push(JSON.parse(value)); }
    catch (_) { try { payloads.push(JSON.parse(decodeURIComponent(value))); } catch (_) {} }
  });
  return payloads;
}
"""


def _find_douyin_video(payload: Any, item_id: str | None) -> dict[str, Any] | None:
    if not item_id:
        return None
    if isinstance(payload, dict):
        identity = payload.get("aweme_id") or payload.get("awemeId") or payload.get("item_id")
        if identity is not None:
            # Never descend into recommendations nested in a different video.
            if str(identity) != item_id:
                return None
            if isinstance(payload.get("video"), dict):
                return payload
        for value in payload.values():
            target = _find_douyin_video(value, item_id)
            if target is not None:
                return target
    elif isinstance(payload, list):
        for value in payload:
            target = _find_douyin_video(value, item_id)
            if target is not None:
                return target
    return None


def _douyin_media_candidates(payloads: list[dict[str, Any]], item_id: str | None) -> list[str]:
    urls: list[str] = []
    for payload in payloads:
        target = _find_douyin_video(payload, item_id)
        if target is not None:
            # Music/author/recommendation URLs outside video are not its audio track.
            urls.extend(_extract_media_urls_from_payload(target["video"]))
    return _rank_media_urls(urls)


_MEDIA_DISCOVERY_SCRIPT = """
() => {
  const values = [];
  const add = (value) => {
    if (typeof value === 'string' && value.trim()) values.push(value.trim());
  };
  document.querySelectorAll('video, audio').forEach((node) => {
    add(node.currentSrc);
    add(node.src);
    node.querySelectorAll('source').forEach((source) => add(source.src));
  });
  performance.getEntriesByType('resource')
    .map((entry) => entry.name)
    .filter((name) => /douyinvod|bytevod|mime_type=(video|audio)|mime=(video|audio)|video_mp4|\\.mp4|\\.m4a|\\/aweme\\/v1\\/(play|music)\\//i.test(name))
    .forEach(add);
  return Array.from(new Set(values));
}
"""


def _looks_like_direct_media(url: str) -> bool:
    path = urlparse(url).path.lower()
    return Path(path).suffix in MEDIA_EXTENSIONS


def _is_media_content_type(content_type: str | None) -> bool:
    return bool(content_type and content_type.lower().startswith(MEDIA_CONTENT_PREFIXES))


def _is_detail_api_url(url: str) -> bool:
    return "aweme/v1/web/aweme/detail" in url.lower()


def _is_douyin_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "douyin.com" or hostname.endswith(".douyin.com") or hostname == "iesdouyin.com" or hostname.endswith(
        ".iesdouyin.com"
    )


def _extract_douyin_item_id(url: str) -> str | None:
    match = re.search(r"/(?:video|share/video)/(\d+)", urlparse(url).path)
    return match.group(1) if match else None


def _decode_router_data(html: str) -> dict[str, Any]:
    marker = "window._ROUTER_DATA = "
    marker_index = html.find(marker)
    if marker_index < 0:
        raise AppException(code=4004, message="抖音分享页缺少视频数据", status_code=404)
    payload, _ = json.JSONDecoder().raw_decode(html[marker_index + len(marker) :])
    if not isinstance(payload, dict):
        raise AppException(code=4004, message="抖音分享页视频数据格式异常", status_code=404)
    return payload


def _is_media_candidate_url(url: str) -> bool:
    normalized = url.lower()
    if not normalized.startswith(("http://", "https://")) or _is_detail_api_url(normalized):
        return False
    return _looks_like_direct_media(normalized) or any(
        token in normalized
        for token in (
            "douyinvod.com",
            "bytevod.com",
            "mime_type=video",
            "mime_type=audio",
            "mime=video",
            "mime=audio",
            "video_mp4",
            "/aweme/v1/play/",
            "/aweme/v1/playwm/",
            "/aweme/v1/music/",
        )
    )


def _extract_media_urls_from_payload(payload: Any) -> list[str]:
    media_urls: list[str] = []

    def walk(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, str):
            path_text = ".".join(path).lower()
            if value.startswith(("http://", "https://")) and (
                _is_media_candidate_url(value)
                or any(token in path_text for token in ("play_addr", "download_addr", "play_url", "bit_rate", "audio"))
            ):
                no_watermark_url = _to_no_watermark_url(value)
                if no_watermark_url != value:
                    media_urls.append(no_watermark_url)
                media_urls.append(value)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, (*path, str(key)))
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, (*path, str(index)))

    walk(payload, ())
    return list(dict.fromkeys(media_urls))


def _payload_title(payloads: list[dict[str, Any]]) -> str | None:
    for payload in payloads:
        detail = payload.get("aweme_detail")
        if isinstance(detail, dict):
            for key in ("desc", "preview_title"):
                title = _safe_title(detail.get(key))
                if title:
                    return title

        stack: list[Any] = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if isinstance(value.get("video"), dict):
                    title = _safe_title(value.get("desc") or value.get("preview_title"))
                    if title:
                        return title
                stack.extend(reversed(list(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))
    return None


def _rank_media_urls(urls: list[str]) -> list[str]:
    unique = []
    seen = set()
    for url in urls:
        if not url or url in seen or not _is_media_candidate_url(url):
            continue
        seen.add(url)
        unique.append(url)

    def score(url: str) -> int:
        lower = url.lower()
        value = 0
        if _looks_like_direct_media(lower):
            value += 50
        if _looks_like_audio_candidate(lower):
            value -= 60
        if "douyinvod.com" in lower or "bytevod.com" in lower or "/aweme/v1/play/" in lower:
            value += 40
        if "/aweme/v1/play/" in lower:
            value += 100
        if "/aweme/v1/playwm/" in lower or "watermark=1" in lower:
            value -= 150
        if "video" in lower or "playwm" in lower or "douyin" in lower:
            value += 15
        if "mime_type=video" in lower:
            value += 60
        if ".m3u8" in lower:
            value -= 30
        if "avatar" in lower or "image" in lower or ".jpg" in lower or ".png" in lower:
            value -= 50
        return value

    return sorted(unique, key=score, reverse=True)


def _to_no_watermark_url(url: str) -> str:
    parsed = urlparse(url)
    if "/aweme/v1/playwm/" not in parsed.path:
        return url
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "watermark"
    ]
    return urlunparse(
        parsed._replace(
            path=parsed.path.replace("/aweme/v1/playwm/", "/aweme/v1/play/"),
            query=urlencode(query),
        )
    )


def _looks_like_audio_candidate(url: str) -> bool:
    lower = url.lower()
    suffix = Path(unquote(urlparse(lower).path)).suffix
    return suffix in AUDIO_EXTENSIONS or any(
        token in lower
        for token in (
            "mime_type=audio",
            "mime=audio",
            "/audio/",
            "/music/",
            "audio_id=",
        )
    )


def _guess_suffix(url: str, content_type: str | None) -> str:
    path_suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if path_suffix in MEDIA_EXTENSIONS:
        return path_suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guessed in MEDIA_EXTENSIONS:
        return guessed
    if content_type and content_type.startswith("audio/"):
        return ".mp3"
    return ".mp4"


def _resolve_file_type(suffix: str, content_type: str | None) -> str:
    if suffix in VIDEO_EXTENSIONS or (content_type or "").startswith("video/"):
        return "VIDEO"
    if suffix in AUDIO_EXTENSIONS or (content_type or "").startswith("audio/"):
        return "AUDIO"
    raise AppException(code=1001, message="暂不支持该媒体格式")


def _source_file_name(url: str, suffix: str, title: str | None) -> str:
    if title:
        return f"{_safe_title(title)}{suffix}"
    parsed_name = Path(unquote(urlparse(url).path)).name
    if parsed_name:
        return parsed_name[:255]
    return f"imported-media{suffix}"


def _safe_title(value: str | None) -> str | None:
    if not value:
        return None
    safe = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", value).strip(" ._")
    return (safe or "imported-media")[:200]


def _cookie_header(cookies: list[dict]) -> str | None:
    pairs = [f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies if cookie.get("name")]
    return "; ".join(pairs) if pairs else None


def _probe_duration_seconds(path: Path) -> int | None:
    ffprobe = shutil.which(get_settings().ffprobe_command)
    if ffprobe is None:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    if duration <= 0:
        return None
    return max(1, int(math.ceil(duration)))
