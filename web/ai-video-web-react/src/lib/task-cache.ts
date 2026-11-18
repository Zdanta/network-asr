import type { QueryClient } from "@tanstack/react-query";

import type { TaskListItem, TaskPageResult } from "../types/api";

function mergeTask(oldTask: TaskListItem, nextTask: Partial<TaskListItem> & { taskNo: string }): TaskListItem {
  return {
    ...oldTask,
    ...nextTask,
    progress: nextTask.progress ?? oldTask.progress ?? 0,
  };
}

function upsertArray(tasks: TaskListItem[] | undefined, task: TaskListItem): TaskListItem[] {
  const current = tasks ?? [];
  const exists = current.some((item) => item.taskNo === task.taskNo);
  if (!exists) return [task, ...current];
  return current.map((item) => (item.taskNo === task.taskNo ? mergeTask(item, task) : item));
}

function patchArray(tasks: TaskListItem[] | undefined, patch: Partial<TaskListItem> & { taskNo: string }) {
  if (!tasks) return tasks;
  return tasks.map((item) => (item.taskNo === patch.taskNo ? mergeTask(item, patch) : item));
}

function removeArray(tasks: TaskListItem[] | undefined, taskNo: string) {
  if (!tasks) return tasks;
  return tasks.filter((item) => item.taskNo !== taskNo);
}

function isTaskPage(data: unknown): data is TaskPageResult {
  return Boolean(data && typeof data === "object" && Array.isArray((data as TaskPageResult).records));
}

export function upsertTaskCache(queryClient: QueryClient, task: TaskListItem) {
  queryClient.setQueriesData<TaskListItem[]>({ queryKey: ["tasks", "recent"] }, (old) => upsertArray(old, task).slice(0, 20));
  queryClient.setQueriesData<TaskPageResult>({ queryKey: ["tasks", "list"] }, (old) => {
    if (!isTaskPage(old)) return old;
    const exists = old.records.some((item) => item.taskNo === task.taskNo);
    return {
      ...old,
      total: exists ? old.total : old.total + 1,
      records: upsertArray(old.records, task).slice(0, old.pageSize),
    };
  });
}

export function patchTaskCache(queryClient: QueryClient, patch: Partial<TaskListItem> & { taskNo: string }) {
  queryClient.setQueriesData<TaskListItem[]>({ queryKey: ["tasks", "recent"] }, (old) => patchArray(old, patch));
  queryClient.setQueriesData<TaskPageResult>({ queryKey: ["tasks", "list"] }, (old) => {
    if (!isTaskPage(old)) return old;
    return { ...old, records: patchArray(old.records, patch) ?? old.records };
  });
}

export function removeTaskCache(queryClient: QueryClient, taskNo: string) {
  queryClient.setQueriesData<TaskListItem[]>({ queryKey: ["tasks", "recent"] }, (old) => removeArray(old, taskNo));
  queryClient.setQueriesData<TaskPageResult>({ queryKey: ["tasks", "list"] }, (old) => {
    if (!isTaskPage(old)) return old;
    const exists = old.records.some((item) => item.taskNo === taskNo);
    return {
      ...old,
      total: exists ? Math.max(0, old.total - 1) : old.total,
      records: removeArray(old.records, taskNo) ?? old.records,
    };
  });
  queryClient.removeQueries({ queryKey: ["tasks", "detail"], exact: false });
}
