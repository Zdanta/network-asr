from sqlalchemy import select

from app.models.file import FileRecord
from app.repositories.base import BaseRepository


class FileRecordRepository(BaseRepository[FileRecord]):
    model = FileRecord

    def get_by_file_no(self, file_no: str, user_id: int | None = None) -> FileRecord | None:
        statement = select(FileRecord).where(FileRecord.file_no == file_no, FileRecord.deleted == 0)
        if user_id is not None:
            statement = statement.where(FileRecord.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()
