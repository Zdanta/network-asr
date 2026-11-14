"""Collect redistributable notices and exact build information into the release."""

import importlib.metadata as metadata
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def prepare(destination):
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    for package in (
        "pywebview",
        "httpx",
        "httpcore",
        "certifi",
        "anyio",
        "playwright",
        "pyee",
        "greenlet",
        "PySide6",
        "PySide6-Addons",
        "PySide6-Essentials",
        "shiboken6",
        "QtPy",
        "bottle",
        "proxy_tools",
        "packaging",
        "idna",
        "h11",
        "typing_extensions",
    ):
        dist = metadata.distribution(package)
        folder = target / package
        folder.mkdir(exist_ok=True)
        (folder / "VERSION.txt").write_text(dist.version, encoding="utf-8")
        for item in dist.files or []:
            if (
                any(
                    part.upper().startswith(("LICENSE", "COPYING", "NOTICE")) for part in item.parts
                )
                and dist.locate_file(item).is_file()
            ):
                source = dist.locate_file(item)
                dest = folder / str(item).replace("/", "_").replace("\\", "_")
                shutil.copy2(source, dest)
    for name, url in {
        "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
        "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
        "LGPL-2.1.txt": "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt",
        "Chromium-LICENSE.txt": "https://raw.githubusercontent.com/chromium/chromium/main/LICENSE",
    }.items():
        path = target / name
        if not path.exists():
            response = httpx.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, target / "Python-LICENSE.txt")
    ffmpeg = ROOT / "resources" / "bin" / "ffmpeg.exe"
    result = subprocess.run(
        [str(ffmpeg), "-version"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    (target / "FFmpeg-build.txt").write_bytes(result.stdout + result.stderr)
    source_folder = target / "sources"
    source_folder.mkdir(exist_ok=True)
    match = re.search(rb"ffmpeg version ([0-9]+\.[0-9]+(?:\.[0-9]+)?)", result.stdout)
    if not match:
        raise RuntimeError("Cannot identify FFmpeg source version")
    version = match.group(1).decode("ascii")
    source = source_folder / f"ffmpeg-{version}.tar.xz"
    if not source.exists():
        response = httpx.get(f"https://ffmpeg.org/releases/ffmpeg-{version}.tar.xz", timeout=120)
        response.raise_for_status()
        source.write_bytes(response.content)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", target.parent / "THIRD_PARTY_NOTICES.md")


if __name__ == "__main__":
    prepare(sys.argv[1])
