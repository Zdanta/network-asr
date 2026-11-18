import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    db_file = Path(tempfile.gettempdir()) / "ai_video_api_verify_commercial.db"
    if db_file.exists():
        db_file.unlink()

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    os.environ["AUTH_TOKEN_SECRET"] = "verify-secret"
    os.environ["INIT_POINTS"] = "100"
    os.environ["INVITE_REWARD_RATE_PERCENT"] = "10"

    import app.models  # noqa: F401
    from fastapi.testclient import TestClient

    from app.core.database import Base, get_engine
    from app.core.transaction import session_scope
    from app.main import app
    from app.models.system import SysConfig
    from app.repositories.system import SysConfigRepository

    Base.metadata.create_all(get_engine())
    with session_scope() as session:
        repo = SysConfigRepository(session)
        repo.add(SysConfig(config_key="INIT_POINTS", config_value="100", config_name="Initial points", status="ENABLE"))
        repo.add(SysConfig(config_key="INVITE_REWARD_RATE_PERCENT", config_value="10", config_name="Invite rate", status="ENABLE"))

    client = TestClient(app)

    inviter_login = client.post("/api/v1/auth/login", json={"mobile": "13800001001", "code": "123456"})
    assert inviter_login.status_code == 200, inviter_login.text
    inviter_data = inviter_login.json()["data"]
    inviter_headers = {"satoken": inviter_data["token"]}

    invitee_login = client.post(
        "/api/v1/auth/login",
        json={"mobile": "13800001002", "code": "123456", "inviteCode": inviter_data["inviteCode"]},
    )
    assert invitee_login.status_code == 200, invitee_login.text
    invitee_headers = {"satoken": invitee_login.json()["data"]["token"]}

    order = client.post("/api/v1/payment/order", headers=invitee_headers, json={"productType": "FIRST_RECHARGE_GIFT"})
    assert order.status_code == 200, order.text
    order_data = order.json()["data"]
    assert order_data["amount"] == "9.90"

    notify_payload = {
        "orderNo": order_data["orderNo"],
        "thirdPartyOrderNo": "MOCK-COMMERCIAL-001",
        "amount": "9.90",
        "payChannel": "MOCK",
        "payStatus": "SUCCESS",
    }
    notify = client.post("/api/v1/payment/notify", json=notify_payload)
    assert notify.status_code == 200, notify.text
    notify_again = client.post("/api/v1/payment/notify", json=notify_payload)
    assert notify_again.status_code == 200, notify_again.text

    order_info = client.get(f"/api/v1/payment/order/{order_data['orderNo']}", headers=invitee_headers)
    assert order_info.status_code == 200, order_info.text
    assert order_info.json()["data"]["status"] == "SUCCESS"

    quota = client.get("/api/v1/quota", headers=invitee_headers)
    assert quota.status_code == 200, quota.text
    assert quota.json()["data"]["remainingPoints"] == 1100

    logs = client.get("/api/v1/quota/logs", headers=invitee_headers)
    assert logs.status_code == 200, logs.text
    purchase_logs = [item for item in logs.json()["data"]["records"] if item["changeType"] == "PURCHASE"]
    assert len(purchase_logs) == 1, purchase_logs

    invite_info = client.get("/api/v1/invite", headers=inviter_headers)
    assert invite_info.status_code == 200, invite_info.text
    assert invite_info.json()["data"]["inviteCount"] == 1
    assert Decimal(invite_info.json()["data"]["rewardTotal"]) == Decimal("0.99")

    invite_records = client.get("/api/v1/invite/records", headers=inviter_headers)
    assert invite_records.status_code == 200, invite_records.text
    assert len(invite_records.json()["data"]) == 1
    assert invite_records.json()["data"][0]["triggerOrderNo"] == order_data["orderNo"]

    too_early_withdrawal = client.post(
        "/api/v1/invite/withdrawals",
        headers=inviter_headers,
        json={"alipayAccount": "inviter@example.com"},
    )
    assert too_early_withdrawal.status_code == 400, too_early_withdrawal.text

    for idx in range(2):
        pack = client.post("/api/v1/payment/order", headers=invitee_headers, json={"productType": "POINT_PACK_PLUS"})
        assert pack.status_code == 200, pack.text
        pack_data = pack.json()["data"]
        paid = client.post(
            "/api/v1/payment/notify",
            json={
                "orderNo": pack_data["orderNo"],
                "thirdPartyOrderNo": f"MOCK-COMMERCIAL-PLUS-{idx}",
                "amount": "59.90",
                "payChannel": "MOCK",
                "payStatus": "SUCCESS",
            },
        )
        assert paid.status_code == 200, paid.text

    summary = client.get("/api/v1/invite/withdrawals/summary", headers=inviter_headers)
    assert summary.status_code == 200, summary.text
    summary_data = summary.json()["data"]
    assert Decimal(summary_data["rewardTotal"]) == Decimal("12.97")
    assert summary_data["canApply"] is True

    withdrawal = client.post(
        "/api/v1/invite/withdrawals",
        headers=inviter_headers,
        json={"alipayAccount": "inviter@example.com"},
    )
    assert withdrawal.status_code == 200, withdrawal.text
    withdrawal_data = withdrawal.json()["data"]
    assert Decimal(withdrawal_data["amount"]) == Decimal("12.97")
    assert withdrawal_data["status"] == "PENDING"

    withdrawals = client.get("/api/v1/invite/withdrawals", headers=inviter_headers)
    assert withdrawals.status_code == 200, withdrawals.text
    assert len(withdrawals.json()["data"]) == 1

    after_summary = client.get("/api/v1/invite/withdrawals/summary", headers=inviter_headers)
    assert after_summary.status_code == 200, after_summary.text
    assert Decimal(after_summary.json()["data"]["withdrawableAmount"]) == Decimal("0.00")

    print("commercial verification passed")

    get_engine().dispose()
    if db_file.exists():
        db_file.unlink()


if __name__ == "__main__":
    main()
