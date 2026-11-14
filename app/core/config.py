import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.paths import data_root
from app.core.security import crypt


@dataclass
class Config:
    provider: str = "volcengine"
    url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    api_key: str = ""
    resource_id: str = "volc.bigasr.auc_turbo"
    model_name: str = "bigmodel"
    timeout: int = 180
    output_dir: str = str(Path.home() / "Downloads" / "AiVideoDesktop")

    def validate(self):
        from urllib.parse import urlparse

        u = urlparse(self.url)
        if (
            self.provider != "volcengine"
            or u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or u.query
        ):
            raise ValueError("ASR 配置错误：请填写 HTTPS 接口地址（不含凭据或查询参数）")
        if not self.api_key.strip() or not self.resource_id.strip() or not self.model_name.strip():
            raise ValueError("ASR 配置错误：请填写 API Key、资源 ID 和模型")
        if not 1 <= int(self.timeout) <= 3600:
            raise ValueError("超时应在 1 到 3600 秒之间")
        if not Path(self.output_dir).is_absolute():
            raise ValueError("输出目录必须为绝对路径")


def save_config(config, path=None):
    path = Path(path or data_root() / "config.json")
    values = asdict(config)
    values["api_key"] = crypt(values["api_key"]) if values["api_key"] else ""
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def load_config(path=None):
    path = Path(path or data_root() / "config.json")
    if not path.exists():
        return Config()
    values = json.loads(path.read_text(encoding="utf-8"))
    if values.get("api_key"):
        values["api_key"] = crypt(values["api_key"], True)
    return Config(**values)
