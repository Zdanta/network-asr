import { FormEvent, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight, RefreshCw, Search, Trash2 } from "lucide-react";

import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, Modal, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { removeTaskCache } from "../lib/task-cache";
import { deleteTask, getTasks } from "../services/tasks";
import { useAuthStore } from "../store/auth-store";
import type { TaskListItem } from "../types/api";
import { refreshBillingCache } from "../lib/billing-cache";

const statusOptions = [
  { label: "全部", value: "ALL" },
  { label: "处理中", value: "PROCESSING" },
  { label: "已完成", value: "SUCCESS" },
  { label: "未完成", value: "FAIL" },
];

const EMPTY_TASKS: TaskListItem[] = [];

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS") return "success";
  if (status === "FAIL") return "danger";
  if (status === "PROCESSING") return "warning";
  if (status === "INIT") return "info";
  return "neutral";
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    INIT: "等待处理",
    PROCESSING: "正在提取",
    SUCCESS: "已完成",
    FAIL: "未完成",
  };
  return map[status] ?? status;
}

function isRunning(task: TaskListItem) {
  return task.status === "INIT" || task.status === "PROCESSING";
}

function formatDate(value?: string | null) {
  if (!value) return "刚刚提交";
  return new Date(value).toLocaleString();
}

function friendlyStage(task: TaskListItem) {
  if (task.status === "INIT") return "正在排队，很快开始处理";
  if (task.status === "PROCESSING") {
    if ((task.progress ?? 0) < 35) return "正在准备素材";
    if ((task.progress ?? 0) < 75) return "正在识别声音内容";
    return "正在整理文字稿";
  }
  if (task.status === "SUCCESS") return "文字稿已生成";
  if (task.status === "FAIL") return "没有成功生成文字稿";
  return "等待更新";
}

