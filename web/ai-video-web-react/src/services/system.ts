import { api } from "../lib/api-client";
import type { HealthInfo } from "../types/api";

export function getHealth() {
  return api.get<HealthInfo>("/system/health");
}
