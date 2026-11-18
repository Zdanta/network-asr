import importlib
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.models
from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.exceptions import AppException, register_exception_handlers
from app.api.v1.router import api_v1_router
from app.models.guest import GuestIdentity, GuestReservation
from app.models.user import User
from app.models.quota import UserQuota, QuotaLog
from app.models.file import FileRecord
from app.models.task import Task
from app.modules.guest.service import GuestService, COOKIE, client_ip
from app.modules.payment.opcpay_worker import process_opcpay_task


class GuestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "guest.db"))
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.stack = ExitStack()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.stack.close)
        self.cfg = Settings(_env_file=None, guest_enabled=True, opcpay_enabled=True, auth_token_secret="isolated-guest-tests",
            storage_root=str(Path(self.temp.name)/"storage"), app_env="local", guest_trusted_proxies="127.0.0.1/32")
        for name in ("app.core.security", "app.modules.guest.service", "app.modules.guest.router", "app.modules.quota.service",
                     "app.modules.task.service", "app.modules.task.worker", "app.modules.file.service", "app.modules.payment.opcpay_service",
                     "app.modules.payment.service", "app.modules.admin.service"):
            self.stack.enter_context(patch.object(importlib.import_module(name), "get_settings", return_value=self.cfg))
        self.stack.enter_context(patch("app.modules.payment.opcpay_worker.get_session_factory", return_value=self.factory))
        self.stack.enter_context(patch("app.modules.task.service.task_worker_queue.enqueue_task"))
        self.stack.enter_context(patch("app.modules.media_import.service.media_import_worker_queue.enqueue_job"))
        self.stack.enter_context(patch("app.modules.file.service.probe_duration_seconds", return_value=96))
        self.verify = self.stack.enter_context(patch("app.modules.auth.email_codes.EmailCodeService.verify"))
        self.access = self.stack.enter_context(patch("app.modules.payment.opcpay_client.OpcpayClient.access", return_value={"remaining":0,"quota_unit":"POINT"}))
        self.remote = self.stack.enter_context(patch("app.modules.payment.opcpay_client.OpcpayClient.request", side_effect=AssertionError("no remote payment writes")))
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(api_v1_router, prefix="/api/v1")
        def override():
            with self.factory() as db:
                yield db
        app.dependency_overrides[get_db] = override
        self.client = self.stack.enter_context(TestClient(app))

    def claim(self, device="device-one-1234567890"):
        response = self.client.post("/api/v1/auth/guest", json={"deviceId":device})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def upload(self):
        response = self.client.post("/api/v1/file/upload", files={"file":("sample.wav",b"RIFF-test-file","audio/wav")})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["fileNo"]

    def create(self, file_no):
        response = self.client.post("/api/v1/task", json={"fileNo":file_no})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["taskNo"]

    def process(self, task_no, fail=False):
        with patch("app.modules.task.worker._extract_audio", return_value="audio.wav"), \
             patch("app.modules.task.worker._run_asr", side_effect=RuntimeError("failed") if fail else None, return_value="访客文字稿"):
            self.assertTrue(process_opcpay_task(task_no))

    def test_claim_is_once_cookie_is_http_only_and_guest_cannot_purchase_or_admin(self):
        self.assertIsNone(self.client.get("/api/v1/auth/guest-session").json()["data"])
        user = self.claim()
        self.assertTrue(user["guest"])
        self.assertEqual(user["remainingPoints"],100)
        self.assertEqual(self.claim()["userId"], user["userId"])
        self.assertEqual(self.client.get("/api/v1/quota").json()["data"]["remainingPoints"],100)
        self.access.assert_not_called()
        self.assertEqual(self.client.post("/api/v1/payment/opcpay/purchase",json={"actionId":"guest-buy-123","skuId":"anything"}).json()["code"],2101)
        self.assertEqual(self.client.get("/api/v1/admin/orders").status_code,403)
        self.remote.assert_not_called()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserQuota)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(QuotaLog)),1)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/v1/auth/guest",json={"deviceId":"device-one-1234567890"}).json()["code"],2101)

    def test_ip_claim_limit_and_device_impersonation_do_not_issue_extra_gifts(self):
        for i in range(3):
            self.client.cookies.clear()
            self.claim("different-device-"+str(i))
        self.client.cookies.clear()
        response=self.client.post("/api/v1/auth/guest",json={"deviceId":"different-device-4"})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.json()["code"],2101)

    def test_task_reservation_dedup_and_exact_local_consumption(self):
        user=self.claim(); file_no=self.upload(); task_no=self.create(file_no)
        self.assertEqual(self.create(file_no),task_no)
        self.assertEqual(self.client.post("/api/v1/file/upload",files={"file":("next.wav",b"data","audio/wav")}).status_code,409)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(GuestReservation)),1)
            self.assertEqual(db.get(GuestReservation,task_no).points,16)
        self.process(task_no)
        self.process(task_no)
        self.assertEqual(self.client.get(f"/api/v1/task/{task_no}/result").json()["data"]["rawText"],"访客文字稿")
        self.assertEqual(self.client.get("/api/v1/quota").json()["data"]["remainingPoints"],84)
        with self.factory() as db:
            self.assertEqual(db.get(GuestReservation,task_no).state,"CONSUMED")
            self.assertEqual(db.scalar(select(UserQuota).where(UserQuota.user_id==user["userId"])).remaining_points,84)
        self.remote.assert_not_called()

    def test_failed_asr_releases_hold_without_debit(self):
        self.claim(); task_no=self.create(self.upload());self.process(task_no,fail=True)
        with self.factory() as db:
            self.assertEqual(db.get(GuestReservation,task_no).state,"RELEASED")
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points,100)
        self.upload()

    def test_insufficient_quota_keeps_uploaded_file_without_creating_task(self):
        self.claim()
        with patch("app.modules.file.service.probe_duration_seconds",return_value=601): file_no=self.upload()
        response=self.client.post("/api/v1/task",json={"fileNo":file_no})
        self.assertEqual(response.json()["code"],2101)
        with self.factory() as db:
            self.assertIsNotNone(db.scalar(select(FileRecord).where(FileRecord.file_no==file_no)))
            self.assertEqual(db.scalar(select(func.count()).select_from(Task)),0)
            self.assertEqual(db.scalar(select(func.count()).select_from(GuestReservation)),0)

    def test_new_email_upgrades_same_identity_and_inherits_remaining_points(self):
        user=self.claim();task_no=self.create(self.upload());self.process(task_no)
        response=self.client.post("/api/v1/auth/login",json={"email":"new@example.com","code":"123456"})
        self.assertEqual(response.status_code,200,response.text)
        login=response.json()["data"]
        self.assertTrue(login["guestConverted"])
        self.assertEqual(login["userId"],user["userId"])
        self.assertEqual(login["remainingPoints"],84)
        self.assertNotIn(COOKIE,self.client.cookies)
        with self.factory() as db:
            self.assertEqual(db.get(GuestIdentity,user["userId"]).state,"FORMAL")
            self.assertEqual(db.scalar(select(func.count()).select_from(QuotaLog).where(QuotaLog.change_type=="REGISTER_GIFT")),1)
        self.assertEqual(self.client.get(f"/api/v1/task/{task_no}/result",headers={"satoken":login["token"]}).status_code,200)

    def test_existing_account_merge_migrates_records_without_duplicate_gift(self):
        with self.factory() as db:
            account=User(uid="existing-account",email="existing@example.com",invite_code="EXISTING",status="ENABLE")
            db.add(account);db.flush();aid=account.id
            db.add(UserQuota(user_id=aid,remaining_points=10))
            db.add(QuotaLog(user_id=aid,change_type="REGISTER_GIFT",change_amount=100,before_points=0,after_points=100,biz_no="REGISTER-existing"))
            db.commit()
        guest=self.claim();task_no=self.create(self.upload());self.process(task_no)
        response=self.client.post("/api/v1/auth/login",json={"email":"existing@example.com","code":"123456"})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()["data"];self.assertEqual(result["userId"],aid);self.assertEqual(result["remainingPoints"],10)
        with self.factory() as db:
            self.assertEqual(db.get(GuestIdentity,guest["userId"]).state,"MERGED")
            self.assertEqual(db.scalar(select(Task).where(Task.task_no==task_no)).user_id,aid)
            self.assertEqual(db.scalar(select(UserQuota).where(UserQuota.user_id==guest["userId"])).remaining_points,0)
            self.assertEqual(db.scalar(select(QuotaLog).where(QuotaLog.change_type=="TRIAL_ARCHIVE")).change_amount,-84)
        self.assertEqual(self.client.get(f"/api/v1/task/{task_no}/result",headers={"satoken":result["token"]}).status_code,200)

    def test_running_task_prevents_conversion_before_code_is_consumed(self):
        self.claim();self.create(self.upload())
        response=self.client.post("/api/v1/auth/login",json={"email":"new@example.com","code":"123456"})
        self.assertEqual(response.status_code,409)
        self.verify.assert_not_called()

    def test_guest_ownership_and_import_url_restrictions(self):
        user=self.claim();file_no=self.upload()
        self.client.cookies.clear();self.claim("another-device-12345")
        self.assertEqual(self.client.post("/api/v1/task",json={"fileNo":file_no}).status_code,404)
        response=self.client.post("/api/v1/file/import-link/jobs",json={"sourceText":"http://127.0.0.1/private"})
        self.assertEqual(response.status_code,400)

    def test_global_budget_and_proxy_header_trust(self):
        self.cfg.guest_global_points=10
        self.claim();file_no=self.upload()
        response=self.client.post("/api/v1/task",json={"fileNo":file_no})
        self.assertEqual(response.status_code,429)
        request=Request({"type":"http","client":("203.0.113.2",1),"headers":[(b"x-forwarded-for",b"1.1.1.1")]})
        self.assertEqual(client_ip(request),"203.0.113.2")
        request=Request({"type":"http","client":("127.0.0.1",1),"headers":[(b"x-forwarded-for",b"1.1.1.1, 203.0.113.3")]})
        self.assertEqual(client_ip(request),"203.0.113.3")

    def test_import_admission_is_single_and_limited_before_downloading(self):
        self.claim()
        response=self.client.post("/api/v1/file/import-link/jobs",json={"sourceText":"https://v.douyin.com/example/"})
        self.assertEqual(response.status_code,200,response.text)
        second=self.client.post("/api/v1/file/import-link/jobs",json={"sourceText":"https://v.douyin.com/other/"})
        self.assertEqual(second.status_code,409)
        self.remote.assert_not_called()

    def test_oversize_upload_is_removed_and_upload_lease_released(self):
        user=self.claim();self.cfg.guest_upload_mb=1
        response=self.client.post("/api/v1/file/upload",files={"file":("large.wav",b"x"*(1024*1024+1),"audio/wav")})
        self.assertEqual(response.status_code,400)
        with self.factory() as db:
            self.assertIsNone(db.get(GuestIdentity,user["userId"]).upload_lease)
            self.assertEqual(db.scalar(select(func.count()).select_from(FileRecord)),0)
        self.assertFalse(any((Path(self.temp.name)/"storage").rglob("*.wav")))

    def test_policy_changes_only_new_claims_and_admin_counts_exclude_guests(self):
        self.claim()
        response=self.client.get("/api/v1/admin/guest-policy")
        self.assertEqual(response.status_code,403)
        from app.modules.admin.dependencies import get_admin_user
        from app.core.security import CurrentUser
        self.client.app.dependency_overrides[get_admin_user]=lambda:CurrentUser(id=999,uid="test-admin",mobile=None,is_admin=True)
        body={"enabled":True,"points":50,"ip_points":300,"global_points":10000,"ip_claims":3,"upload_mb":50,"session_days":7}
        response=self.client.put("/api/v1/admin/guest-policy",json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get("/api/v1/public/experience").json()["data"]["points"],50)
        self.assertEqual(self.claim()["remainingPoints"],100)
        self.client.cookies.clear();self.assertEqual(self.claim("policy-device-second-123")["remainingPoints"],50)
        self.assertEqual(self.client.get("/api/v1/admin/users").json()["data"]["total"],0)
        self.assertEqual(self.client.get("/api/v1/admin/guests").json()["data"]["total"],2)

    def test_expired_guest_cleanup_preserves_registered_accounts_and_claim_record(self):
        user=self.claim();file_no=self.upload()
        with self.factory() as db:
            identity=db.get(GuestIdentity,user["userId"])
            identity.expires_at=datetime.now()-timedelta(days=2)
            path=Path(self.temp.name)/"storage"/db.scalar(select(FileRecord)).file_url
            self.assertTrue(path.exists())
            db.commit()
        from app.modules.guest.cleanup import cleanup_expired_guests
        with patch("app.modules.guest.cleanup.get_session_factory",return_value=self.factory), \
             patch("app.workers.media_cleanup.get_settings",return_value=self.cfg):
            cleanup_expired_guests()
        self.assertFalse(path.exists())
        with self.factory() as db:
            self.assertEqual(db.get(GuestIdentity,user["userId"]).state,"EXPIRED")
        self.assertIsNone(self.client.get("/api/v1/auth/guest-session").json()["data"])

    def test_guest_identity_cannot_be_used_as_inviter(self):
        first=self.claim()
        self.client.cookies.clear();second=self.claim("referral-second-device")
        response=self.client.post("/api/v1/auth/login",json={"email":"referral@example.com","code":"123456","inviteCode":first["inviteCode"]})
        self.assertEqual(response.status_code,400)
        with self.factory() as db:
            self.assertEqual(db.get(GuestIdentity,second["userId"]).state,"GUEST")
            self.assertIsNone(db.get(User,second["userId"]).email)

