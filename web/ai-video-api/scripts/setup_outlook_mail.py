"""One-time user-authorized OAuth setup. No email is sent and no password is requested."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from dotenv import set_key
from app.modules.auth.oauth_tokens import save_refresh_token


def main():
    parser = argparse.ArgumentParser(description="为网络ASR授权个人Outlook发件邮箱（不发送邮件）")
    parser.add_argument("--client-id", required=True, help="你注册的 Microsoft Entra 公共客户端应用 ID")
    parser.add_argument("--sender", required=True, help="授权的个人 Outlook 发件地址")
    args = parser.parse_args()
    from app.modules.auth.schemas import EmailRequest
    sender = EmailRequest(email=args.sender).email
    base = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(base + "/devicecode", data={"client_id": args.client_id,
                "scope": "https://outlook.office.com/SMTP.Send offline_access"})
            response.raise_for_status()
            challenge = response.json()
            print("请在浏览器打开：", challenge["verification_uri"], flush=True)
            print("授权代码：", challenge["user_code"], flush=True)
            print("请确认应用是你刚注册的应用，只授权你自己的发件邮箱。等待授权…", flush=True)
            deadline = time.monotonic() + int(challenge["expires_in"])
            interval = max(5, int(challenge.get("interval", 5)))
            while time.monotonic() < deadline:
                time.sleep(interval)
                response = client.post(base + "/token", data={"client_id": args.client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": challenge["device_code"]})
                tokens = response.json()
                if tokens.get("error") == "authorization_pending":
                    continue
                if tokens.get("error") == "slow_down":
                    interval += 5
                    continue
                response.raise_for_status()
                refresh = tokens["refresh_token"]
                backend = Path(__file__).resolve().parents[1]
                save_refresh_token(str(backend / ".secrets/outlook-refresh.json"), refresh)
                env_file = backend / ".env"
                for name, value in {"SMTP_HOST": "smtp-mail.outlook.com", "SMTP_PORT": "587", "SMTP_FROM": sender,
                    "SMTP_USERNAME": sender, "SMTP_AUTH_MODE": "oauth2", "SMTP_OAUTH_CLIENT_ID": args.client_id,
                    "SMTP_OAUTH_TENANT": "consumers", "SMTP_OAUTH_TOKEN_FILE": str(backend / ".secrets/outlook-refresh.json")}.items():
                    set_key(str(env_file), name, value)
                print("授权已保存到服务端私密配置，未显示令牌、未发送邮件。请重启后端。")
                return 0
        print("授权已超时，请重新运行。")
    except Exception:
        print("授权未完成，请核实应用允许个人账户、已开启公共客户端流及 SMTP.Send 委托权限。未显示上游凭据。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
