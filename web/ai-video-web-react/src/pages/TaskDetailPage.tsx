import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Clipboard, Download, RefreshCw, Trash2 } from "lucide-react";

import { Badge, Button, Card, EmptyState, LoadingSkeleton, Modal, useToast } from "../components/ui";
import { patchTaskCache, removeTaskCache } from "../lib/task-cache";
import { queryClient } from "../lib/query-client";
import { createTaskDownloadTicket, deleteTask, getTaskResult, getTasks } from "../services/tasks";
import { useAuthStore } from "../store/auth-store";
import { buildAgentPrompt } from "../lib/agent-prompt";
import { refreshBillingCache } from "../lib/billing-cache";

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
    PROCESSING: "正在生成",
    SUCCESS: "已完成",
    FAIL: "未完成",
  };
  return map[status] ?? status;
}

function isRunning(status?: string) {
  return status === "INIT" || status === "PROCESSING";
}

function friendlyStage(status?: string, progress = 0) {
  if (status === "INIT") return "正在排队，很快开始处理";
  if (status === "PROCESSING") {
    if (progress < 35) return "正在准备素材";
    if (progress < 75) return "正在识别声音内容";
    return "正在整理文字稿";
  }
  if (status === "SUCCESS") return "文字稿已生成";
  if (status === "FAIL") return "没有成功生成文字稿";
  return "等待更新";
}

