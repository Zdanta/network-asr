import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
metadata = json.loads((root / "release.json").read_text(encoding="utf-8"))
output = root.parent / "release-web"
output.mkdir(exist_ok=True)
archive = output / ("NetworkASR-" + metadata["tag"] + "-deploy.zip")
skip = {".git", ".venv", "node_modules", "__pycache__", "storage", ".secrets", "output", ".pytest_cache"}
with ZipFile(archive, "w", ZIP_DEFLATED) as package:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in skip for part in relative.parts):
            continue
        if path.name in {".env", ".env.local"} or path.suffix in {".log", ".pyc", ".db"}:
            continue
        package.write(path, "network-asr-web/" + relative.as_posix())
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / "SHA256SUMS.txt").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
print(archive.name, checksum)
