"""Fill the actual repository URL before the first public release."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def set_repository(url):
    url = url.removesuffix(".git").rstrip("/")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url):
        raise ValueError("请提供真实的 https://github.com/owner/repository 地址")
    readme = ROOT / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("REPOSITORY_URL", url), encoding="utf-8"
    )
    print(url)


if __name__ == "__main__":
    set_repository(sys.argv[1])
