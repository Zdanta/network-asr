from app.common.clock import utc_naive_now
from datetime import datetime
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.guest import GuestIdentity
from app.models.user import User
from app.models.file import FileRecord
from app.models.task import Task
from app.models.media_import import MediaImportJob
from app.modules.guest.service import GuestService


def cleanup_expired_guests():
    # Keep hashed claim and billing records to prevent re-claiming; clear expired unregistered media/text.
    from app.workers.media_cleanup import resolve_storage_path
    with get_session_factory()() as db:
        ids = list(db.scalars(select(GuestIdentity.user_id).where(GuestIdentity.state == "GUEST",
            GuestIdentity.expires_at < utc_naive_now()).limit(50)))
        for uid in ids:
            service = GuestService(db)
            service.lock()
            identity = db.scalar(select(GuestIdentity).where(GuestIdentity.user_id == uid).with_for_update()
                                 .execution_options(populate_existing=True))
            if identity.state != "GUEST" or identity.expires_at >= utc_naive_now():
                db.rollback()
                continue
            active = db.scalar(select(Task.id).where(Task.user_id == uid, Task.status.in_(["INIT", "PROCESSING"])).with_for_update())
            imported = db.scalar(select(MediaImportJob.id).where(MediaImportJob.user_id == uid,
                MediaImportJob.status.in_(["INIT", "PROCESSING"])).with_for_update())
            if active or imported or (identity.upload_until and identity.upload_until > utc_naive_now()):
                db.rollback()
                continue
            for file in db.scalars(select(FileRecord).where(FileRecord.user_id == uid)):
                path = resolve_storage_path(file.file_url)
                if path:
                    path.unlink(missing_ok=True)
                file.status = "EXPIRED"
            for task in db.scalars(select(Task).where(Task.user_id == uid)):
                if task.audio_url:
                    path = resolve_storage_path(task.audio_url)
                    if path:
                        path.unlink(missing_ok=True)
                task.raw_text, task.ai_text, task.more_versions_json, task.deleted = None, None, None, 1
            identity.state = "EXPIRED"
            db.get(User, uid).status = "DISABLE"
            db.commit()
