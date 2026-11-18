from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user
from app.modules.media_import.schemas import (
    ImportLinkJobCreateRequest,
    ImportLinkJobCreateVO,
    ImportLinkJobStatusVO,
)
from app.modules.media_import.service import MediaImportService

router = APIRouter()


@router.post("/jobs", response_model=ApiResponse[ImportLinkJobCreateVO])
def create_import_link_job(
    request_data: ImportLinkJobCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ImportLinkJobCreateVO]:
    data = MediaImportService(db).create_job(current_user.id, request_data)
    return success_response(data)


@router.get("/jobs/{job_id}", response_model=ApiResponse[ImportLinkJobStatusVO])
def get_import_link_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ImportLinkJobStatusVO]:
    data = MediaImportService(db).get_job(current_user.id, job_id)
    return success_response(data)
