import json
import os
import tempfile
from pathlib import Path


def save_refresh_token(path: str, token: str):
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".oauth-", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump({"refresh_token": token}, file)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_refresh_token(path: str, fallback):
    target = Path(path)
    if target.exists():
        token = json.loads(target.read_text(encoding="utf-8"))["refresh_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("invalid refresh token file")
        return token
    return fallback.get_secret_value() if fallback else None
