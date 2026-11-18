import logging
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.exceptions import AppException
from app.models.file import FileRecord
from app.models.task import Task
from app.modules.quota.service import QuotaService
from app.modules.task.asr import transcribe_audio
from app.repositories.file import FileRecordRepository
from app.repositories.task import TaskRepository

logger = logging.getLogger(__name__)


def process_task_asr(task_no: str) -> None:
    if get_settings().opcpay_enabled:
        from app.modules.payment.opcpay_worker import process_opcpay_task
        if process_opcpay_task(task_no):
            return
    started_at = perf_counter()
    logger.info("task worker started, taskNo=%s", task_no)

    session = get_session_factory()()
    try:
        with _stage(task_no, "load-file"):
            task, file_record = _load_task_and_file(session, task_no)
            _update_task(session, task, status="PROCESSING", progress=10, start_time=datetime.now(), error_msg=None)

        with _stage(task_no, "extract-audio"):
            from app.modules.guest.service import GuestService
            GuestService(session).before_asr(task_no)
            audio_url = _extract_audio(file_record)
            _update_task(session, task, progress=35, audio_url=audio_url)

        with _stage(task_no, "asr"):
            raw_text = _run_asr(file_record, audio_url)
            _update_task(session, task, progress=75)

        with _stage(task_no, "consume-quota"):
            if file_record.duration_seconds is not None:
                QuotaService(session).consume_quota_by_duration(
                    task.user_id,
                    file_record.duration_seconds,
                    task.task_no,
                    "按素材时长扣除额度",
                )
            session.commit()

        with _stage(task_no, "save-result"):
            task.raw_text = raw_text
            task.ai_text = None
            task.more_versions_json = None
            task.error_msg = None
            task.status = "SUCCESS"
            task.progress = 100
            task.finish_time = datetime.now()
            session.commit()

        logger.info("task worker finished, taskNo=%s, elapsedMs=%.2f", task_no, _elapsed_ms(started_at))
    except Exception as exc:
        session.rollback()
        logger.exception("task worker failed, taskNo=%s, elapsedMs=%.2f", task_no, _elapsed_ms(started_at))
        _mark_failed(session, task_no, str(exc))
    finally:
        session.close()


def _load_task_and_file(session, task_no: str) -> tuple[Task, FileRecord]:
    task = TaskRepository(session).get_by_task_no(task_no)
    if task is None:
        raise AppException(code=4004, message="处理记录不存在")

    file_record = FileRecordRepository(session).get(task.file_id)
    if file_record is None or file_record.deleted != 0:
        raise AppException(code=4004, message="文件不存在")
    return task, file_record


def _extract_audio(file_record: FileRecord) -> str:
    source_path = Path(get_settings().storage_root) / file_record.file_url
    if not source_path.exists():
        raise AppException(code=4004, message="上传文件不存在，请重新上传")

    if file_record.file_type == "AUDIO":
        return file_record.file_url

    if file_record.file_type != "VIDEO":
        raise AppException(code=1001, message="该文件格式暂不支持提取文字")

    ffmpeg = shutil.which(get_settings().ffmpeg_command)
    if ffmpeg is None:
        raise AppException(code=5000, message="音频处理组件不可用，请稍后重试", status_code=500)

    if not _has_audio_stream(source_path):
        raise AppException(code=1001, message="视频里没有可识别的声音")

    audio_relative_path = _build_audio_relative_path(file_record)
    audio_path = Path(get_settings().storage_root) / audio_relative_path
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:a:0",
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise AppException(code=5000, message="提取音频失败，请换一个文件再试", status_code=500)
    return audio_relative_path.as_posix()


def _has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which(get_settings().ffprobe_command)
    if ffprobe is None:
        raise AppException(code=5000, message="音频检测组件不可用，请稍后重试", status_code=500)

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return result.returncode == 0 and "audio" in result.stdout.lower()


def _run_asr(file_record: FileRecord, audio_url: str) -> str:
    audio_path = Path(get_settings().storage_root) / audio_url
    if not audio_path.exists():
        raise AppException(code=4004, message="音频文件不存在，请重新处理")

    result = transcribe_audio(audio_path, file_record.source_file_name)
    return result.text


def _build_audio_relative_path(file_record: FileRecord) -> Path:
    audio_dir = Path(get_settings().audio_subdir) / datetime.now().strftime("%Y%m%d")
    return audio_dir / f"{file_record.file_no}.wav"


def _update_task(
    session,
    task: Task,
    status: str | None = None,
    progress: int | None = None,
    audio_url: str | None = None,
    start_time: datetime | None = None,
    error_msg: str | None = None,
) -> None:
    if status is not None:
        task.status = status
    if progress is not None:
        task.progress = progress
    if audio_url is not None:
        task.audio_url = audio_url
    if start_time is not None:
        task.start_time = start_time
    if error_msg is not None:
        task.error_msg = error_msg
    session.commit()


def _mark_failed(session, task_no: str, error_msg: str) -> None:
    task = TaskRepository(session).get_by_task_no(task_no)
    if task is None:
        return
    task.status = "FAIL"
    task.progress = 100
    task.error_msg = error_msg[:1000]
    task.finish_time = datetime.now()
    task.raw_text = None
    task.ai_text = None
    task.more_versions_json = None
    from app.modules.guest.service import GuestService
    GuestService(session).settle(task_no, False)
    session.commit()


@contextmanager
def _stage(task_no: str, stage: str):
    started_at = perf_counter()
    logger.info("task stage started, taskNo=%s, stage=%s", task_no, stage)
    try:
        yield
        logger.info("task stage finished, taskNo=%s, stage=%s, elapsedMs=%.2f", task_no, stage, _elapsed_ms(started_at))
    except Exception:
        logger.exception("task stage failed, taskNo=%s, stage=%s, elapsedMs=%.2f", task_no, stage, _elapsed_ms(started_at))
        raise


def _elapsed_ms(started_at: float) -> float:
    return (perf_counter() - started_at) * 1000
