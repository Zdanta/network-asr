import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    db_file = Path(tempfile.gettempdir()) / "ai_video_api_verify_admin.db"
    if db_file.exists():
        db_file.unlink()

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    os.environ["AUTH_TOKEN_SECRET"] = "verify-secret"
    os.environ["ADMIN_MOBILE_WHITELIST"] = "13800002000"
    os.environ["INIT_POINTS"] = "100"

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

    admin_login = client.post("/api/v1/auth/login", json={"mobile": "13800002000", "code": "123456"})
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = {"satoken": admin_login.json()["data"]["token"]}

    inviter_login = client.post("/api/v1/auth/login", json={"mobile": "13800002001", "code": "123456"})
    assert inviter_login.status_code == 200, inviter_login.text
    inviter_data = inviter_login.json()["data"]
    inviter_headers = {"satoken": inviter_data["token"]}

    user_login = client.post(
        "/api/v1/auth/login",
        json={"mobile": "13800002002", "code": "123456", "inviteCode": inviter_data["inviteCode"]},
    )
    assert user_login.status_code == 200, user_login.text
    user_data = user_login.json()["data"]
    user_headers = {"satoken": user_data["token"]}

    denied = client.get("/api/v1/admin/dashboard/overview", headers=user_headers)
    assert denied.status_code == 403, denied.text

    order = client.post("/api/v1/payment/order", headers=user_headers, json={"productType": "POINT_PACK_PLUS"})
    assert order.status_code == 200, order.text
    order_data = order.json()["data"]
    paid = client.post(
        "/api/v1/payment/notify",
        json={
            "orderNo": order_data["orderNo"],
            "thirdPartyOrderNo": "MOCK-ADMIN-001",
            "amount": "59.90",
            "payChannel": "MOCK",
            "payStatus": "SUCCESS",
        },
    )
    assert paid.status_code == 200, paid.text

    adjust = client.post(
        "/api/v1/admin/users/quota/adjust",
        headers=admin_headers,
        json={"uid": user_data["uid"], "points": 25, "remark": "admin grant test"},
    )
    assert adjust.status_code == 200, adjust.text
    assert adjust.json()["data"]["remainingPoints"] == 3625

    logs = client.get("/api/v1/quota/logs", headers=user_headers)
    assert logs.status_code == 200, logs.text
    assert any(item["changeType"] == "ADMIN_GRANT" for item in logs.json()["data"]["records"])

    overview = client.get("/api/v1/admin/dashboard/overview", headers=admin_headers)
    assert overview.status_code == 200, overview.text
    overview_data = overview.json()["data"]
    assert overview_data["totalUsers"] == 3
    assert overview_data["todayPaidOrders"] == 1

    users = client.get("/api/v1/admin/users", headers=admin_headers, params={"keyword": "13800002002"})
    assert users.status_code == 200, users.text
    assert users.json()["data"]["total"] == 1
    assert users.json()["data"]["records"][0]["uid"] == user_data["uid"]

    detail = client.get(f"/api/v1/admin/users/{user_data['uid']}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["paidOrderCount"] == 1
    assert detail.json()["data"]["remainingPoints"] == 3625

    withdrawal = client.post(
        "/api/v1/invite/withdrawals",
        headers=inviter_headers,
        json={"alipayAccount": "inviter-admin@example.com"},
    )
    assert withdrawal.status_code == 400, withdrawal.text

    for idx in range(2):
        pack = client.post("/api/v1/payment/order", headers=user_headers, json={"productType": "POINT_PACK_PLUS"})
        assert pack.status_code == 200, pack.text
        paid_pack = client.post(
            "/api/v1/payment/notify",
            json={
                "orderNo": pack.json()["data"]["orderNo"],
                "thirdPartyOrderNo": f"MOCK-ADMIN-PLUS-{idx}",
                "amount": "59.90",
                "payChannel": "MOCK",
                "payStatus": "SUCCESS",
            },
        )
        assert paid_pack.status_code == 200, paid_pack.text

    withdrawal = client.post(
        "/api/v1/invite/withdrawals",
        headers=inviter_headers,
        json={"alipayAccount": "inviter-admin@example.com"},
    )
    assert withdrawal.status_code == 200, withdrawal.text
    withdraw_no = withdrawal.json()["data"]["withdrawNo"]
    assert Decimal(withdrawal.json()["data"]["amount"]) == Decimal("17.97")

    withdrawals = client.get("/api/v1/admin/withdrawals", headers=admin_headers, params={"status": "PENDING"})
    assert withdrawals.status_code == 200, withdrawals.text
    assert withdrawals.json()["data"]["total"] == 1

    paid_status = client.put(
        f"/api/v1/admin/withdrawals/{withdraw_no}/status",
        headers=admin_headers,
        json={"status": "PAID", "remark": "manual payout done"},
    )
    assert paid_status.status_code == 200, paid_status.text
    paid_data = paid_status.json()["data"]
    assert paid_data["status"] == "PAID"
    assert paid_data["handledBy"] == admin_login.json()["data"]["userId"]
    assert paid_data["handledAt"] is not None
    assert paid_data["paidAt"] is not None
    assert paid_data["remark"] == "manual payout done"

    second_update = client.put(
        f"/api/v1/admin/withdrawals/{withdraw_no}/status",
        headers=admin_headers,
        json={"status": "REJECTED", "remark": "should fail"},
    )
    assert second_update.status_code == 400, second_update.text

    print("admin verification passed")

    get_engine().dispose()
    if db_file.exists():
        db_file.unlink()


if __name__ == "__main__":
    main()
