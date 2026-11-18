import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Clipboard, RefreshCw, Send } from "lucide-react";

import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { applyWithdrawal, getInviteInfo, getInviteRecords, getWithdrawalSummary, getWithdrawals } from "../services/invite";
import { useAuthStore } from "../store/auth-store";

function money(value?: string | number | null) {
  return Number(value ?? 0).toFixed(2);
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "PAID" || status === "SUCCESS") return "success";
  if (status === "REJECTED" || status === "FAIL") return "danger";
  if (status === "PENDING") return "warning";
  return "neutral";
}

function rewardStatusText(status: string) {
  const map: Record<string, string> = {
    PENDING: "冻结中",
    REVERSED: "退款已撤回",
    SUCCESS: "已入账",
    PAID: "已打款",
    REJECTED: "已驳回",
  };
  return map[status] ?? status;
}

export function InvitePage() {
  const { showToast } = useToast();
  const user = useAuthStore((state) => state.user);
  const [alipayAccount, setAlipayAccount] = useState("");

  const inviteInfoQuery = useQuery({ queryKey: ["invite", "info"], queryFn: getInviteInfo });
  const inviteRecordsQuery = useQuery({
    queryKey: ["invite", "records"],
    queryFn: getInviteRecords,
    placeholderData: (previousData) => previousData,
  });
  const withdrawalSummaryQuery = useQuery({ queryKey: ["invite", "withdrawals", "summary"], queryFn: getWithdrawalSummary });
  const withdrawalsQuery = useQuery({
    queryKey: ["invite", "withdrawals"],
    queryFn: getWithdrawals,
    placeholderData: (previousData) => previousData,
  });

  const inviteCode = inviteInfoQuery.data?.inviteCode ?? user?.inviteCode ?? "";
  const inviteLink = useMemo(() => {
    if (!inviteCode) return "";
    return `${window.location.origin}/login?inviteCode=${encodeURIComponent(inviteCode)}`;
  }, [inviteCode]);

  const summary = withdrawalSummaryQuery.data;
  const canApply = Boolean(summary?.canApply);

  const withdrawalMutation = useMutation({
    mutationFn: applyWithdrawal,
    onSuccess: async () => {
      setAlipayAccount("");
      showToast({ tone: "success", title: "提现申请已提交", description: "我们会尽快处理你的申请。" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["invite", "withdrawals"] }),
        queryClient.invalidateQueries({ queryKey: ["invite", "withdrawals", "summary"] }),
      ]);
    },
    onError: (error) => {
      showToast({ tone: "error", title: "提交失败", description: error.message });
    },
  });

  async function handleCopyInviteLink() {
    if (!inviteLink) {
      showToast({ tone: "warning", title: "暂时没有邀请链接", description: "请重新登录后再试。" });
      return;
    }
    await navigator.clipboard.writeText(inviteLink);
    showToast({ tone: "success", title: "邀请链接已复制" });
  }

  function handleWithdraw(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const account = alipayAccount.trim();
    if (!account) {
      showToast({ tone: "warning", title: "请输入支付宝账号" });
      return;
    }
    if (!canApply) {
      showToast({
        tone: "warning",
        title: "暂时不能提现",
        description: `满 ¥${money(summary?.minWithdrawalAmount ?? 10)} 后即可申请。`,
      });
      return;
    }
    withdrawalMutation.mutate(account);
  }

  return (
    <div className="page-stack">
      <section className="invite-panel">
        <div>
          <Badge tone="success">邀请返现</Badge>
          <h1>分享有奖，到账可提</h1>
          <p>好友通过邀请链接完成邮箱注册，核验支付后，按购买时套餐标价的 {inviteInfoQuery.data?.rewardRatePercent ?? 10}% 返现，冻结 {inviteInfoQuery.data?.holdDays ?? 7} 天后可提。</p>
        </div>
        <div className="invite-code">
          <span>我的邀请码</span>
          <strong>{inviteCode || "-"}</strong>
        </div>
      </section>

      <section className="commerce-grid">
        <Card title="分享给好友" eyebrow="邀请链接">
          <div className="copy-box">
            <span>{inviteLink || "登录后生成邀请链接"}</span>
            <Button type="button" variant="secondary" icon={<Clipboard size={16} />} onClick={handleCopyInviteLink}>
              复制链接
            </Button>
          </div>
          <p className="muted-text">邀请关系在首次注册时确定。支付回跳不算到账；冻结期结束会再次核验，退款返现撤回，人工审核后打款。</p>
        </Card>

        <Card
          title={`可提现 ¥${money(summary?.withdrawableAmount)}`}
          eyebrow="提现"
          action={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              icon={<RefreshCw size={16} />}
              loading={withdrawalSummaryQuery.isFetching || withdrawalsQuery.isFetching}
              onClick={() => {
                void withdrawalSummaryQuery.refetch();
                void withdrawalsQuery.refetch();
              }}
            >
              刷新
            </Button>
          }
        >
          {withdrawalSummaryQuery.isFetching && !summary ? (
            <LoadingSkeleton lines={4} />
          ) : (
            <div className="metric-mini-grid">
              <div>
                <span>累计收益</span>
                <strong>¥{money(summary?.rewardTotal)}</strong>
              </div>
              <div>
                <span>处理中</span>
                <strong>¥{money(summary?.pendingAmount)}</strong>
              </div>
              <div>
                <span>已到账</span>
                <strong>¥{money(summary?.paidAmount)}</strong>
              </div>
            </div>
          )}

          <form className="withdraw-form" onSubmit={handleWithdraw}>
            <p className="muted-text">冻结返现 ¥{money(summary?.frozenRewardAmount)}</p>
            {Number(summary?.debtAmount || 0) > 0 ? <p className="error-text">存在退款待抵扣 ¥{money(summary?.debtAmount)}，抵扣完成前不能提现。</p> : null}
            <Input
              label="支付宝账号"
              value={alipayAccount}
              onChange={(event) => setAlipayAccount(event.target.value)}
              placeholder="请输入收款支付宝账号"
              hint={`最低提现金额 ¥${money(summary?.minWithdrawalAmount ?? 10)}`}
            />
            <Button type="submit" icon={<Send size={16} />} loading={withdrawalMutation.isPending} disabled={!canApply}>
              申请提现
            </Button>
          </form>
        </Card>
      </section>

      <section className="split-grid">
        <Card title="邀请记录" eyebrow="收益明细">
          {inviteRecordsQuery.isFetching && !inviteRecordsQuery.data ? (
            <LoadingSkeleton lines={5} />
          ) : inviteRecordsQuery.data?.length ? (
            <div className="record-list">
              {inviteRecordsQuery.data.map((record) => (
                <article className="record-row" key={`${record.inviteeUid}-${record.triggerOrderNo}-${record.createdAt}`}>
                  <div>
                    <strong>好友 {record.inviteeUid}</strong>
                    <span>{formatDate(record.createdAt)}</span>
                  </div>
                  <div className="record-row__right">
                    <Badge tone={statusTone(record.rewardStatus)}>{rewardStatusText(record.rewardStatus)}</Badge>
                    <strong className={record.rewardStatus === "REVERSED" ? "error-text" : "positive-text"}>{record.rewardStatus === "REVERSED" ? "已撤回 " : ""}¥{money(record.rewardAmount)}</strong>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="还没有邀请记录" description="好友充值成功后，收益会显示在这里。" />
          )}
        </Card>

        <Card title="提现记录" eyebrow="申请记录">
          {withdrawalsQuery.isFetching && !withdrawalsQuery.data ? (
            <LoadingSkeleton lines={5} />
          ) : withdrawalsQuery.data?.length ? (
            <div className="record-list">
              {withdrawalsQuery.data.map((withdrawal) => (
                <article className="record-row" key={withdrawal.withdrawNo}>
                  <div>
                    <strong>¥{money(withdrawal.amount)}</strong>
                    <span>{withdrawal.alipayAccount} · {formatDate(withdrawal.createdAt)}</span>
                  </div>
                  <div className="record-row__right">
                    <Badge tone={statusTone(withdrawal.status)}>{withdrawal.statusDesc || rewardStatusText(withdrawal.status)}</Badge>
                    {withdrawal.remark ? <span>{withdrawal.remark}</span> : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="还没有提现记录" description="满足最低金额后，填写支付宝账号即可申请。" />
          )}
        </Card>
      </section>
    </div>
  );
}
