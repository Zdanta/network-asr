import { api } from "../lib/api-client";
import type {
  AdminDashboardOverview,
  AdminOrderPage,
  AdminUserDetail,
  AdminUserPage,
  AdminWithdrawal,
  AdminWithdrawalPage,
} from "../types/api";

export type AdminPageParams = {
  keyword?: string;
  pageNo?: number;
  pageSize?: number;
};

export type AdminWithdrawalParams = AdminPageParams & {
  status?: string;
};

function buildQuery(params: AdminPageParams & { status?: string } = {}) {
  const search = new URLSearchParams();
  if (params.keyword?.trim()) search.set("keyword", params.keyword.trim());
  if (params.status && params.status !== "ALL") search.set("status", params.status);
  search.set("pageNo", String(params.pageNo ?? 1));
  search.set("pageSize", String(params.pageSize ?? 10));
  return `?${search.toString()}`;
}

export function getAdminDashboardOverview() {
  return api.get<AdminDashboardOverview>("/admin/dashboard/overview");
}

export function getAdminOrders(params: AdminPageParams & { status?: string; source?: string } = {}) {
  const search = new URLSearchParams(buildQuery(params).slice(1));
  if (params.source && params.source !== "ALL") search.set("source", params.source);
  if (search.get("status") === "ALL") search.delete("status");
  return api.get<AdminOrderPage>(`/admin/orders?${search.toString()}`);
}

export function getAdminUsers(params: AdminPageParams = {}) {
  return api.get<AdminUserPage>(`/admin/users${buildQuery(params)}`);
}

export function getAdminUserDetail(uid: string) {
  return api.get<AdminUserDetail>(`/admin/users/${uid}`);
}

export function adjustAdminUserQuota(payload: { uid: string; points: number; remark: string }) {
  return api.post<AdminUserDetail>("/admin/users/quota/adjust", payload);
}

export function getAdminWithdrawals(params: AdminWithdrawalParams = {}) {
  return api.get<AdminWithdrawalPage>(`/admin/withdrawals${buildQuery(params)}`);
}

export function updateAdminWithdrawalStatus(payload: { withdrawNo: string; status: "PAID" | "REJECTED"; remark?: string }) {
  return api.put<AdminWithdrawal>(`/admin/withdrawals/${payload.withdrawNo}/status`, {
    status: payload.status,
    remark: payload.remark,
  });
}
