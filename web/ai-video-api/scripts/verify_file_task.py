import os
import shutil
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    db_file = Path(tempfile.gettempdir()) / "ai_video_api_verify_file_task.db"
    storage_root = Path(tempfile.gettempdir()) / "ai_video_api_verify_storage"
    if db_file.exists():
        db_file.unlink()
    if storage_root.exists():
        shutil.rmtree(storage_root)

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    os.environ["AUTH_TOKEN_SECRET"] = "verify-secret"
    os.environ["STORAGE_ROOT"] = storage_root.as_posix()
    os.environ["INIT_POINTS"] = "100"
    os.environ["SECONDS_PER_POINT"] = "6"

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
        repo.add(SysConfig(config_key="SECONDS_PER_POINT", config_value="6", config_name="Seconds per point", status="ENABLE"))

    client = TestClient(app)

    login = client.post("/api/v1/auth/login", json={"mobile": "13800000003", "code": "123456"})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["token"]
    headers = {"satoken": token}

    upload = client.post(
        "/api/v1/file/upload",
        headers=headers,
        data={"durationSeconds": "12"},
        files={"file": ("demo.mp3", b"fake mp3 bytes", "audio/mpeg")},
    )
    assert upload.status_code == 200, upload.text
    file_no = upload.json()["data"]["fileNo"]

    created = client.post("/api/v1/task", headers=headers, json={"fileNo": file_no})
    assert created.status_code == 200, created.text
    task_no = created.json()["data"]["taskNo"]

    result_data = None
    for _ in range(20):
        result = client.get(f"/api/v1/task/{task_no}/result", headers=headers)
        assert result.status_code == 200, result.text
        result_data = result.json()["data"]
        if result_data["status"] in {"SUCCESS", "FAIL"}:
            break
        time.sleep(0.1)

    assert result_data is not None
    assert result_data["status"] == "SUCCESS", result_data
    assert "demo.mp3" in result_data["rawText"]
    assert result_data["aiText"] is None
    assert result_data["moreVersions"] == []
    assert result_data["estimatedPoints"] == 2

    detail = client.get(f"/api/v1/task/{task_no}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["status"] == "SUCCESS"

    page = client.get("/api/v1/task", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["data"]["total"] == 1

    recent = client.get("/api/v1/task/recent", headers=headers)
    assert recent.status_code == 200, recent.text
    assert len(recent.json()["data"]) == 1

    quota = client.get("/api/v1/quota", headers=headers)
    assert quota.status_code == 200, quota.text
    assert quota.json()["data"]["remainingPoints"] == 98

    other_login = client.post("/api/v1/auth/login", json={"mobile": "13800000004", "code": "123456"})
    other_headers = {"satoken": other_login.json()["data"]["token"]}
    other_page = client.get("/api/v1/task", headers=other_headers)
    assert other_page.status_code == 200, other_page.text
    assert other_page.json()["data"]["total"] == 0

    print("file/task verification passed")

    get_engine().dispose()
    if db_file.exists():
        db_file.unlink()
    if storage_root.exists():
        shutil.rmtree(storage_root)


if __name__ == "__main__":
    main()
