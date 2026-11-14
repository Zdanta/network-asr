import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def now():
    return datetime.now().isoformat(timespec="seconds")


class History:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, source_type TEXT, source_input TEXT, source_title TEXT,
                source_path TEXT, downloaded_path TEXT, audio_path TEXT, duration_seconds REAL,
                status TEXT, stage TEXT, progress INTEGER, raw_text TEXT, error_message TEXT,
                created_at TEXT, started_at TEXT, finished_at TEXT, deleted_at TEXT, output_dir TEXT)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            db.execute(
                "UPDATE tasks SET status='INTERRUPTED',stage='处理中断，可重试',finished_at=? WHERE status IN ('RUNNING','PENDING')",
                (now(),),
            )

    def create(self, kind, source, output):
        tid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO tasks(task_id,source_type,source_input,source_title,status,stage,created_at,output_dir) VALUES(?,?,?,?,?,?,?,?)",
                (
                    tid,
                    kind,
                    source,
                    Path(source).name if kind == "local" else "",
                    "PENDING",
                    "等待处理",
                    now(),
                    output,
                ),
            )
        return tid

    def update(self, tid, **values):
        allowed = {
            "source_title",
            "source_path",
            "downloaded_path",
            "audio_path",
            "duration_seconds",
            "status",
            "stage",
            "progress",
            "raw_text",
            "error_message",
            "started_at",
            "finished_at",
            "deleted_at",
        }
        if not values or not set(values) <= allowed:
            raise ValueError("无效任务字段")
        with self.connect() as db:
            db.execute(
                "UPDATE tasks SET " + ",".join(k + "=?" for k in values) + " WHERE task_id=?",
                (*values.values(), tid),
            )

    def get(self, tid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone()
            if row is None:
                raise ValueError("处理记录不存在")
            return dict(row)

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM tasks WHERE deleted_at IS NULL ORDER BY created_at DESC"
                )
            ]

    def delete(self, tid):
        task = self.get(tid)
        if task["status"] in ("PENDING", "RUNNING"):
            raise ValueError("处理中任务不能删除")
        self.update(tid, deleted_at=now())
