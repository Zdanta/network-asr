import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { LogOut, RefreshCw, UserRound } from "lucide-react";

import { Badge, Button, Card, EmptyState, LoadingSkeleton, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { logout } from "../services/auth";
import { getProfileQuotaLogs } from "../services/profile";
import { getQuota } from "../services/quota";
import { useAuthStore } from "../store/auth-store";
import type { QuotaLog } from "../types/api";
import { BindEmailCard } from "../components/BindEmailCard";
import { refreshBillingCache } from "../lib/billing-cache";

const quotaLogTypes = [
  { label: "全部", value: "ALL" },
  { label: "购买", value: "PURCHASE" },
  { label: "使用", value: "CONSUME" },
  { label: "邀请", value: "INVITE_REWARD" },
  { label: "赠送", value: "REGISTER_GIFT" },
];

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function isTaskBizNo(value?: string | null) {
  return Boolean(value?.startsWith("TASK"));
}

function logTitle(log: QuotaLog) {
  const map: Record<string, string> = {
    CONSUME: "处理素材",
    PURCHASE: "购买额度",
    REGISTER_GIFT: "新用户赠送",
    INVITE_REWARD: "邀请奖励",
    ADMIN_GRANT: "平台赠送",
    ADMIN_DEDUCT: "额度调整",
  };
  return map[log.changeType] ?? log.changeTypeDesc;
}

function QuotaLogMeta({ log }: { log: QuotaLog }) {
  const bizNo = log.changeType === "PURCHASE" ? undefined : log.bizNo?.trim();
  const remark = log.remark?.trim();
  const bizLabel = isTaskBizNo(bizNo) ? "处理编号" : "记录编号";

  return (
    <div className="record-row__meta">
      {bizNo ? (
        <span className="record-row__biz">
          {bizLabel} <code>{bizNo}</code>
        </span>
      ) : null}
      {remark && !/ASR|billing|duration/i.test(remark) ? <span>{remark}</span> : null}
      {!bizNo && !remark ? <span>额度变动</span> : null}
    </div>
  );
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const user = useAuthStore((state) => state.user);
  const logoutLocal = useAuthStore((state) => state.logoutLocal);
  const [changeType, setChangeType] = useState("ALL");

  const quotaQuery = useQuery({ queryKey: ["quota", user?.uid], queryFn: getQuota, refetchInterval: 15000 });
  const quotaLogsQuery = useQuery({
    queryKey: ["profile", "quota-logs", user?.uid, { changeType, pageNo: 1, pageSize: 20 }],
    queryFn: () => getProfileQuotaLogs({ changeType, pageNo: 1, pageSize: 20 }),
    placeholderData: (previousData) => previousData,
    refetchInterval: 15000,
  });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSettled: () => {
      logoutLocal();
      queryClient.clear();
      showToast({ tone: "info", title: "已退出登录" });
      navigate("/login", { replace: true });
    },
  });

  const remainingPoints = quotaQuery.data?.remainingPoints ?? user?.remainingPoints ?? 0;
  const approxSeconds = quotaQuery.data ? quotaQuery.data.remainingPoints * quotaQuery.data.secondsPerPoint : null;

  return (
    <div className="page-stack">
      <section className="profile-hero">
        <div>
          <Badge tone="info">我的账户</Badge>
          <h1>{user?.nickname || user?.email || "个人中心"}</h1>
          <p>查看账户信息、剩余额度和使用明细。所有素材处理记录都可以在“处理记录”中查看。</p>
        </div>
        <UserRound size={48} />
      </section>

      {!user?.email ? <BindEmailCard /> : null}
      <section className="profile-grid">
        <Card title="账户信息" eyebrow="基本信息">
          <div className="info-list">
            <span>账号 ID</span>
            <strong>{user?.uid ?? "-"}</strong>
            <span>邮箱</span>
            <strong>{user?.email ?? "尚未绑定"}</strong>
            <span>邀请码</span>
            <strong>{user?.inviteCode ?? "-"}</strong>
            <span>身份</span>
            <strong>{user?.admin ? "管理员" : "普通用户"}</strong>
          </div>
          <Button
            type="button"
            variant="danger"
            icon={<LogOut size={16} />}
            loading={logoutMutation.isPending}
            onClick={() => logoutMutation.mutate()}
          >
            退出登录
          </Button>
        </Card>

        <Card title={`${remainingPoints} 点额度`} eyebrow="可用额度">
          {quotaQuery.isFetching && !quotaQuery.data ? (
            <LoadingSkeleton lines={4} />
          ) : (
            <div className="metric-mini-grid">
              <div>
                <span>总额度</span>
                <strong>{remainingPoints}</strong>
              </div>
              <div><span>购买额度</span><strong>{quotaQuery.data?.purchasedRemainingPoints ?? "-"} 点</strong></div>
              <div><span>原有额度（含赠送）</span><strong>{quotaQuery.data?.localRemainingPoints ?? "-"} 点</strong></div>
              <div>
                <span>约可处理</span>
                <strong>{approxSeconds ?? "-"} 秒</strong>
              </div>
            </div>
          )}
        </Card>
      </section>

      <Card
        title="额度明细"
        eyebrow="使用明细"
        action={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            icon={<RefreshCw size={16} />}
            loading={quotaLogsQuery.isFetching || quotaQuery.isFetching}
            onClick={() => void refreshBillingCache()}
          >
            刷新
          </Button>
        }
      >
        <div className="status-tabs quota-tabs">
          {quotaLogTypes.map((item) => (
            <Button
              key={item.value}
              type="button"
              size="sm"
              variant={changeType === item.value ? "secondary" : "ghost"}
              onClick={() => setChangeType(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </div>

        {quotaLogsQuery.isFetching && !quotaLogsQuery.data ? (
          <LoadingSkeleton lines={6} />
        ) : quotaLogsQuery.data?.records.length ? (
          <div className="record-list">
            {quotaLogsQuery.data.records.map((log) => (
              <article className="record-row" key={`${log.bizNo}-${log.createdAt}-${log.changeType}`}>
                <div>
                  <strong>{logTitle(log)}</strong>
                  <QuotaLogMeta log={log} />
                </div>
                <div className="record-row__right">
                  <strong className={log.changeAmount >= 0 ? "positive-text" : "negative-text"}>
                    {log.changeAmount >= 0 ? "+" : ""}
                    {log.changeAmount}
                  </strong>
                  <span>{formatDate(log.createdAt)}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="还没有额度明细" description="购买、使用或邀请奖励产生后，会显示在这里。" />
        )}
      </Card>
    </div>
  );
}
