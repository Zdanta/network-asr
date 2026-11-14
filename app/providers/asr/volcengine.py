import base64
import uuid

import httpx


class VolcengineFlash:
    def __init__(self, config, transport=None):
        self.config, self.transport = config, transport

    def transcribe(self, path):
        c = self.config
        c.validate()
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("音频超过火山 Flash 的 100MB 限制，请将素材分段后重试")
        headers = {
            "X-Api-Key": c.api_key,
            "X-Api-Resource-Id": c.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }
        payload = {
            "user": {"uid": "desktop-" + str(uuid.uuid4())},
            "request": {"model_name": c.model_name},
            "audio": {
                "format": path.suffix.lstrip("."),
                "codec": "raw",
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            },
        }
        try:
            with httpx.Client(timeout=c.timeout, transport=self.transport) as client:
                r = client.post(c.url, headers=headers, json=payload)
        except httpx.TimeoutException:
            raise RuntimeError("ASR 请求超时，请稍后重试") from None
        except httpx.HTTPError:
            raise RuntimeError("ASR 网络请求失败，请检查连接") from None
        return parse_response(r)


def parse_response(r):
    if r.status_code in (401, 403):
        raise RuntimeError("ASR 密钥错误或无资源权限，请检查设置")
    if r.status_code >= 400:
        raise RuntimeError(f"ASR 服务商返回 HTTP 错误（{r.status_code}）")
    code = r.headers.get("X-Api-Status-Code")
    if code and code != "20000000":
        # Do not echo provider messages; they can contain credentials.
        raise RuntimeError("ASR 服务商返回错误，请核对密钥、资源 ID、额度及音频格式")
    try:
        text = r.json()["result"]["text"].strip()
        if not isinstance(text, str) or not text:
            raise ValueError()
        return text
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError("ASR 返回异常或没有识别到可用文字") from None
