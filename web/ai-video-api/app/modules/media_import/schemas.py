from pydantic import BaseModel, Field


class ImportLinkJobCreateRequest(BaseModel):
    sourceText: str | None = Field(default=None, min_length=1, max_length=4000)
    sourceUrl: str | None = Field(default=None, min_length=1, max_length=1000)
    url: str | None = Field(default=None, min_length=1, max_length=1000)
    link: str | None = Field(default=None, min_length=1, max_length=1000)

    def normalized_source_text(self) -> str:
        value = self.sourceText or self.sourceUrl or self.url or self.link
        return (value or "").strip()


class ImportLinkJobCreateVO(BaseModel):
    jobId: str
    status: str


class ImportJobFileVO(BaseModel):
    fileNo: str
    fileUrl: str
    sourceFileName: str
    fileType: str
    fileSize: int
    cookieSource: str | None = None
    downloadEngine: str | None = None


class ImportLinkJobStatusVO(BaseModel):
    jobId: str
    status: str
    progress: int
    stage: str | None = None
    file: ImportJobFileVO | None = None
    taskNo: str | None = None
    errorMessage: str | None = None
