from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user, parse_download_ticket
from app.modules.task.schemas import SourceDownloadTicketVO, TaskCreateRequest, TaskCreateVO, TaskDeleteVO, TaskListItemVO, TaskPageVO, TaskResultVO, TaskStatusVO
from app.modules.task.service import TaskService

router = APIRouter()


@router.post("", response_model=ApiResponse[TaskCreateVO])
def create_task(
    request_data: TaskCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskCreateVO]:
    data = TaskService(db).create_task(current_user.id, request_data)
    return success_response(data)


@router.get("", response_model=ApiResponse[TaskPageVO])
def list_tasks(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page_no: int = Query(default=1, ge=1, alias="pageNo"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskPageVO]:
    data = TaskService(db).list_tasks(current_user.id, status, keyword, page_no, page_size)
    return success_response(data)


@router.get("/recent", response_model=ApiResponse[list[TaskListItemVO]])
def list_recent_tasks(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[TaskListItemVO]]:
    data = TaskService(db).list_recent_tasks(current_user.id, limit)
    return success_response(data)


@router.get("/{task_no}", response_model=ApiResponse[TaskStatusVO])
def get_task_status(
    task_no: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskStatusVO]:
    data = TaskService(db).get_task_status(current_user.id, task_no)
    return success_response(data)


@router.get("/{task_no}/result", response_model=ApiResponse[TaskResultVO])
def get_task_result(
    task_no: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskResultVO]:
    data = TaskService(db).get_task_result(current_user.id, task_no)
    return success_response(data)


@router.post("/{task_no}/source-download-ticket", response_model=ApiResponse[SourceDownloadTicketVO])
def create_task_source_download_ticket(
    task_no: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[SourceDownloadTicketVO]:
    data = TaskService(db).create_source_download_ticket(current_user.id, task_no)
    return success_response(data)


@router.get("/{task_no}/source-download", response_class=FileResponse)
def download_task_source(
    task_no: str,
    ticket: str = Query(...),
    db: Session = Depends(get_db),
) -> FileResponse:
    user_id, ticket_task_no = parse_download_ticket(ticket)
    if ticket_task_no != task_no:
        raise AppException(code=1003, message="下载链接与任务不匹配", status_code=403)
    path, filename, media_type = TaskService(db).get_source_download(user_id, task_no)
    return FileResponse(
        path=path,
        filename=filename,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/{task_no}", response_model=ApiResponse[TaskDeleteVO])
def delete_task(
    task_no: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskDeleteVO]:
    data = TaskService(db).delete_task(current_user.id, task_no)
    return success_response(data)
