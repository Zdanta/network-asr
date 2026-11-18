from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ai-video-api"
    app_version: str = "0.1.0"
    app_env: str = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = Field(
        default="mysql+pymysql://root:root@127.0.0.1:3306/ai_video_text?charset=utf8mb4"
    )
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_recycle_seconds: int = 1800
    database_pool_pre_ping: bool = True
    health_check_database: bool = True

    auth_token_secret: str = "change-me-in-production"
    auth_token_expire_seconds: int = Field(default=0, ge=0)
    download_ticket_expire_seconds: int = 60
    admin_mobile_whitelist: str = "17838346022"
    admin_email_whitelist: str = ""
    smtp_host: str = "smtp-mail.outlook.com"
    smtp_port: int = 587
    smtp_security: Literal["auto", "ssl", "starttls"] = "auto"
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_from: str = ""
    smtp_auth_mode: str = "oauth2"
    smtp_oauth_client_id: str = ""
    smtp_oauth_client_secret: SecretStr | None = None
    smtp_oauth_refresh_token: SecretStr | None = None
    smtp_oauth_tenant: str = "consumers"
    smtp_oauth_token_file: str = ".secrets/outlook-refresh.json"

    init_points: int = 100
    guest_enabled: bool = False
    guest_points: int = 100
    guest_ip_points: int = 300
    guest_global_points: int = 10000
    guest_ip_claims: int = 3
    guest_session_days: int = 7
    guest_upload_mb: int = 50
    guest_trusted_proxies: str = "127.0.0.1/32,::1/128"
    seconds_per_point: int = 6

    payment_duplicate_order_window_seconds: int = 120
    opcpay_api_key: SecretStr | None = None
    opcpay_enabled: bool = False
    opcpay_trial_sku_id: str = "S0806000214835352"
    opcpay_callback_url: str = ""
    mock_pay_url_prefix: str = "https://mock-pay.local/qrcode/"
    first_recharge_gift_amount: str = "9.90"
    first_recharge_gift_points: int = 1000
    point_pack_amount: str = "19.90"
    point_pack_points: int = 1000
    point_pack_plus_amount: str = "59.90"
    point_pack_plus_points: int = 3500
    invite_reward_rate_percent: int = 10
    invite_reward_hold_days: int = 7
    min_withdrawal_amount: str = "10.00"

    storage_root: str = "storage"
    upload_subdir: str = "uploads"
    max_upload_size_bytes: int = 500 * 1024 * 1024

    task_worker_max_workers: int = 2
    ffmpeg_command: str = "ffmpeg"
    ffprobe_command: str = "ffprobe"
    audio_subdir: str = "audio"

    asr_provider: str = "volcengine"
    asr_mock_enabled: bool = False
    asr_timeout_seconds: int = 180
    asr_volcengine_mode: str = "flash"
    asr_volcengine_base_url: str = "https://openspeech.bytedance.com"
    asr_volcengine_flash_path: str = "/api/v3/auc/bigmodel/recognize/flash"
    asr_volcengine_api_key: str | None = None
    asr_volcengine_app_id: str | None = None
    asr_volcengine_access_token: str | None = None
    asr_volcengine_cluster: str | None = None
    asr_volcengine_resource_id: str = "volc.bigasr.auc_turbo"
    asr_volcengine_model_name: str = "bigmodel"
    asr_volcengine_uid_prefix: str = "ai-video2text"

    media_import_worker_max_workers: int = 1
    import_subdir: str = "imports"
    playwright_headless: bool = True
    playwright_chromium_executable_path: str | None = None
    playwright_timeout_seconds: int = 30
    playwright_user_agent: str | None = None
    media_download_timeout_seconds: int = 120
    import_download_ttl_seconds: int = 60 * 60
    media_cleanup_interval_seconds: int = 60

    @property
    def admin_mobiles(self) -> set[str]:
        return {item.strip() for item in self.admin_mobile_whitelist.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
