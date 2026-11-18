import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from pydantic import SecretStr
from app.core.exceptions import AppException
from app.modules.auth.mailer import send_verification_email


class OutlookMailerTest(unittest.TestCase):
    def config(self, directory):
        return SimpleNamespace(smtp_username="sender@outlook.com", smtp_from="sender@outlook.com",
            smtp_host="smtp-mail.outlook.com", smtp_port=587, smtp_security="auto", smtp_auth_mode="oauth2",
            smtp_oauth_client_id="test-client", smtp_oauth_client_secret=None,
            smtp_oauth_refresh_token=SecretStr("test-refresh"), smtp_oauth_tenant="consumers",
            smtp_oauth_token_file=str(Path(directory) / "refresh.json"))

    def test_outlook_uses_tls_xoauth2_and_saves_rotated_refresh_token(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            response = httpx.Response(200, json={"access_token": "test-access", "refresh_token": "test-rotated"},
                request=httpx.Request("POST", "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"))
            with patch("app.modules.auth.mailer.get_settings", return_value=config), \
                 patch("app.modules.auth.mailer.httpx.Client") as http, patch("app.modules.auth.mailer.smtplib.SMTP") as smtp:
                http.return_value.__enter__.return_value.post.return_value = response
                server = smtp.return_value.__enter__.return_value
                server.docmd.return_value = (235, b"accepted")
                send_verification_email("recipient@example.com", "654321")
                server.starttls.assert_called_once()
                server.login.assert_not_called()
                args = server.docmd.call_args.args
                self.assertEqual(args[0], "AUTH")
                self.assertIn("auth=Bearer test-access", base64.b64decode(args[1].split(" ", 1)[1]).decode())
                server.send_message.assert_called_once()
                self.assertEqual(json.loads(Path(config.smtp_oauth_token_file).read_text())["refresh_token"], "test-rotated")

    def test_missing_configuration_fails_closed_without_password_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            config.smtp_oauth_client_id = ""
            with patch("app.modules.auth.mailer.get_settings", return_value=config), \
                 patch("app.modules.auth.mailer.smtplib.SMTP") as smtp:
                with self.assertRaises(AppException) as caught:
                    send_verification_email("recipient@example.com", "654321")
                self.assertNotIn("654321", caught.exception.message)
                self.assertNotIn("test-refresh", caught.exception.message)
                smtp.assert_not_called()

    def test_qq_uses_implicit_tls_and_authorization_code_without_oauth(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            config.smtp_host, config.smtp_port, config.smtp_security = "smtp.qq.com", 465, "ssl"
            config.smtp_auth_mode, config.smtp_password = "password", SecretStr("test-authorization-code")
            config.smtp_username = config.smtp_from = "sender@qq.com"
            with patch("app.modules.auth.mailer.get_settings", return_value=config), \
                 patch("app.modules.auth.mailer.httpx.Client") as http, \
                 patch("app.modules.auth.mailer.smtplib.SMTP") as plain, \
                 patch("app.modules.auth.mailer.smtplib.SMTP_SSL") as secure:
                send_verification_email("recipient@example.com", "654321")
                secure.assert_called_once()
                self.assertEqual(secure.call_args.args[:2], ("smtp.qq.com", 465))
                self.assertTrue(secure.call_args.kwargs["context"].check_hostname)
                server = secure.return_value.__enter__.return_value
                server.login.assert_called_once_with("sender@qq.com", "test-authorization-code")
                server.starttls.assert_not_called()
                server.send_message.assert_called_once()
                plain.assert_not_called()
                http.assert_not_called()

    def test_qq_auth_failure_does_not_expose_authorization_code_or_otp(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            config.smtp_port, config.smtp_security, config.smtp_auth_mode = 465, "auto", "password"
            config.smtp_password = SecretStr("test-authorization-code")
            with patch("app.modules.auth.mailer.get_settings", return_value=config), \
                 patch("app.modules.auth.mailer.smtplib.SMTP_SSL") as secure:
                server = secure.return_value.__enter__.return_value
                server.login.side_effect = RuntimeError("test-authorization-code")
                with self.assertRaises(AppException) as caught:
                    send_verification_email("recipient@example.com", "654321")
                self.assertNotIn("test-authorization-code", caught.exception.message)
                self.assertNotIn("654321", caught.exception.message)
                server.send_message.assert_not_called()
