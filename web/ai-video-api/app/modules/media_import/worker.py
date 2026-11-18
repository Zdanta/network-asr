import logging
from contextlib import contextmanager
from time import perf_counter

import app.models  # noqa: F401
from app.common.ids import generate_biz_no
from app.core.database import get_session_factory
from app.core.exceptions import AppException
from app.models.file import FileRecord
from app.models.media_import import MediaImportJob
from app.modules.media_import.downloader import DownloadedMedia, PlaywrightMediaDownloader
from app.modules.media_import.service import _extract_url
from app.modules.task.service import TaskService
from app.repositories.file import FileRecordRepository
from app.repositories.media_import import MediaImportJobRepository
from app.workers.task_queue import task_worker_queue

logger = logging.getLogger(__name__)


def process_import_job(job_id: str) -> None:
    started_at = perf_counter()
    logger.info("media import worker started, jobId=%s", job_id)

    session = get_session_factory()()
    task_no: str | None = None
    try:
        with _stage(job_id, "load-job"):
            job = _load_job(session, job_id)
            _update_job(session, job, status="PROCESSING", progress=5, stage="load-job", error_message=None)

        with _stage(job_id, "extract-url"):
            source_url = job.source_url or _extract_url(job.source_text)
            if source_url is None:
                raise AppException(code=1001, message="没有识别到有效链接，请重新粘贴分享内容")
            job.source_url = source_url
            _update_job(session, job, progress=15, stage="extract-url")

        with _stage(job_id, "download-media"):
            _update_job(session, job, progress=25, stage="download-media")
            from app.modules.guest.service import GuestService, is_guest
            limit = GuestService(session).policy()["upload_mb"] * 1024 * 1024 if is_guest(session, job.user_id) else None
            session.commit()
            media = PlaywrightMediaDownloader(max_bytes=limit).download(source_url, job.job_id)
            _update_job(
                session,
                job,
                progress=65,
                stage="download-media",
                title=media.title,
                download_engine=media.download_engine,
                cookie_source=media.cookie_source,
            )

        with _stage(job_id, "save-file-record"):
            file_record = _create_file_record(session, job.user_id, media)
            job.file_id = file_record.id
            _update_job(session, job, progress=78, stage="save-file-record")

        with _stage(job_id, "create-task"):
            task = TaskService(session).create_task_for_file(job.user_id, file_record)
            task_no = task.task_no
            job.task_no = task.task_no
            _update_job(session, job, progress=90, stage="create-task")

        with _stage(job_id, "mark-success"):
            _update_job(session, job, status="SUCCESS", progress=100, stage="SUCCESS", error_message=None)

        if task_no:
            task_worker_queue.enqueue_task(task_no)

        logger.info("media import worker finished, jobId=%s, taskNo=%s, elapsedMs=%.2f", job_id, task_no, _elapsed_ms(started_at))
    except Exception as exc:
        session.rollback()
        logger.exception("media import worker failed, jobId=%s, elapsedMs=%.2f", job_id, _elapsed_ms(started_at))
        _mark_failed(session, job_id, str(exc))
    finally:
        session.close()


def _load_job(session, job_id: str) -> MediaImportJob:
    job = MediaImportJobRepository(session).get_by_job_id(job_id)
    if job is None:
        raise AppException(code=4004, message="导入任务不存在")
    return job


def _create_file_record(session, user_id: int, media: DownloadedMedia) -> FileRecord:
    repo = FileRecordRepository(session)
    file_record = FileRecord(
        file_no=_generate_file_no(repo),
        user_id=user_id,
        source_file_name=media.source_file_name,
        storage_file_name=media.storage_file_name,
        file_type=media.file_type,
        content_type=media.content_type,
        file_size=media.file_size,
        file_url=media.relative_path,
        duration_seconds=media.duration_seconds,
        status="UPLOADED",
        remark="import-link",
    )
    repo.add(file_record)
    return file_record


def _generate_file_no(repo: FileRecordRepository) -> str:
    for _ in range(10):
        file_no = generate_biz_no("FILE")
        if repo.get_by_file_no(file_no) is None:
            return file_no
    raise AppException(code=5000, message="文件编号生成失败，请稍后重试", status_code=500)


def _update_job(session, job: MediaImportJob, **kwargs) -> None:
    for key, value in kwargs.items():
        setattr(job, key, value)
    session.commit()


def _mark_failed(session, job_id: str, error_message: str) -> None:
    job = MediaImportJobRepository(session).get_by_job_id(job_id)
    if job is None:
        return
    job.status = "FAIL"
    job.progress = 100
    job.stage = "FAIL"
    job.error_message = error_message[:1000]
    session.commit()


@contextmanager
def _stage(job_id: str, stage: str):
    started_at = perf_counter()
    logger.info("media import stage started, jobId=%s, stage=%s", job_id, stage)
    try:
        yield
        logger.info(
            "media import stage finished, jobId=%s, stage=%s, elapsedMs=%.2f",
            job_id,
            stage,
            _elapsed_ms(started_at),
        )
    except Exception:
        logger.exception("media import stage failed, jobId=%s, stage=%s, elapsedMs=%.2f", job_id, stage, _elapsed_ms(started_at))
        raise


def _elapsed_ms(started_at: float) -> float:
    return (perf_counter() - started_at) * 1000
