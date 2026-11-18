import { api } from "../lib/api-client";
import type { QuotaInfo } from "../types/api";

export function getQuota() {
  return api.get<QuotaInfo>("/quota");
}
