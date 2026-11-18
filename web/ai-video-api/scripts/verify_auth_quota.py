import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    db_file = Path(tempfile.gettempdir()) / "ai_video_api_verify_auth_quota.db"
    if db_file.exists():
        db_file.unlink()

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    os.environ["AUTH_TOKEN_SECRET"] = "verify-secret"
    os.environ["ADMIN_MOBILE_WHITELIST"] = "13800000001"

    import app.models  # noqa: F401
    from fastapi.testclient import TestClient

    from app.core.database import Base, get_engine
    from app.main import app
    from app.models.system import SysConfig
    from app.repositories.system import SysConfigRepository
    from app.core.transaction import session_scope

    Base.metadata.create_all(get_engine())
    with session_scope() as session:
        repo = SysConfigRepository(session)
        repo.add(SysConfig(config_key="INIT_POINTS", config_value="188", config_name="Initial points", status="ENABLE"))
        repo.add(SysConfig(config_key="SECONDS_PER_POINT", config_value="6", config_name="Seconds per point", status="ENABLE"))

    client = TestClient(app)

    inviter_login = client.post(
        "/api/v1/auth/login",
        json={"mobile": "13800000001", "code": "123456"},
    )
    assert inviter_login.status_code == 200, inviter_login.text
    inviter_data = inviter_login.json()["data"]
    assert inviter_data["remainingPoints"] == 188
    assert inviter_data["admin"] is True

    invitee_login = client.post(
        "/api/v1/auth/login",
        json={"mobile": "13800000002", "code": "123456", "inviteCode": inviter_data["inviteCode"]},
    )
    assert invitee_login.status_code == 200, invitee_login.text
    invitee_data = invitee_login.json()["data"]
    assert invitee_data["remainingPoints"] == 188

    headers = {"satoken": invitee_data["token"]}
    user_info = client.get("/api/v1/user/info", headers=headers)
    assert user_info.status_code == 200, user_info.text
    assert user_info.json()["data"]["mobile"] == "13800000002"

    quota = client.get("/api/v1/quota", headers=headers)
    assert quota.status_code == 200, quota.text
    assert quota.json()["data"]["remainingCount"] == 188

    quota_logs = client.get("/api/v1/quota/logs", headers=headers)
    assert quota_logs.status_code == 200, quota_logs.text
    assert quota_logs.json()["data"]["total"] >= 1

    profile_logs = client.get("/api/v1/profile/quota-logs", headers=headers)
    assert profile_logs.status_code == 200, profile_logs.text
    assert profile_logs.json()["data"]["records"][0]["changeType"] == "REGISTER_GIFT"

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200, logout.text

    after_logout = client.get("/api/v1/user/info", headers=headers)
    assert after_logout.status_code == 401, after_logout.text
    assert after_logout.json()["code"] == 1002

    print("auth/quota verification passed")

    get_engine().dispose()
    if db_file.exists():
        db_file.unlink()


if __name__ == "__main__":
    main()
