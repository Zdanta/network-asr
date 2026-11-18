import base64
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AsrResult:
    text: str
    language: str | None = None


def transcribe_audio(audio_path: Path, source_file_name: str | None = None) -> AsrResult:
    settings = get_settings()
    provider = (settings.asr_provider or "").lower()
    if settings.asr_mock_enabled or provider == "mock":
        return AsrResult(text=f"[模拟转写] {source_file_name or audio_path.name} 已完成文字提取。", language="zh-CN")

    if provider in {"volcengine", "real"}:
        return _transcribe_with_volcengine_flash(audio_path)

    raise AppException(code=5000, message="语音识别服务配置不支持，请联系管理员", status_code=500)


def _transcribe_with_volcengine_flash(audio_path: Path) -> AsrResult:
    settings = get_settings()
    mode = (settings.asr_volcengine_mode or "").lower()
    api_key = _clean_optional(settings.asr_volcengine_api_key)
    app_id = _clean_optional(settings.asr_volcengine_app_id)
    access_token = _clean_optional(settings.asr_volcengine_access_token)
    cluster = _clean_optional(settings.asr_volcengine_cluster)

    if mode != "flash":
        raise AppException(code=5000, message="语音识别模式配置不正确，请联系管理员", status_code=500)
    if not api_key and not (app_id and access_token and cluster):
        raise AppException(code=5000, message="语音识别服务尚未配置，请联系管理员", status_code=500)
    if not audio_path.exists():
        raise AppException(code=4004, message="音频文件不存在，请重新处理", status_code=404)

    request_id = str(uuid.uuid4())
    payload = {
        "user": {"uid": f"{settings.asr_volcengine_uid_prefix}-{uuid.uuid4()}"},
        "request": {"model_name": settings.asr_volcengine_model_name},
        "audio": {
            "format": _resolve_audio_format(audio_path),
            "codec": "raw",
            "data": base64.b64encode(audio_path.read_bytes()).decode("utf-8"),
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Resource-Id": settings.asr_volcengine_resource_id,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": "-1",
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    else:
        headers["X-Api-App-Key"] = app_id or ""
        headers["X-Api-Access-Key"] = access_token or ""

    url = f"{settings.asr_volcengine_base_url.rstrip('/')}{settings.asr_volcengine_flash_path}"
    started_at = perf_counter()
    try:
        with httpx.Client(timeout=float(settings.asr_timeout_seconds)) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AppException(code=5000, message="语音识别服务请求失败，请稍后重试", status_code=500) from exc

    status_code = response.headers.get("X-Api-Status-Code")
    message = response.headers.get("X-Api-Message")
    log_id = response.headers.get("X-Tt-Logid")
    logger.info(
        "volcengine ASR response received, requestId=%s, statusCode=%s, logId=%s, elapsedMs=%.2f",
        request_id,
        status_code,
        log_id,
        (perf_counter() - started_at) * 1000,
    )
    if status_code and status_code != "20000000":
        raise AppException(code=5000, message=_translate_asr_error(message, status_code), status_code=500)

    try:
        result_json = response.json()
    except ValueError as exc:
        raise AppException(code=5000, message="语音识别服务返回异常，请稍后重试", status_code=500) from exc

    result = result_json.get("result") or {}
    raw_text = (result.get("text") or "").strip()
    if not raw_text:
        raise AppException(code=5000, message="没有识别到可用文字，请确认素材中有清晰声音", status_code=500)

    return AsrResult(text=raw_text, language=result.get("language") or "zh-CN")


def _resolve_audio_format(audio_path: Path) -> str:
    suffix = audio_path.suffix.lower().strip(".")
    return suffix or "wav"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _translate_asr_error(message: str | None, status_code: str | None) -> str:
    if message:
        lower = message.lower()
        if "audio" in lower or "format" in lower:
            return "音频格式暂不支持，请换一个文件再试"
        if "auth" in lower or "key" in lower or "token" in lower:
            return "语音识别服务鉴权失败，请联系管理员"
        if "timeout" in lower:
            return "语音识别超时，请稍后重试"
    return f"语音识别失败，请稍后重试（{status_code or '未知错误'}）"
