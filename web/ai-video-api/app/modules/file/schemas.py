from pydantic import BaseModel


class FileUploadVO(BaseModel):
    fileNo: str
    fileUrl: str
    sourceFileName: str
    fileType: str
    fileSize: int
    cookieSource: str | None = None
    downloadEngine: str | None = None
