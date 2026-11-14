"""Run the frozen exe without developer PATH, Python or Qt environment settings."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(package):
    package = Path(package).resolve()
    exe = package / "网络ASR.exe"
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "QT_", "QTWEBENGINE"))
    }
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    with tempfile.TemporaryDirectory(prefix="中文 空格 验收 ") as directory:
        report_path = Path(directory) / "diagnostics.json"
        result = subprocess.run(
            [str(exe), "--smoke-test", str(report_path)],
            cwd=directory,
            env=env,
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0 or not report_path.exists():
            raise RuntimeError("便携程序启动失败，请检查构建日志")
        report = json.loads(report_path.read_text(encoding="utf-8"))
    checks = ("html", "bridge", "icon", "navigation", "ffmpeg", "ffprobe", "media", "chromium")
    if (
        report.get("error")
        or report.get("renderer") != "qtwebengine"
        or not all(report.get(k) is True for k in checks)
    ):
        raise RuntimeError(f"便携包检查失败：{report}")
    (package / "diagnostics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    verify(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "网络ASR")
