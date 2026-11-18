import { api } from "../lib/api-client";
import type { QuotaLogPage } from "../types/api";

export type QuotaLogParams = {
  changeType?: string;
  pageNo?: number;
  pageSize?: number;
};

function buildQuotaLogQuery(params: QuotaLogParams = {}) {
  const search = new URLSearchParams();
  if (params.changeType && params.changeType !== "ALL") search.set("changeType", params.changeType);
  search.set("pageNo", String(params.pageNo ?? 1));
  search.set("pageSize", String(params.pageSize ?? 20));
  return `?${search.toString()}`;
}

export function getProfileQuotaLogs(params: QuotaLogParams = {}) {
  return api.get<QuotaLogPage>(`/profile/quota-logs${buildQuotaLogQuery(params)}`);
}
