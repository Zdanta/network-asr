import mimetypes
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.common.ids import generate_biz_no
from app.common.media import probe_duration_seconds
from app.common.pagination import PageParams
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.security import create_download_ticket
from app.models.file import FileRecord
from app.models.task import Task
from app.modules.quota.service import QuotaService
from app.modules.task.schemas import (
    SourceDownloadTicketVO,
    TaskCreateRequest,
    TaskCreateVO,
    TaskDeleteVO,
    TaskListItemVO,
    TaskPageVO,
    TaskResultVO,
    TaskStatusVO,
)
from app.repositories.file import FileRecordRepository
from app.repositories.task import TaskRepository
from app.workers.task_queue import task_worker_queue
from app.workers.media_cleanup import import_download_expires_at, resolve_storage_path


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.task_repo = TaskRepository(db)
        self.file_repo = FileRecordRepository(db)
        self.quota_service = QuotaService(db)

    def create_task(
        self,
        user_id: int,
        request_data: TaskCreateRequest,
    ) -> TaskCreateVO:
        file_record = self.file_repo.get_by_file_no(request_data.fileNo, user_id=user_id)
        if file_record is None:
            raise AppException(code=4004, message="文件不存在或无权访问", status_code=404)

        task = self.create_task_for_file(user_id, file_record)
        self.db.commit()
        task_worker_queue.enqueue_task(task.task_no)
        return TaskCreateVO(taskNo=task.task_no)

    def create_task_for_file(self, user_id: int, file_record: FileRecord) -> Task:
        if file_record.user_id != user_id:
            raise AppException(code=4004, message="文件不存在或无权访问", status_code=404)
        from app.modules.guest.service import GuestService, is_guest
        if is_guest(self.db, user_id):
            existing_task = self.db.scalar(select(Task).where(Task.user_id == user_id, Task.file_id == file_record.id,
                Task.deleted == 0).order_by(Task.id.desc()))
            if existing_task:
                return existing_task
        if get_settings().opcpay_enabled:
            from app.models.opcpay import OpcpayOperation
            existing = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "CONSUME",
                OpcpayOperation.user_id == user_id, OpcpayOperation.action_id == file_record.file_no))
            if existing:
                return self.task_repo.get_by_task_no(existing.biz_no, user_id=user_id)
        duration_seconds = self._ensure_file_duration(file_record)
        estimated_points = self.quota_service.estimate_points(duration_seconds)
        next_task_no = self._generate_task_no()
        GuestService(self.db).reserve(user_id, next_task_no, estimated_points, allow_import=file_record.remark == "import-link")
        self.quota_service.ensure_has_points(user_id, estimated_points)
        product = None
        if get_settings().opcpay_enabled:
            from app.modules.payment.opcpay_client import OpcpayClient
            local = self.quota_service.get_or_init_quota(user_id)
            if (local.remaining_points or 0) >= estimated_points:
                product = {"quota_unit": "POINT", "source": "LOCAL"}
            else:
                self.db.commit()
                _, product = OpcpayClient().product()
        task = Task(
            task_no=next_task_no,
            user_id=user_id,
            file_id=file_record.id,
            file_url=file_record.file_url,
            status="INIT",
            progress=0,
            ai_text=None,
            more_versions_json=None,
        )
        if get_settings().opcpay_enabled:
            import json
            from app.models.opcpay import OpcpayOperation
            unit = product["quota_unit"]
            body = {"user_id": str(user_id), "idempotency_key": task.task_no,
                    "amount": 1 if unit == "COUNT" else estimated_points, "reason": "音视频转写"}
            try:
                with self.db.begin_nested():
                    self.task_repo.add(task)
                    self.db.add(OpcpayOperation(kind="CONSUME", user_id=user_id, action_id=file_record.file_no,
                        biz_no=task.task_no, request_json=json.dumps({"body": body, "unit": unit,
                            "source": product.get("source", "OPCPAY")}), state="PENDING"))
                    self.db.flush()
            except IntegrityError:
                existing = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "CONSUME",
                    OpcpayOperation.user_id == user_id, OpcpayOperation.action_id == file_record.file_no)
                    .with_for_update())
                if existing is None:
                    raise
                return self.task_repo.get_by_task_no(existing.biz_no, user_id=user_id)
        else:
            self.task_repo.add(task)
        return task

    def _ensure_file_duration(self, file_record: FileRecord) -> int:
        if file_record.duration_seconds and file_record.duration_seconds > 0:
            return file_record.duration_seconds

        absolute_path = Path(get_settings().storage_root) / file_record.file_url
        duration_seconds = probe_duration_seconds(absolute_path)
        if not duration_seconds:
            raise AppException(code=1001, message="暂时无法识别素材时长，请换一个文件再试")

        file_record.duration_seconds = duration_seconds
        self.db.flush()
        return duration_seconds

    def list_tasks(
        self,
        user_id: int,
        status: str | None,
        keyword: str | None,
        page_no: int,
        page_size: int,
    ) -> TaskPageVO:
        statement = (
            select(Task, FileRecord)
            .join(FileRecord, Task.file_id == FileRecord.id)
            .where(Task.user_id == user_id, Task.deleted == 0)
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        normalized_status = status.upper() if status else None
        if normalized_status and normalized_status != "ALL":
            if normalized_status in {"PROCESSING", "RUNNING"}:
                statement = statement.where(Task.status.in_(("INIT", "PROCESSING")))
            else:
                statement = statement.where(Task.status == normalized_status)
        if keyword:
            like = f"%{keyword}%"
            statement = statement.where(
                or_(
                    Task.task_no.like(like),
                    FileRecord.file_no.like(like),
                    FileRecord.source_file_name.like(like),
                )
            )

        page = self._paginate_task_file(statement, page_no, page_size)
        return page

    def list_recent_tasks(self, user_id: int, limit: int = 5) -> list[TaskListItemVO]:
        statement = (
            select(Task, FileRecord)
            .join(FileRecord, Task.file_id == FileRecord.id)
            .where(Task.user_id == user_id, Task.deleted == 0)
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(max(1, min(limit, 20)))
        )
        rows = self.db.execute(statement).all()
        return [self._to_list_item(task, file_record) for task, file_record in rows]

    def get_task_status(self, user_id: int, task_no: str) -> TaskStatusVO:
        task = self._get_user_task(user_id, task_no)
        file_record = self.file_repo.get(task.file_id)
        return self._to_status_vo(task, file_record)

    def get_task_result(self, user_id: int, task_no: str) -> TaskResultVO:
        task = self._get_user_task(user_id, task_no)
        file_record = self.file_repo.get(task.file_id)
        status_vo = self._to_status_vo(task, file_record)
        return TaskResultVO(
            **status_vo.model_dump(),
            rawText=task.raw_text,
            aiText=None,
            moreVersions=[],
        )

    def get_source_download(self, user_id: int, task_no: str) -> tuple[Path, str, str]:
        task = self._get_user_task(user_id, task_no)
        file_record = self.file_repo.get(task.file_id)
        if file_record is None or file_record.remark != "import-link":
            raise AppException(code=4004, message="该任务没有可下载的原视频", status_code=404)

        expires_at = import_download_expires_at(task)
        if datetime.now() >= expires_at or file_record.status == "EXPIRED":
            raise AppException(code=4100, message="原视频已超过一小时有效期", status_code=410)

        absolute_path = resolve_storage_path(file_record.file_url)
        if absolute_path is None or not absolute_path.is_file():
            raise AppException(code=4100, message="原视频已失效或已被清理", status_code=410)

        media_type = file_record.content_type or mimetypes.guess_type(file_record.source_file_name)[0] or "video/mp4"
        return absolute_path, file_record.source_file_name, media_type

    def create_source_download_ticket(self, user_id: int, task_no: str) -> SourceDownloadTicketVO:
        self.get_source_download(user_id, task_no)
        ticket, expires_at = create_download_ticket(user_id, task_no)
        return SourceDownloadTicketVO(
            url=f"/api/v1/task/{task_no}/source-download?ticket={ticket}",
            expiresAt=datetime.fromtimestamp(expires_at),
        )

    def delete_task(self, user_id: int, task_no: str) -> TaskDeleteVO:
        task = self._get_user_task(user_id, task_no)
        task.deleted = 1
        task.updated_by = user_id
        self.db.commit()
        return TaskDeleteVO(taskNo=task_no, deleted=True)

    def _get_user_task(self, user_id: int, task_no: str) -> Task:
        task = self.task_repo.get_by_task_no(task_no, user_id=user_id)
        if task is None:
            raise AppException(code=4004, message="处理记录不存在或无权访问", status_code=404)
        return task

    def _generate_task_no(self) -> str:
        for _ in range(10):
            task_no = generate_biz_no("TASK")
            if self.task_repo.get_by_task_no(task_no) is None:
                return task_no
        raise AppException(code=5000, message="处理编号生成失败，请稍后重试", status_code=500)

    def _paginate_task_file(self, statement, page_no: int, page_size: int) -> TaskPageVO:
        params = PageParams(page_no=page_no, page_size=page_size)
        total_count = self.db.execute(select(func.count()).select_from(statement.order_by(None).subquery())).scalar_one()
        rows = self.db.execute(statement.offset(params.offset).limit(params.page_size)).all()
        return TaskPageVO(
            pageNo=params.page_no,
            pageSize=params.page_size,
            total=total_count,
            hasMore=params.offset + len(rows) < total_count,
            records=[self._to_list_item(task, file_record) for task, file_record in rows],
        )

    def _to_list_item(self, task: Task, file_record: FileRecord | None) -> TaskListItemVO:
        return TaskListItemVO(
            taskNo=task.task_no,
            fileNo=file_record.file_no if file_record else None,
            sourceFileName=file_record.source_file_name if file_record else None,
            fileType=file_record.file_type if file_record else None,
            status=task.status,
            stage=self._task_stage(task),
            progress=task.progress,
            rawText=task.raw_text,
            errorMsg=task.error_msg,
            durationSeconds=file_record.duration_seconds if file_record else None,
            estimatedPoints=self.quota_service.estimate_points(file_record.duration_seconds if file_record else None),
            createdAt=task.created_at,
            finishTime=task.finish_time,
        )

    def _to_status_vo(self, task: Task, file_record: FileRecord | None) -> TaskStatusVO:
        seconds_per_point = self.quota_service.load_seconds_per_point()
        duration_seconds = file_record.duration_seconds if file_record else None
        download_expires_at = (
            import_download_expires_at(task)
            if file_record is not None and file_record.remark == "import-link"
            else None
        )
        download_path = resolve_storage_path(file_record.file_url) if download_expires_at and file_record else None
        download_available = bool(
            download_expires_at
            and datetime.now() < download_expires_at
            and file_record is not None
            and file_record.status != "EXPIRED"
            and download_path is not None
            and download_path.is_file()
        )
        return TaskStatusVO(
            taskNo=task.task_no,
            sourceFileName=file_record.source_file_name if file_record else None,
            status=task.status,
            stage=self._task_stage(task),
            progress=task.progress,
            errorMsg=task.error_msg,
            durationSeconds=duration_seconds,
            estimatedPoints=self.quota_service.estimate_points(duration_seconds),
            secondsPerPoint=seconds_per_point,
            pointsPerMinute=max(1, 60 // seconds_per_point) if seconds_per_point > 0 else 10,
            sourceDownloadAvailable=download_available,
            sourceDownloadExpiresAt=download_expires_at,
            sourceDownloadUrl=f"/api/v1/task/{task.task_no}/source-download" if download_available else None,
        )

    def _task_stage(self, task: Task) -> str | None:
        if task.status == "INIT":
            return "等待开始处理"
        if task.status == "PROCESSING":
            if task.progress < 35:
                return "提取音频"
            if task.progress < 75:
                return "正在识别声音内容"
            if task.progress < 100:
                return "保存转写结果"
            return "处理完成"
        if task.status == "SUCCESS":
            return "文字稿已生成"
        if task.status == "FAIL":
            return "转写失败"
        return None
