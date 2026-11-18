import base64
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.modules.auth.oauth_tokens import load_refresh_token, save_refresh_token


def send_verification_email(email: str, code: str) -> None:
    cfg = get_settings()
    if not cfg.smtp_username or not cfg.smtp_from:
        raise AppException(code=1010, message="邮箱发送服务尚未配置，请联系管理员", status_code=503)
    try:
        if cfg.smtp_auth_mode == "oauth2":
            refresh = load_refresh_token(cfg.smtp_oauth_token_file, cfg.smtp_oauth_refresh_token)
            if not cfg.smtp_oauth_client_id or not refresh:
                raise ValueError("missing oauth configuration")
            if cfg.smtp_oauth_tenant not in {"consumers", "common", "organizations"}:
                raise ValueError("invalid tenant")
            form = {"client_id": cfg.smtp_oauth_client_id, "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "scope": "https://outlook.office.com/SMTP.Send offline_access"}
            if cfg.smtp_oauth_client_secret:
                form["client_secret"] = cfg.smtp_oauth_client_secret.get_secret_value()
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.post(f"https://login.microsoftonline.com/{cfg.smtp_oauth_tenant}/oauth2/v2.0/token", data=form)
                response.raise_for_status()
                tokens = response.json()
                token = tokens["access_token"]
                if tokens.get("refresh_token"):
                    save_refresh_token(cfg.smtp_oauth_token_file, tokens["refresh_token"])
        elif cfg.smtp_auth_mode != "password" or not cfg.smtp_password:
            raise ValueError("invalid smtp authentication")
        message = EmailMessage()
        message["Subject"] = "网络ASR 邮箱验证码"
        message["From"] = cfg.smtp_from
        message["To"] = email
        message.set_content(f"你的网络ASR验证码是：{code}\n\n10分钟内有效，请勿向他人透露。若非本人操作，请忽略本邮件。")
        implicit_tls = cfg.smtp_security == "ssl" or (cfg.smtp_security == "auto" and cfg.smtp_port == 465)
        connection = (smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15, context=ssl.create_default_context())
                      if implicit_tls else smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15))
        with connection as smtp:
            smtp.ehlo()
            if not implicit_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if cfg.smtp_auth_mode == "oauth2":
                credential = base64.b64encode(f"user={cfg.smtp_username}\x01auth=Bearer {token}\x01\x01".encode()).decode()
                status, _ = smtp.docmd("AUTH", "XOAUTH2 " + credential)
                if status != 235:
                    raise ValueError("smtp oauth rejected")
            else:
                smtp.login(cfg.smtp_username, cfg.smtp_password.get_secret_value())
            smtp.send_message(message)
    except Exception:
        raise AppException(code=1010, message="验证码邮件暂时无法发送，请稍后重试", status_code=503) from None
