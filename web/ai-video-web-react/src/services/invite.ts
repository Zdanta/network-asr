import { api } from "../lib/api-client";
import type { InviteInfo, InviteRecord, WithdrawalRecord, WithdrawalSummary } from "../types/api";

export function getInviteInfo() {
  return api.get<InviteInfo>("/invite");
}

export function getInviteRecords() {
  return api.get<InviteRecord[]>("/invite/records");
}

export function getWithdrawalSummary() {
  return api.get<WithdrawalSummary>("/invite/withdrawals/summary");
}

export function getWithdrawals() {
  return api.get<WithdrawalRecord[]>("/invite/withdrawals");
}

export function applyWithdrawal(alipayAccount: string) {
  return api.post<WithdrawalRecord>("/invite/withdrawals", { alipayAccount });
}
