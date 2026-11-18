import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MediaImportWorkerQueue:
    """In-process import queue boundary; can be swapped for Redis/ARQ later."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self._executor is not None:
                return
            max_workers = max(1, get_settings().media_import_worker_max_workers)
            self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="media-import-worker")
            logger.info("media import worker queue started, max_workers=%s", max_workers)

    def stop(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)
            logger.info("media import worker queue stopped")

    def enqueue_job(self, job_id: str) -> None:
        self.start()
        assert self._executor is not None
        logger.info("media import job enqueued, jobId=%s", job_id)
        self._executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: str) -> None:
        from app.modules.media_import.worker import process_import_job

        process_import_job(job_id)


media_import_worker_queue = MediaImportWorkerQueue()
