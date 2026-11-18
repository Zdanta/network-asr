import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Gift, Link2, UploadCloud } from "lucide-react";

import { Badge, Button, Card, EmptyState, LoadingSkeleton } from "../components/ui";
import { getQuota } from "../services/quota";
import { getRecentTasks } from "../services/tasks";
import { useAuthStore } from "../store/auth-store";
import type { TaskListItem } from "../types/api";

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS") return "success";
  if (status === "FAIL") return "danger";
  if (status === "PROCESSING") return "warning";
  if (status === "INIT") return "info";
  return "neutral";
}

function statusText(status: string) {
  const map: Record<string, string> = {
    INIT: "等待处理",
    PROCESSING: "正在提取",
    SUCCESS: "已完成",
    FAIL: "未完成",
  };
  return map[status] ?? status;
}

function TaskRow({ task }: { task: TaskListItem }) {
  return (
    <Link className="task-row task-row--link" to={`/tasks/${task.taskNo}`}>
      <div>
        <strong>{task.sourceFileName?.trim() || task.taskNo}</strong>
        <span>{task.createdAt ? new Date(task.createdAt).toLocaleString() : "刚刚提交"}</span>
      </div>
      <div className="task-row__meta">
        <span>{task.progress}%</span>
        <Badge tone={statusTone(task.status)}>{statusText(task.status)}</Badge>
        <span className="task-row__open" aria-hidden="true">
          <ArrowUpRight size={16} />
        </span>
      </div>
    </Link>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const userId = user?.userId;
  const quotaQuery = useQuery({ queryKey: ["quota"], queryFn: getQuota });
  const recentTasksQuery = useQuery({ queryKey: ["tasks", "recent", userId], queryFn: getRecentTasks, enabled: Boolean(userId) });
  const remainingPoints = quotaQuery.data?.remainingPoints ?? user?.remainingPoints ?? 0;
  const approxSeconds = quotaQuery.data ? quotaQuery.data.remainingPoints * quotaQuery.data.secondsPerPoint : 0;

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <Badge tone="success">网络ASR</Badge>
          <h1>一键提取声音文字</h1>
          <p>上传视频、音频或抖音链接，快速生成可复制的文字稿。</p>
        </div>
        <div className="hero-panel__actions">
          <Button icon={<UploadCloud size={18} />} onClick={() => navigate("/upload")}>
            上传文件
          </Button>
          <Button variant="secondary" icon={<Link2 size={18} />} onClick={() => navigate("/upload?mode=link")}>
            粘贴抖音链接
          </Button>
        </div>
      </section>

      <section className="split-grid">
        <Card eyebrow="我的额度" title={quotaQuery.isFetching && !quotaQuery.data ? "读取中" : `${remainingPoints} 点`}>
          <p className="muted-text">
            {quotaQuery.data
              ? `大约还可处理 ${approxSeconds} 秒音视频，提交前会先预估所需额度。`
              : "额度加载完成后会自动更新，不影响你浏览其它内容。"}
          </p>
          <Link className="text-link" to="/payment">
            去购买额度 <ArrowRight size={14} />
          </Link>
        </Card>

        <Card eyebrow="邀请返现" title="邀请好友，充值后你可获得现金奖励">
          <p className="muted-text">把专属链接发给好友。好友充值成功后，收益会自动记录，满足金额即可申请提现。</p>
          <Link className="text-link" to="/invite">
            查看我的收益 <Gift size={14} />
          </Link>
        </Card>
      </section>

      <Card
        eyebrow="最近处理"
        title="最新文稿"
        action={
          <Button variant="ghost" size="sm" onClick={() => navigate("/tasks")}>
            查看全部
          </Button>
        }
      >
        {recentTasksQuery.isFetching && !recentTasksQuery.data ? (
          <LoadingSkeleton lines={4} />
        ) : recentTasksQuery.data && recentTasksQuery.data.length > 0 ? (
          <div className="task-list">
            {recentTasksQuery.data.map((task) => (
              <TaskRow key={task.taskNo} task={task} />
            ))}
          </div>
        ) : (
          <EmptyState title="还没有文稿" description="上传一个文件，或导入抖音链接，处理进度会显示在这里。" />
        )}
      </Card>
    </div>
  );
}
