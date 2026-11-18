import os
import shutil
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args) -> None:  # noqa: A002
        return


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    db_file = Path(tempfile.gettempdir()) / "ai_video_api_verify_import_job.db"
    storage_root = Path(tempfile.gettempdir()) / "ai_video_api_verify_import_storage"
    media_root = Path(tempfile.gettempdir()) / "ai_video_api_verify_import_media"
    for path in (db_file,):
        if path.exists():
            path.unlink()
    for path in (storage_root, media_root):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    media_file = media_root / "douyin-demo.mp3"
    media_file.write_bytes(b"fake mp3 bytes from import job")

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    os.environ["AUTH_TOKEN_SECRET"] = "verify-secret"
    os.environ["STORAGE_ROOT"] = storage_root.as_posix()
    os.environ["INIT_POINTS"] = "100"
    os.environ["SECONDS_PER_POINT"] = "6"
    os.environ["MEDIA_IMPORT_WORKER_MAX_WORKERS"] = "1"

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

    handler = partial(QuietHandler, directory=str(media_root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        media_url = f"http://127.0.0.1:{server.server_port}/douyin-demo.mp3"
        client = TestClient(app)

        login = client.post("/api/v1/auth/login", json={"mobile": "13800000005", "code": "123456"})
        assert login.status_code == 200, login.text
        headers = {"satoken": login.json()["data"]["token"]}

        created = client.post(
            "/api/v1/file/import-link/jobs",
            headers=headers,
            json={"sourceText": f"copy from douyin {media_url}"},
        )
        assert created.status_code == 200, created.text
        job_id = created.json()["data"]["jobId"]

        job_data = None
        for _ in range(30):
            status = client.get(f"/api/v1/file/import-link/jobs/{job_id}", headers=headers)
            assert status.status_code == 200, status.text
            job_data = status.json()["data"]
            if job_data["status"] in {"SUCCESS", "FAIL"}:
                break
            time.sleep(0.2)

        assert job_data is not None
        assert job_data["status"] == "SUCCESS", job_data
        assert job_data["progress"] == 100
        assert job_data["file"]["sourceFileName"] == "douyin-demo.mp3"
        assert job_data["file"]["downloadEngine"] == "direct-http"
        assert job_data["taskNo"]

        task_no = job_data["taskNo"]
        result_data = None
        for _ in range(30):
            result = client.get(f"/api/v1/task/{task_no}/result", headers=headers)
            assert result.status_code == 200, result.text
            result_data = result.json()["data"]
            if result_data["status"] in {"SUCCESS", "FAIL"}:
                break
            time.sleep(0.2)

        assert result_data is not None
        assert result_data["status"] == "SUCCESS", result_data
        assert "douyin-demo.mp3" in result_data["rawText"]
        assert result_data["aiText"] is None
        assert result_data["moreVersions"] == []

        print("import-link job verification passed")
    finally:
        server.shutdown()
        get_engine().dispose()
        if db_file.exists():
            db_file.unlink()
        for path in (storage_root, media_root):
            if path.exists():
                shutil.rmtree(path)


if __name__ == "__main__":
    main()
