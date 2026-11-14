"""Stage a portable release, build a ZIP and record SHA256 checksums."""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import __version__  # noqa: E402


def package():
    draft = "--draft" in sys.argv
    if not draft and "REPOSITORY_URL" in (ROOT / "README.md").read_text(encoding="utf-8"):
        raise RuntimeError(
            "先运行 scripts/set_repository.py 填入真实仓库地址；本地预览可使用 --draft"
        )
    build = ROOT / "dist" / "网络ASR"
    if not (build / "网络ASR.exe").is_file():
        raise RuntimeError("请先完成 PyInstaller 构建")
    report = json.loads((build / "diagnostics.json").read_text(encoding="utf-8"))
    required = ("html", "bridge", "icon", "navigation", "ffmpeg", "ffprobe", "media", "chromium")
    if (
        report.get("error")
        or report.get("renderer") != "qtwebengine"
        or not all(report.get(k) is True for k in required)
    ):
        raise RuntimeError("便携包运行时检查未通过，拒绝生成 Release")
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, build / name)
    destination = ROOT / "release"
    destination.mkdir(exist_ok=True)
    output = destination / f"NetworkASR-v{__version__}-windows-x64{'-draft' if draft else ''}.zip"
    with zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True
    ) as archive:
        for path in sorted(build.rglob("*")):
            if path.is_file():
                archive.write(path, Path("NetworkASR") / path.relative_to(build))
    with output.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    (destination / "SHA256SUMS.txt").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    shutil.copy2(ROOT / "docs" / "RELEASE_NOTES.md", destination / "RELEASE_NOTES.md")
    print(output)
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    package()
