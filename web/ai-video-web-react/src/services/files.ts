import { api } from "../lib/api-client";
import type { FileUploadResult, ImportJobCreateResult, ImportJobStatus } from "../types/api";

export function uploadFile(file: File, durationSeconds?: number) {
  const formData = new FormData();
  formData.append("file", file);
  if (durationSeconds !== undefined) {
    formData.append("durationSeconds", String(durationSeconds));
  }
  return api.post<FileUploadResult>("/file/upload", formData);
}

export function createImportJob(sourceText: string) {
  return api.post<ImportJobCreateResult>("/file/import-link/jobs", { sourceText });
}

export function getImportJob(jobId: string) {
  return api.get<ImportJobStatus>(`/file/import-link/jobs/${jobId}`);
}
