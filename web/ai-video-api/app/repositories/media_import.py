from sqlalchemy import select

from app.models.media_import import MediaImportJob
from app.repositories.base import BaseRepository


class MediaImportJobRepository(BaseRepository[MediaImportJob]):
    model = MediaImportJob

    def get_by_job_id(self, job_id: str, user_id: int | None = None) -> MediaImportJob | None:
        statement = select(MediaImportJob).where(MediaImportJob.job_id == job_id, MediaImportJob.deleted == 0)
        if user_id is not None:
            statement = statement.where(MediaImportJob.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()
