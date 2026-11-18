import re

from sqlalchemy.orm import Session

from app.common.ids import generate_biz_no
from app.core.exceptions import AppException
from app.models.file import FileRecord
from app.models.media_import import MediaImportJob
from app.modules.media_import.schemas import (
    ImportJobFileVO,
    ImportLinkJobCreateRequest,
    ImportLinkJobCreateVO,
    ImportLinkJobStatusVO,
)
from app.repositories.file import FileRecordRepository
from app.repositories.media_import import MediaImportJobRepository
from app.workers.media_import_queue import media_import_worker_queue


class MediaImportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_repo = MediaImportJobRepository(db)
        self.file_repo = FileRecordRepository(db)

    def create_job(self, user_id: int, request_data: ImportLinkJobCreateRequest) -> ImportLinkJobCreateVO:
        source_text = request_data.normalized_source_text()
        if not source_text:
            raise AppException(code=1001, message="请粘贴抖音分享链接")

        from app.modules.guest.service import GuestService, is_guest
        if is_guest(self.db, user_id):
            from urllib.parse import urlsplit
            host = (urlsplit(_extract_url(source_text) or "").hostname or "").lower()
            if not any(host == domain or host.endswith("." + domain) for domain in ("douyin.com", "iesdouyin.com")):
                raise AppException(code=1001, message="免注册体验支持抖音分享链接，请粘贴正确链接")
        GuestService(self.db).gate_request(user_id, "IMPORT")

        job = MediaImportJob(
            job_id=self._generate_job_id(),
            user_id=user_id,
            source_text=source_text,
            source_url=_extract_url(source_text),
            status="INIT",
            progress=0,
            stage="INIT",
        )
        self.job_repo.add(job)
        self.db.commit()
        media_import_worker_queue.enqueue_job(job.job_id)
        return ImportLinkJobCreateVO(jobId=job.job_id, status=job.status)

    def get_job(self, user_id: int, job_id: str) -> ImportLinkJobStatusVO:
        job = self.job_repo.get_by_job_id(job_id, user_id=user_id)
        if job is None:
            raise AppException(code=4004, message="导入任务不存在或无权访问", status_code=404)

        file_record = self.file_repo.get(job.file_id) if job.file_id else None
        return self._to_status_vo(job, file_record)

    def _to_status_vo(self, job: MediaImportJob, file_record: FileRecord | None) -> ImportLinkJobStatusVO:
        file_vo = None
        if file_record is not None and file_record.deleted == 0:
            file_vo = ImportJobFileVO(
                fileNo=file_record.file_no,
                fileUrl=file_record.file_url,
                sourceFileName=file_record.source_file_name,
                fileType=file_record.file_type,
                fileSize=file_record.file_size,
                cookieSource=job.cookie_source,
                downloadEngine=job.download_engine,
            )
        return ImportLinkJobStatusVO(
            jobId=job.job_id,
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            file=file_vo,
            taskNo=job.task_no,
            errorMessage=job.error_message,
        )

    def _generate_job_id(self) -> str:
        for _ in range(10):
            job_id = generate_biz_no("IMP")
            if self.job_repo.get_by_job_id(job_id) is None:
                return job_id
        raise AppException(code=5000, message="导入任务编号生成失败，请稍后重试", status_code=500)


def _extract_url(source_text: str) -> str | None:
    match = re.search(r"https?://[^\s]+", source_text)
    if match is None:
        return None
    return match.group(0).strip(".,;!?，。；！）)]}>'\"")
