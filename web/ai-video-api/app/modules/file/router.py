from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user
from app.modules.file.schemas import FileUploadVO
from app.modules.file.service import FileService

router = APIRouter()


@router.post("/upload", response_model=ApiResponse[FileUploadVO])
def upload_file(
    file: UploadFile = File(...),
    duration_seconds: int | None = Form(default=None, alias="durationSeconds"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[FileUploadVO]:
    data = FileService(db).upload_file(current_user.id, file, duration_seconds)
    return success_response(data)
