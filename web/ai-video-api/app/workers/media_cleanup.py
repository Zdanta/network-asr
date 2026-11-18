import logging
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.file import FileRecord
from app.models.task import Task

logger = logging.getLogger(__name__)

TERMINAL_TASK_STATUSES = {"SUCCESS", "FAIL"}


def import_download_expires_at(task: Task) -> datetime:
    return task.created_at + timedelta(seconds=max(1, get_settings().import_download_ttl_seconds))


def resolve_storage_path(relative_path: str) -> Path | None:
    root = Path(get_settings().storage_root).resolve()
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        logger.error("refused to access path outside storage root, path=%s", relative_path)
        return None
    return target


def cleanup_expired_import_media(now: datetime | None = None) -> int:
    current_time = now or datetime.now()
    session = get_session_factory()()
    cleaned = 0
    try:
        files = session.execute(
            select(FileRecord).where(
                FileRecord.deleted == 0,
                FileRecord.remark == "import-link",
                FileRecord.status != "EXPIRED",
            )
        ).scalars().all()
        for file_record in files:
            tasks = session.execute(select(Task).where(Task.file_id == file_record.id)).scalars().all()
            expires_at = (
                min(import_download_expires_at(task) for task in tasks)
                if tasks
                else file_record.created_at + timedelta(seconds=max(1, get_settings().import_download_ttl_seconds))
            )
            if expires_at > current_time:
                continue
            if any(task.deleted == 0 and task.status not in TERMINAL_TASK_STATUSES for task in tasks):
                continue

            _unlink_relative_path(file_record.file_url)
            for task in tasks:
                if task.audio_url:
                    _unlink_relative_path(task.audio_url)
                    task.audio_url = None
            file_record.status = "EXPIRED"
            file_record.file_size = 0
            cleaned += 1

        protected_paths = {
            file_record.file_url
            for file_record in files
            if file_record.status != "EXPIRED"
        }
        cleaned += _cleanup_orphan_import_files(current_time, protected_paths)
        if cleaned:
            session.commit()
            logger.info("expired import media cleaned, count=%s", cleaned)
        return cleaned
    except Exception:
        session.rollback()
        logger.exception("expired import media cleanup failed")
        return 0
    finally:
        session.close()


def _unlink_relative_path(relative_path: str) -> None:
    target = resolve_storage_path(relative_path)
    if target is not None:
        target.unlink(missing_ok=True)


def _cleanup_orphan_import_files(current_time: datetime, protected_paths: set[str]) -> int:
    settings = get_settings()
    root = Path(settings.storage_root).resolve()
    import_root = (root / settings.import_subdir).resolve()
    if import_root == root or root not in import_root.parents or not import_root.exists():
        return 0

    ttl = timedelta(seconds=max(1, settings.import_download_ttl_seconds))
    cleaned = 0
    for target in import_root.rglob("*"):
        if not target.is_file():
            continue
        relative_path = target.resolve().relative_to(root).as_posix()
        if relative_path in protected_paths:
            continue
        modified_at = datetime.fromtimestamp(target.stat().st_mtime)
        if modified_at + ttl > current_time:
            continue
        target.unlink(missing_ok=True)
        cleaned += 1
    return cleaned


class MediaCleanupWorker:
    def __init__(self) -> None:
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = Thread(target=self._run, name="media-cleanup-worker", daemon=True)
            self._thread.start()
            logger.info("media cleanup worker started")

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout=5)
            logger.info("media cleanup worker stopped")

    def _run(self) -> None:
        interval = max(10, get_settings().media_cleanup_interval_seconds)
        while not self._stop_event.is_set():
            cleanup_expired_import_media()
            try:
                from app.modules.guest.cleanup import cleanup_expired_guests
                cleanup_expired_guests()
            except Exception:
                logger.warning("guest cleanup deferred; check migration and storage")
            self._stop_event.wait(interval)


media_cleanup_worker = MediaCleanupWorker()