function TaskCard({
  task,
  refreshing,
  deleting,
  onDelete,
}: {
  task: TaskListItem;
  refreshing: boolean;
  deleting: boolean;
  onDelete: (taskNo: string) => void;
}) {
  const progress = Math.max(0, Math.min(task.progress ?? 0, 100));
  const title = task.sourceFileName?.trim() || task.taskNo;

  return (
    <article className="task-card task-card--interactive">
      <div className="task-card__head">
        <div>
          <Badge tone={statusTone(task.status)}>{statusLabel(task.status)}</Badge>
          <h3>{title}</h3>
          <p>{formatDate(task.createdAt)}</p>
        </div>
        <div className="task-card__actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            icon={<Trash2 size={15} />}
            loading={deleting}
            onClick={() => onDelete(task.taskNo)}
          >
            删除
          </Button>
          <Link className="task-card__open" to={`/tasks/${task.taskNo}`} aria-label={`打开处理记录 ${task.taskNo}`}>
            <ArrowUpRight size={18} />
          </Link>
        </div>
      </div>

      <div className="progress-track" aria-label={`处理进度 ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>

      <footer>
        <span>{friendlyStage(task)}</span>
        <strong>{progress}%</strong>
      </footer>

      <div className="task-card__meta">
        <span>处理编号 {task.taskNo}</span>
        {task.estimatedPoints ? <span>预计消耗 {task.estimatedPoints} 点</span> : <span>正在估算消耗</span>}
      </div>

      {task.errorMsg ? <p className="error-text">{task.errorMsg}</p> : null}
      {refreshing && isRunning(task) ? <span className="task-card__pulse">正在更新这条记录</span> : null}
    </article>
  );
}

export function TasksPage() {
  const [status, setStatus] = useState("ALL");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [pendingDeleteTaskNo, setPendingDeleteTaskNo] = useState<string | null>(null);
  const deferredKeyword = useDeferredValue(keyword);
  const userId = useAuthStore((state) => state.user?.userId);
  const { showToast } = useToast();

  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: (result) => {
      removeTaskCache(queryClient, result.taskNo);
      setPendingDeleteTaskNo(null);
      void queryClient.invalidateQueries({ queryKey: ["tasks"], refetchType: "active" });
      showToast({ tone: "success", title: "已删除记录", description: "这条处理记录已从列表中移除。" });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "删除失败", description: error.message });
    },
  });

  const tasksQuery = useQuery({
    queryKey: ["tasks", "list", userId, { status, keyword: deferredKeyword, pageNo: 1, pageSize: 20 }],
    queryFn: () => getTasks({ status, keyword: deferredKeyword, pageNo: 1, pageSize: 20 }),
    enabled: Boolean(userId),
    placeholderData: (previousData) => previousData,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.records.some(isRunning) ? 2200 : false;
    },
  });

  const tasks = tasksQuery.data?.records ?? EMPTY_TASKS;
  const finishedTasks = tasks.filter((task) => task.status === "SUCCESS" || task.status === "FAIL")
    .map((task) => `${task.taskNo}:${task.status}`).join(",");
  useEffect(() => {
    if (finishedTasks) void refreshBillingCache();
  }, [finishedTasks]);
  const pendingDeleteTask = tasks.find((task) => task.taskNo === pendingDeleteTaskNo);
  const isInitialLoading = tasksQuery.isFetching && !tasksQuery.data;
  const isSoftRefreshing = tasksQuery.isFetching && Boolean(tasksQuery.data);

  const counters = useMemo(() => {
    return {
      total: tasksQuery.data?.total ?? tasks.length,
      running: tasks.filter(isRunning).length,
      done: tasks.filter((task) => task.status === "SUCCESS").length,
    };
  }, [tasks, tasksQuery.data?.total]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setKeyword(keywordInput.trim());
  }

  function handleDelete(taskNo: string) {
    setPendingDeleteTaskNo(taskNo);
  }

  function confirmDelete() {
    if (!pendingDeleteTaskNo) return;
    deleteMutation.mutate(pendingDeleteTaskNo);
  }

  return (
    <div className="page-stack">
      <div className="page-heading tasks-heading">
        <div>
          <p className="eyebrow">我的文稿</p>
          <h1>处理记录</h1>
          <p>查看每个素材的处理进度。完成后可以进入详情复制完整文字稿。</p>
        </div>
        <Button
          type="button"
          variant="ghost"
          icon={<RefreshCw size={16} />}
          loading={isSoftRefreshing}
          onClick={() => void tasksQuery.refetch()}
        >
          刷新状态
        </Button>
      </div>

      <section className="task-control-panel">
        <Card className="task-stat-card">
          <span>全部记录</span>
          <strong>{counters.total}</strong>
        </Card>
        <Card className="task-stat-card task-stat-card--active">
          <span>处理中</span>
          <strong>{counters.running}</strong>
        </Card>
        <Card className="task-stat-card">
          <span>已完成</span>
          <strong>{counters.done}</strong>
        </Card>
      </section>

      <Card>
        <div className="tasks-toolbar">
          <div className="status-tabs" role="tablist" aria-label="处理状态筛选">
            {statusOptions.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={status === option.value ? "secondary" : "ghost"}
                onClick={() => setStatus(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <form className="task-search" onSubmit={handleSearch}>
            <Input
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              placeholder="搜索文件名或处理编号"
              leftIcon={<Search size={16} />}
            />
            <Button type="submit" variant="secondary">
              搜索
            </Button>
          </form>
        </div>
      </Card>

      {isInitialLoading ? (
        <Card>
          <LoadingSkeleton lines={6} />
        </Card>
      ) : tasks.length > 0 ? (
        <div className="task-card-grid">
          {tasks.map((task) => (
            <TaskCard
              key={task.taskNo}
              task={task}
              refreshing={isSoftRefreshing}
              deleting={deleteMutation.isPending && deleteMutation.variables === task.taskNo}
              onDelete={handleDelete}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="还没有处理记录" description="上传文件或粘贴抖音链接后，进度会显示在这里。" />
      )}

      <Modal
        open={Boolean(pendingDeleteTaskNo)}
        title="删除这条处理记录？"
        onClose={() => {
          if (!deleteMutation.isPending) setPendingDeleteTaskNo(null);
        }}
        footer={
          <>
            <Button type="button" variant="ghost" disabled={deleteMutation.isPending} onClick={() => setPendingDeleteTaskNo(null)}>
              先保留
            </Button>
            <Button type="button" variant="danger" loading={deleteMutation.isPending} onClick={confirmDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <div className="confirm-dialog-copy">
          <p>删除后，这条记录不会再出现在你的处理记录列表中。</p>
          <div className="confirm-dialog__target">
            <span>处理编号</span>
            <strong>{pendingDeleteTask?.taskNo ?? pendingDeleteTaskNo}</strong>
          </div>
          <p className="muted-text">这是软删除，不会影响已经生成的文字内容和后台数据留痕。</p>
        </div>
      </Modal>
    </div>
  );
}