function formatDownloadExpiry(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function TaskDetailPage() {
  const { taskNo = "" } = useParams();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const userId = useAuthStore((state) => state.user?.userId);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: (result) => {
      removeTaskCache(queryClient, result.taskNo);
      setDeleteConfirmOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["tasks"], refetchType: "active" });
      showToast({ tone: "success", title: "已删除记录", description: "这条处理记录已从列表中移除。" });
      navigate("/tasks", { replace: true });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "删除失败", description: error.message });
    },
  });

  const taskQuery = useQuery({
    queryKey: ["tasks", "detail", userId, taskNo],
    queryFn: () => getTaskResult(taskNo),
    enabled: Boolean(userId && taskNo),
    placeholderData: (previousData) => previousData,
    refetchInterval: (query) => (isRunning(query.state.data?.status) ? 1800 : false),
  });

  const task = taskQuery.data;
  useEffect(() => {
    if (task?.status === "SUCCESS" || task?.status === "FAIL") void refreshBillingCache();
  }, [task?.status, task?.taskNo]);
  const titleLookupQuery = useQuery({
    queryKey: ["tasks", "title", userId, taskNo],
    queryFn: () => getTasks({ keyword: taskNo, pageNo: 1, pageSize: 20 }),
    enabled: Boolean(userId && taskNo && task && task.status !== "INIT" && !task.sourceFileName?.trim()),
    staleTime: 60_000,
  });
  const titleFromList = titleLookupQuery.data?.records.find((item) => item.taskNo === taskNo)?.sourceFileName?.trim();
  const progress = Math.max(0, Math.min(task?.progress ?? 0, 100));
  const rawText = task?.rawText?.trim() ?? "";
  const taskTitle = task?.status === "INIT" ? task.taskNo : task?.sourceFileName?.trim() || titleFromList || task?.taskNo;
  const sourceDownloadExpiry = formatDownloadExpiry(task?.sourceDownloadExpiresAt);
  const sourceDownloadMutation = useMutation({
    mutationFn: () => createTaskDownloadTicket(taskNo),
    onSuccess: (ticket) => {
      const anchor = document.createElement("a");
      anchor.href = ticket.url;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      showToast({ tone: "success", title: "视频已开始下载", description: "请在浏览器下载记录中查看。" });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "视频下载失败", description: error.message });
      void taskQuery.refetch();
    },
  });

  useEffect(() => {
    if (!task) return;
    patchTaskCache(queryClient, {
      taskNo: task.taskNo,
      sourceFileName: task.sourceFileName,
      status: task.status,
      stage: task.stage,
      progress: task.progress,
      rawText: task.rawText,
      errorMsg: task.errorMsg,
      durationSeconds: task.durationSeconds,
      estimatedPoints: task.estimatedPoints,
    });
  }, [task]);

  async function handleCopy(forAgent = false) {
    if (!rawText) {
      showToast({ tone: "warning", title: "还没有可复制的文字", description: "文字稿生成后就可以复制。" });
      return;
    }
    try {
      await navigator.clipboard.writeText(forAgent ? buildAgentPrompt(rawText, taskTitle) : rawText);
      showToast({ tone: "success", title: forAgent ? "已复制给 Agent" : "已复制", description: forAgent ? "已包含整理提示词与原始转写稿，可粘贴给 Agent。" : "文字内容已放入剪贴板。" });
    } catch {
      showToast({ tone: "error", title: "复制失败", description: "请允许浏览器访问剪贴板后重试。" });
    }
  }

  function handleDelete() {
    if (!taskNo) return;
    setDeleteConfirmOpen(true);
  }

  function confirmDelete() {
    if (!taskNo) return;
    deleteMutation.mutate(taskNo);
  }

  return (
    <div className="page-stack">
      <div className="detail-topbar">
        <Link className="text-link detail-back" to="/tasks">
          <ArrowLeft size={16} />
          返回处理记录
        </Link>
        <div className="detail-topbar__actions">
          {task?.sourceDownloadAvailable ? (
            <Button
              type="button"
              variant="secondary"
              icon={<Download size={16} />}
              loading={sourceDownloadMutation.isPending}
              onClick={() => sourceDownloadMutation.mutate()}
            >
              下载原视频
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            icon={<RefreshCw size={16} />}
            loading={taskQuery.isFetching && Boolean(task)}
            onClick={() => void taskQuery.refetch()}
          >
            刷新进度
          </Button>
          <Button
            type="button"
            variant="danger"
            icon={<Trash2 size={16} />}
            loading={deleteMutation.isPending}
            onClick={handleDelete}
          >
            删除记录
          </Button>
        </div>
      </div>

      {taskQuery.isFetching && !task ? (
        <Card>
          <LoadingSkeleton lines={8} />
        </Card>
      ) : task ? (
        <>
          <section className="task-detail-hero">
            <div>
              <Badge tone={statusTone(task.status)}>{statusLabel(task.status)}</Badge>
              <h1>{taskTitle}</h1>
              <p>{friendlyStage(task.status, progress)}</p>
              <p className="muted-text">处理编号 {task.taskNo}</p>
              {task.sourceDownloadAvailable ? (
                <p className="source-download-hint">
                  原视频临时保留 1 小时{sourceDownloadExpiry ? `，${sourceDownloadExpiry} 前可下载` : ""}
                </p>
              ) : null}
            </div>
            <div className="task-detail-progress">
              <strong>{progress}%</strong>
              <div className="progress-track">
                <span style={{ width: `${progress}%` }} />
              </div>
            </div>
          </section>

          <Card
            title="提取出的文字"
            eyebrow="文字稿"
            action={
              <div className="detail-topbar__actions"><Button type="button" variant="secondary" icon={<Clipboard size={16} />} onClick={() => void handleCopy()} disabled={!rawText}>
                复制文字
              </Button><Button type="button" onClick={() => void handleCopy(true)} disabled={!rawText}>一键复制给 Agent</Button></div>
            }
          >
            {rawText ? (
              <article className="raw-text-panel">{rawText}</article>
            ) : task.errorMsg ? (
              <EmptyState title="没有生成成功" description={task.errorMsg} />
            ) : (
              <EmptyState title="文字稿正在生成" description="完成后，这里会显示完整文字内容。" />
            )}
          </Card>
        </>
      ) : (
        <EmptyState title="没有找到这条记录" description="请返回处理记录重新选择。" />
      )}

      <Modal
        open={deleteConfirmOpen}
        title="删除这条处理记录？"
        onClose={() => {
          if (!deleteMutation.isPending) setDeleteConfirmOpen(false);
        }}
        footer={
          <>
            <Button type="button" variant="ghost" disabled={deleteMutation.isPending} onClick={() => setDeleteConfirmOpen(false)}>
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
            <strong>{task?.taskNo ?? taskNo}</strong>
          </div>
          <p className="muted-text">这是软删除，不会影响后台数据留痕。</p>
        </div>
      </Modal>
    </div>
  );
}
