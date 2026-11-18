from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.common.ids import generate_biz_no
from app.common.media import probe_duration_seconds
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.file import FileRecord
from app.repositories.file import FileRecordRepository
from app.modules.file.schemas import FileUploadVO

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


class FileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.file_repo = FileRecordRepository(db)

    def upload_file(self, user_id: int, upload_file: UploadFile, duration_seconds: int | None) -> FileUploadVO:
        from app.modules.guest.service import GuestService
        service = GuestService(self.db)
        lease = service.gate_request(user_id, "UPLOAD")
        limit = service.policy()["upload_mb"] * 1024 * 1024 if lease else None
        try:
            return self._upload_file(user_id, upload_file, duration_seconds, limit)
        finally:
            self.db.rollback()
            service.release_upload(user_id, lease)

    def _upload_file(self, user_id: int, upload_file: UploadFile, duration_seconds: int | None, limit=None) -> FileUploadVO:
        source_name = Path(upload_file.filename or "upload.bin").name
        suffix = Path(source_name).suffix.lower()
        file_type = self._resolve_file_type(suffix, upload_file.content_type)
        file_no = self._generate_file_no()
        storage_name = f"{file_no}{suffix or '.bin'}"
        relative_dir = Path(get_settings().upload_subdir) / datetime.now().strftime("%Y%m%d")
        relative_path = relative_dir / storage_name
        absolute_path = Path(get_settings().storage_root) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        file_size = self._save_upload(upload_file, absolute_path, limit)
        probed_duration_seconds = probe_duration_seconds(absolute_path)
        file_record = FileRecord(
            file_no=file_no,
            user_id=user_id,
            source_file_name=source_name,
            storage_file_name=storage_name,
            file_type=file_type,
            content_type=upload_file.content_type,
            file_size=file_size,
            file_url=relative_path.as_posix(),
            duration_seconds=probed_duration_seconds,
            status="UPLOADED",
        )
        self.file_repo.add(file_record)
        self.db.commit()
        return self._to_vo(file_record)

    def _save_upload(self, upload_file: UploadFile, absolute_path: Path, limit=None) -> int:
        max_size = min(limit, get_settings().max_upload_size_bytes) if limit else get_settings().max_upload_size_bytes
        total = 0
        with absolute_path.open("wb") as target:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    target.close()
                    absolute_path.unlink(missing_ok=True)
                    raise AppException(code=1001, message="文件过大，请压缩后再上传")
                target.write(chunk)
        return total

    def _resolve_file_type(self, suffix: str, content_type: str | None) -> str:
        if suffix in VIDEO_EXTENSIONS or (content_type or "").startswith("video/"):
            return "VIDEO"
        if suffix in AUDIO_EXTENSIONS or (content_type or "").startswith("audio/"):
            return "AUDIO"
        raise AppException(code=1001, message="暂不支持该文件格式，请上传常见音频或视频文件")

    def _generate_file_no(self) -> str:
        for _ in range(10):
            file_no = generate_biz_no("FILE")
            if self.file_repo.get_by_file_no(file_no) is None:
                return file_no
        raise AppException(code=5000, message="文件编号生成失败，请稍后重试", status_code=500)

    def _to_vo(self, file_record: FileRecord) -> FileUploadVO:
        return FileUploadVO(
            fileNo=file_record.file_no,
            fileUrl=file_record.file_url,
            sourceFileName=file_record.source_file_name,
            fileType=file_record.file_type,
            fileSize=file_record.file_size,
        )
