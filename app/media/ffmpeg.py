import math
import shutil
import subprocess
from pathlib import Path

from app.media.settings import get_settings


def probe_duration_seconds(path: Path) -> int | None:
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
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
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


def has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which(get_settings().ffprobe_command)
    if ffprobe is None:
        return False

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    return result.returncode == 0 and "audio" in result.stdout.lower()


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    ffmpeg = shutil.which(get_settings().ffmpeg_command)
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not available")

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1000:] or "ffmpeg merge failed")


def extract_audio(source, target):
    if not has_audio_stream(source):
        raise RuntimeError("视频或音频没有可用音轨")
    result = subprocess.run(
        [
            get_settings().ffmpeg_command,
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(target),
        ],
        capture_output=True,
        timeout=600,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("FFmpeg 提取音频失败，请检查素材")
