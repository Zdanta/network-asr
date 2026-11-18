import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.core.exceptions import AppException
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.modules.auth.email_codes import EmailCodeService
from app.modules.auth.schemas import LoginRequest
from app.modules.auth.service import AuthService


class EmailAuthTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.sent = []
        self.sender = patch("app.modules.auth.email_codes.send_verification_email", side_effect=lambda email, code: self.sent.append((email, code)))
        self.sender.start()
        self.addCleanup(self.sender.stop)

    def test_phone_and_static_code_are_not_login_credentials(self):
        with self.assertRaises(ValidationError):
            LoginRequest.model_validate({"mobile": "13800000000", "code": "123456"})
        with self.assertRaises(AppException):
            EmailCodeService(self.db).verify("user@example.com", "123456")

    def test_send_hashes_code_and_registration_consumes_it_once(self):
        service = EmailCodeService(self.db)
        result = service.send("user@example.com", "127.0.0.1")
        self.assertTrue(result["sent"])
        row = self.db.get(EmailVerification, "user@example.com")
        self.assertNotEqual(row.code_hash, self.sent[0][1])
        request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)})
        data = AuthService(self.db).login(LoginRequest(email="USER@example.com", code=self.sent[0][1]), request)
        self.assertEqual(data.email, "user@example.com")
        self.assertIsNone(data.mobile)
        self.assertEqual(len(list(self.db.scalars(select(User)))), 1)
        with self.assertRaises(AppException):
            service.verify("user@example.com", self.sent[0][1])

    def test_cooldown_expiry_and_failed_attempt_limit(self):
        service = EmailCodeService(self.db)
        service.send("user@example.com", "127.0.0.1")
        with self.assertRaises(AppException) as caught:
            service.send("user@example.com", "127.0.0.1")
        self.assertEqual(caught.exception.status_code, 429)
        wrong = "000000" if self.sent[0][1] != "000000" else "999999"
        for _ in range(5):
            with self.assertRaises(AppException):
                service.verify("user@example.com", wrong)
        with self.assertRaises(AppException):
            service.verify("user@example.com", self.sent[0][1])
        row = self.db.get(EmailVerification, "user@example.com")
        row.expires_at = datetime.now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(AppException):
            service.verify("user@example.com", self.sent[0][1])

    def test_wrong_mailbox_and_failed_delivery_cannot_verify(self):
        service = EmailCodeService(self.db)
        service.send("user@example.com", "127.0.0.1")
        with self.assertRaises(AppException):
            service.verify("other@example.com", self.sent[0][1])
        with patch("app.modules.auth.email_codes.send_verification_email", side_effect=AppException(1010, "发送失败")):
            with self.assertRaises(AppException):
                service.send("failed@example.com", "127.0.0.1")
        self.assertEqual(self.db.get(EmailVerification, "failed@example.com").state, "FAILED")

    def test_http_email_login_and_legacy_binding_preserve_account_identity(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from app.core.database import get_db
        from app.core.security import get_current_user
        from app.core.exceptions import register_exception_handlers
        from app.modules.auth.router import router
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1/auth")
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)
        response = client.post("/api/v1/auth/email-code", json={"email": "USER@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("code", response.json()["data"])
        response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "code": self.sent[-1][1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["email"], "user@example.com")
        self.assertTrue(response.json()["data"]["token"])
        self.assertEqual(client.post("/api/v1/auth/login", json={"mobile": "13800000000", "code": "123456"}).status_code, 422)
        legacy = User(uid="legacy-user", mobile="13800000000", invite_code="LEGACY", status="ENABLE")
        self.db.add(legacy)
        self.db.commit()
        original_id = legacy.id
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=original_id, is_guest=False)
        client.post("/api/v1/auth/email-code", json={"email": "legacy@example.com"})
        result = client.post("/api/v1/auth/bind-email", json={"email": "legacy@example.com", "code": self.sent[-1][1]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.db.get(User, original_id).uid, "legacy-user")
        self.assertEqual(self.db.get(User, original_id).email, "legacy@example.com")
