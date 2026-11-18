import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TaskWorkerQueue:
    """Small in-process queue boundary that can later be swapped for Redis/ARQ."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self._executor is not None:
                return
            max_workers = max(1, get_settings().task_worker_max_workers)
            self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="task-worker")
            logger.info("task worker queue started, max_workers=%s", max_workers)

    def stop(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)
            logger.info("task worker queue stopped")

    def enqueue_task(self, task_no: str) -> None:
        self.start()
        assert self._executor is not None
        logger.info("task enqueued, taskNo=%s", task_no)
        self._executor.submit(self._run_task, task_no)

    def _run_task(self, task_no: str) -> None:
        from app.modules.task.worker import process_task_asr

        process_task_asr(task_no)


task_worker_queue = TaskWorkerQueue()
