import { api } from "../lib/api-client";
import type { SourceDownloadTicket, TaskCreateResult, TaskDeleteResult, TaskListItem, TaskPageResult, TaskResult, TaskStatusResult } from "../types/api";

export type TaskListParams = {
  status?: string;
  keyword?: string;
  pageNo?: number;
  pageSize?: number;
};

function buildTaskQuery(params: TaskListParams = {}) {
  const search = new URLSearchParams();
  if (params.status && params.status !== "ALL") search.set("status", params.status);
  if (params.keyword?.trim()) search.set("keyword", params.keyword.trim());
  search.set("pageNo", String(params.pageNo ?? 1));
  search.set("pageSize", String(params.pageSize ?? 20));
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function getRecentTasks() {
  return api.get<TaskListItem[]>("/task/recent");
}

export function getTasks(params: TaskListParams = {}) {
  return api.get<TaskPageResult>(`/task${buildTaskQuery(params)}`);
}

export function getTaskStatus(taskNo: string) {
  return api.get<TaskStatusResult>(`/task/${taskNo}`);
}

export function getTaskResult(taskNo: string) {
  return api.get<TaskResult>(`/task/${taskNo}/result`);
}

export function createTask(fileNo: string) {
  return api.post<TaskCreateResult>("/task", { fileNo });
}

export function deleteTask(taskNo: string) {
  return api.delete<TaskDeleteResult>(`/task/${taskNo}`);
}

export function createTaskDownloadTicket(taskNo: string) {
  return api.post<SourceDownloadTicket>(`/task/${taskNo}/source-download-ticket`);
}
