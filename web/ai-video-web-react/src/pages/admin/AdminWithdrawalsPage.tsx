import { FormEvent, useDeferredValue, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Search, XCircle } from "lucide-react";

import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, Modal, useToast } from "../../components/ui";
import { queryClient } from "../../lib/query-client";
import { getAdminWithdrawals, updateAdminWithdrawalStatus } from "../../services/admin";
import type { AdminWithdrawal } from "../../types/api";

const EMPTY_WITHDRAWALS: AdminWithdrawal[] = [];
const statusOptions = [
  { label: "全部", value: "ALL" },
  { label: "待处理", value: "PENDING" },
  { label: "已打款", value: "PAID" },
  { label: "已驳回", value: "REJECTED" },
];

function money(value?: string | number | null) {
  return Number(value ?? 0).toFixed(2);
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "PAID") return "success";
  if (status === "REJECTED") return "danger";
  if (status === "PENDING") return "warning";
  return "neutral";
}

function statusText(status: string) {
  const map: Record<string, string> = {
    PENDING: "待处理",
    PAID: "已打款",
    REJECTED: "已驳回",
  };
  return map[status] ?? status;
}

export function AdminWithdrawalsPage() {
  const { showToast } = useToast();
  const [status, setStatus] = useState("PENDING");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword);
  const [target, setTarget] = useState<AdminWithdrawal | null>(null);
  const [targetStatus, setTargetStatus] = useState<"PAID" | "REJECTED">("PAID");
  const [remark, setRemark] = useState("");

  const withdrawalsQuery = useQuery({
    queryKey: ["admin", "withdrawals", { status, keyword: deferredKeyword, pageNo: 1, pageSize: 20 }],
    queryFn: () => getAdminWithdrawals({ status, keyword: deferredKeyword, pageNo: 1, pageSize: 20 }),
    placeholderData: (previousData) => previousData,
  });

  const updateMutation = useMutation({
    mutationFn: updateAdminWithdrawalStatus,
    onSuccess: async (updated) => {
      showToast({ tone: "success", title: "提现单已更新", description: `${updated.withdrawNo} 已标记为${statusText(updated.status)}` });
      setTarget(null);
      setRemark("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "withdrawals"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "dashboard", "overview"] }),
      ]);
    },
    onError: (error) => {
      showToast({ tone: "error", title: "操作失败", description: error.message });
    },
  });

  const withdrawals = withdrawalsQuery.data?.records ?? EMPTY_WITHDRAWALS;

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setKeyword(keywordInput.trim());
  }

  function openAction(withdrawal: AdminWithdrawal, nextStatus: "PAID" | "REJECTED") {
    setTarget(withdrawal);
    setTargetStatus(nextStatus);
    setRemark(nextStatus === "PAID" ? "线下已打款" : "申请信息异常，已驳回");
  }

  function handleStatusUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!target) return;
    updateMutation.mutate({ withdrawNo: target.withdrawNo, status: targetStatus, remark: remark.trim() || undefined });
  }

  return (
    <div className="page-stack admin-page">
      <div className="page-heading admin-heading">
        <div>
          <p className="eyebrow">提现处理</p>
          <h1>提现处理</h1>
          <p>筛选待处理、已打款和已驳回申请；操作成功后只刷新提现队列和概览指标。</p>
        </div>
        <Badge tone="danger">保留处理人、处理时间、打款时间</Badge>
      </div>

      <Card>
        <div className="admin-toolbar admin-toolbar--wide">
          <div className="status-tabs">
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
          <form className="admin-search-form" onSubmit={handleSearch}>
            <Input
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              placeholder="提现单号 / 支付宝 / 邮箱 / UID"
              leftIcon={<Search size={16} />}
            />
            <Button type="submit" variant="secondary">
              搜索
            </Button>
          </form>
        </div>
      </Card>

      <Card className="admin-table-card">
        {withdrawalsQuery.isFetching && !withdrawalsQuery.data ? (
          <LoadingSkeleton lines={8} />
        ) : withdrawals.length ? (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>提现单</th>
                  <th>用户</th>
                  <th>金额</th>
                  <th>支付宝</th>
                  <th>状态</th>
                  <th>申请时间</th>
                  <th>处理信息</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {withdrawals.map((withdrawal) => (
                  <tr key={withdrawal.withdrawNo}>
                    <td>
                      <strong>{withdrawal.withdrawNo}</strong>
                      <span>{withdrawal.remark ?? "-"}</span>
                    </td>
                    <td>
                      <strong>{withdrawal.nickname || withdrawal.email || withdrawal.mobile || withdrawal.userUid || "-"}</strong>
                      <span>{withdrawal.userUid ?? "-"}</span>
                    </td>
                    <td>¥{money(withdrawal.amount)}</td>
                    <td>{withdrawal.alipayAccount}</td>
                    <td>
                      <Badge tone={statusTone(withdrawal.status)}>{withdrawal.statusDesc || statusText(withdrawal.status)}</Badge>
                    </td>
                    <td>{formatDate(withdrawal.createdAt)}</td>
                    <td>
                      <strong>{withdrawal.handledBy ? `管理员 ${withdrawal.handledBy}` : "-"}</strong>
                      <span>{formatDate(withdrawal.handledAt)}</span>
                    </td>
                    <td>
                      {withdrawal.status === "PENDING" ? (
                        <div className="admin-row-actions">
                          <Button
                            type="button"
                            size="sm"
                            icon={<CheckCircle2 size={14} />}
                            onClick={() => openAction(withdrawal, "PAID")}
                          >
                            已打款
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            icon={<XCircle size={14} />}
                            onClick={() => openAction(withdrawal, "REJECTED")}
                          >
                            驳回
                          </Button>
                        </div>
                      ) : (
                        <span>{withdrawal.paidAt ? `打款 ${formatDate(withdrawal.paidAt)}` : "已处理"}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="暂无提现记录" description="切换筛选条件或等待用户提交提现申请。" />
        )}
      </Card>

      <Modal
        open={Boolean(target)}
        title={targetStatus === "PAID" ? "标记为已打款" : "驳回提现申请"}
        onClose={() => setTarget(null)}
        footer={
          <>
            <Button type="button" variant="ghost" onClick={() => setTarget(null)}>
              取消
            </Button>
            <Button
              type="submit"
              form="admin-withdrawal-status-form"
              variant={targetStatus === "PAID" ? "primary" : "danger"}
              loading={updateMutation.isPending}
            >
              确认{targetStatus === "PAID" ? "已打款" : "驳回"}
            </Button>
          </>
        }
      >
        <form id="admin-withdrawal-status-form" className="admin-form" onSubmit={handleStatusUpdate}>
          <div className="admin-confirm-box">
            <span>提现单</span>
            <strong>{target?.withdrawNo}</strong>
            <span>金额</span>
            <strong>¥{money(target?.amount)}</strong>
            <span>支付宝</span>
            <strong>{target?.alipayAccount}</strong>
          </div>
          <Input
            label="处理备注"
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
            placeholder="会写入处理备注"
          />
        </form>
      </Modal>
    </div>
  );
}
