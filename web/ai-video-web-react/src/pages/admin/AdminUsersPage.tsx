import { FormEvent, useDeferredValue, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw, Search, SlidersHorizontal } from "lucide-react";

import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, Modal, useToast } from "../../components/ui";
import { queryClient } from "../../lib/query-client";
import { adjustAdminUserQuota, getAdminUserDetail, getAdminUsers } from "../../services/admin";
import type { AdminUser } from "../../types/api";
import { refreshBillingCache } from "../../lib/billing-cache";

const EMPTY_USERS: AdminUser[] = [];

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "ENABLE") return "success";
  if (status === "DISABLE") return "danger";
  return "neutral";
}

function statusText(status: string) {
  const map: Record<string, string> = {
    ENABLE: "正常",
    DISABLE: "已禁用",
  };
  return map[status] ?? status;
}

export function AdminUsersPage() {
  const { showToast } = useToast();
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustPoints, setAdjustPoints] = useState("");
  const [adjustRemark, setAdjustRemark] = useState("");

  const usersQuery = useQuery({
    queryKey: ["admin", "users", { keyword: deferredKeyword, pageNo: 1, pageSize: 20 }],
    queryFn: () => getAdminUsers({ keyword: deferredKeyword, pageNo: 1, pageSize: 20 }),
    placeholderData: (previousData) => previousData,
    refetchOnWindowFocus: true,
  });

  const userDetailQuery = useQuery({
    queryKey: ["admin", "users", "detail", selectedUid],
    queryFn: () => getAdminUserDetail(selectedUid!),
    enabled: Boolean(selectedUid),
    refetchOnWindowFocus: true,
  });

  const adjustMutation = useMutation({
    mutationFn: adjustAdminUserQuota,
    onSuccess: async (detail) => {
      showToast({ tone: "success", title: "积分已调整", description: `${detail.uid} 当前 ${detail.remainingPoints} 积分` });
      setAdjustOpen(false);
      setAdjustPoints("");
      setAdjustRemark("");
      setSelectedUid(detail.uid);
      queryClient.setQueryData(["admin", "users", "detail", detail.uid], detail);
      await refreshBillingCache();
    },
    onError: (error) => {
      showToast({ tone: "error", title: "调整失败", description: error.message });
    },
  });

  const users = usersQuery.data?.records ?? EMPTY_USERS;
  const selectedUser = userDetailQuery.data;

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setKeyword(keywordInput.trim());
  }

  function handleAdjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUid) return;
    const points = Number(adjustPoints);
    if (!Number.isInteger(points) || points === 0) {
      showToast({ tone: "warning", title: "请输入非零整数积分" });
      return;
    }
    if (!adjustRemark.trim()) {
      showToast({ tone: "warning", title: "请填写调整原因" });
      return;
    }
    adjustMutation.mutate({ uid: selectedUid, points, remark: adjustRemark.trim() });
  }

  return (
    <div className="page-stack admin-page">
      <div className="page-heading admin-heading">
        <div>
          <p className="eyebrow">用户管理</p>
          <h1>用户积分</h1>
          <p>搜索用户、查看总额度及任务、支付、邀请统计，手动调整原有额度。</p>
        </div>
        <Badge tone="warning">高风险操作需备注</Badge>
      </div>

      <section className="admin-workbench-grid">
        <Card className="admin-table-card">
          <form className="admin-toolbar" onSubmit={handleSearch}>
            <Input
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              placeholder="邮箱 / UID / 邀请码 / 昵称"
              leftIcon={<Search size={16} />}
            />
            <Button type="submit" variant="secondary">
              搜索
            </Button>
            <Button type="button" variant="ghost" icon={<RefreshCw size={16} />} loading={usersQuery.isFetching || userDetailQuery.isFetching}
              onClick={() => void refreshBillingCache()}>刷新</Button>
          </form>
          {usersQuery.isError ? <p className="error-text">额度暂时无法同步，请刷新重试。</p> : null}

          {usersQuery.isFetching && !usersQuery.data ? (
            <LoadingSkeleton lines={8} />
          ) : users.length ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>用户</th>
                    <th>总积分</th>
                    <th>任务</th>
                    <th>支付</th>
                    <th>状态</th>
                    <th>注册时间</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.uid}
                      className={selectedUid === user.uid ? "is-selected" : undefined}
                      onClick={() => setSelectedUid(user.uid)}
                    >
                      <td>
                        <strong>{user.nickname || user.email || user.mobile || user.uid}</strong>
                        <span>{user.uid}</span>
                      </td>
                      <td>{user.remainingPoints}</td>
                      <td>{user.taskCount}</td>
                      <td>{user.paidOrderCount}</td>
                      <td>
                        <Badge tone={statusTone(user.status)}>{statusText(user.status)}</Badge>
                      </td>
                      <td>{formatDate(user.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="暂无用户" description="换一个关键词试试，或等待新用户注册。" />
          )}
        </Card>

        <Card
          title="用户详情"
          eyebrow="详情"
          action={
            selectedUid ? (
              <Button type="button" size="sm" icon={<SlidersHorizontal size={15} />} disabled={!selectedUser || selectedUser.uid !== selectedUid || userDetailQuery.isError} onClick={() => setAdjustOpen(true)}>
                调整积分
              </Button>
            ) : null
          }
        >
          {userDetailQuery.isError ? <p className="error-text">该用户额度暂时无法同步，请刷新重试。</p> : null}
          {userDetailQuery.isFetching && !selectedUser ? (
            <LoadingSkeleton lines={8} />
          ) : selectedUser ? (
            <div className="admin-detail-panel">
              <div className="admin-detail-title">
                <strong>{selectedUser.nickname || selectedUser.email || selectedUser.mobile || selectedUser.uid}</strong>
                <Badge tone={statusTone(selectedUser.status)}>{statusText(selectedUser.status)}</Badge>
              </div>
              <div className="admin-kv-list">
                <span>UID</span>
                <strong>{selectedUser.uid}</strong>
                <span>邮箱</span>
                <strong>{selectedUser.email ?? "尚未绑定"}</strong>
                <span>邀请码</span>
                <strong>{selectedUser.inviteCode}</strong>
                <span>邀请人</span>
                <strong>{selectedUser.inviterUid ?? "-"}</strong>
                <span>总积分</span>
                <strong>{selectedUser.remainingPoints}</strong>
                <span>购买额度</span>
                <strong>{selectedUser.purchasedRemainingPoints}</strong>
                <span>原有额度（含赠送）</span>
                <strong>{selectedUser.localRemainingPoints}</strong>
                <span>任务数</span>
                <strong>{selectedUser.taskCount}</strong>
                <span>成功支付</span>
                <strong>{selectedUser.paidOrderCount}</strong>
                <span>邀请数</span>
                <strong>{selectedUser.inviteCount}</strong>
                <span>注册时间</span>
                <strong>{formatDate(selectedUser.createdAt)}</strong>
              </div>
            </div>
          ) : (
            <EmptyState title="选择一个用户" description="点击左侧列表中的用户查看详情和调整积分。" />
          )}
        </Card>
      </section>

      <Modal
        open={adjustOpen}
        title="手动调整积分"
        onClose={() => setAdjustOpen(false)}
        footer={
          <>
            <Button type="button" variant="ghost" onClick={() => setAdjustOpen(false)}>
              取消
            </Button>
            <Button type="submit" form="admin-adjust-quota-form" loading={adjustMutation.isPending}>
              提交调整
            </Button>
          </>
        }
      >
        <form id="admin-adjust-quota-form" className="admin-form" onSubmit={handleAdjust}>
          <p className="muted-text">仅调整原有额度（含赠送），当前 {selectedUser?.localRemainingPoints ?? "-"} 点；购买额度由支付平台管理。</p>
          <Input
            label="调整积分"
            value={adjustPoints}
            onChange={(event) => setAdjustPoints(event.target.value)}
            placeholder="正数增加，负数扣减，例如 100 或 -50"
          />
          <Input
            label="调整原因"
            value={adjustRemark}
            onChange={(event) => setAdjustRemark(event.target.value)}
            placeholder="例如：客服补偿、异常扣减"
          />
        </form>
      </Modal>
    </div>
  );
}
