"""Media runtime defaults; independent of user ASR credentials."""

from types import SimpleNamespace

from app.core.paths import browser_executable, data_root, tool


def get_settings():
    return SimpleNamespace(
        media_download_timeout_seconds=120,
        playwright_timeout_seconds=30,
        playwright_user_agent=None,
        playwright_headless=True,
        playwright_chromium_executable_path=browser_executable(),
        storage_root=str(data_root() / "cache"),
        import_subdir="downloads",
        max_upload_size_bytes=1024**3,
        ffprobe_command=tool("ffprobe"),
        ffmpeg_command=tool("ffmpeg"),
    )
