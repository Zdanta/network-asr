"""Read only the opcpay key and launch the server-side SDK discovery tool."""
import os
from pathlib import Path
import subprocess
import sys

from dotenv import get_key


def main() -> int:
    backend = Path(__file__).resolve().parents[1]
    key = os.environ.get("opcpay_api_key")
    env_file = backend / ".env"
    if not key and env_file.exists():
        # get_key logs a warning for absent keys; avoid logging configuration contents.
        import logging
        logging.getLogger("dotenv.main").disabled = True
        key = get_key(str(env_file), "opcpay_api_key")
    if not key or not key.strip():
        print("未配置服务端 opcpay_api_key，未发出请求。")
        return 1
    child_env = os.environ.copy()
    child_env["opcpay_api_key"] = key
    script = backend.parent / "integrations" / "opcpay" / "probe.mjs"
    try:
        return subprocess.run(["node", str(script)], env=child_env, check=False).returncode
    except OSError:
        print("无法运行 Node.js，请安装 Node.js 18 或以上版本。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
