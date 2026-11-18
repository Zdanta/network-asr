from datetime import datetime

from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    fileNo: str
    importJobId: str | None = None


class TaskCreateVO(BaseModel):
    taskNo: str


class TaskDeleteVO(BaseModel):
    taskNo: str
    deleted: bool


class SourceDownloadTicketVO(BaseModel):
    url: str
    expiresAt: datetime


class TaskStatusVO(BaseModel):
    taskNo: str
    sourceFileName: str | None = None
    status: str
    stage: str | None = None
    progress: int
    errorMsg: str | None = None
    durationSeconds: int | None = None
    estimatedPoints: int
    secondsPerPoint: int
    pointsPerMinute: int
    sourceDownloadAvailable: bool = False
    sourceDownloadExpiresAt: datetime | None = None
    sourceDownloadUrl: str | None = None


class TaskResultVO(TaskStatusVO):
    rawText: str | None = None
    aiText: str | None = None
    moreVersions: list[str] = []


class TaskListItemVO(BaseModel):
    taskNo: str
    fileNo: str | None = None
    sourceFileName: str | None = None
    fileType: str | None = None
    status: str
    stage: str | None = None
    progress: int
    rawText: str | None = None
    errorMsg: str | None = None
    durationSeconds: int | None = None
    estimatedPoints: int
    createdAt: datetime | None = None
    finishTime: datetime | None = None


class TaskPageVO(BaseModel):
    pageNo: int
    pageSize: int
    total: int
    hasMore: bool
    records: list[TaskListItemVO]
