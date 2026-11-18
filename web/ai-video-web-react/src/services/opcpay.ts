import { api } from "../lib/api-client";

export interface OpcpayCatalog {
  enabled: boolean;
  billingMode?: string;
  quotaUnit?: "POINT" | "COUNT";
  transactionQuery?: boolean;
  plans: Array<{ skuId: string; name: string; price: string; quantity: number }>;
}
export interface PurchaseIntent { actionId: string; skuId: string; orderNo?: string; payUrl?: string; qrCode?: string; expiresAt?: string }
export interface PurchaseEntry { orderNo: string; status: string; payUrl: string | null; qrCode: string | null; expiresAt: string | null }
export const getOpcpayCatalog = () => api.get<OpcpayCatalog>("/payment/opcpay/catalog");
export const getOpcpayAccess = () => api.get<{ remaining: number; quotaUnit: string; accessGranted: boolean; legacyRemainingPoints: number }>("/payment/opcpay/access");
export const createOpcpayPurchase = (intent: PurchaseIntent) =>
  api.post<PurchaseEntry>("/payment/opcpay/purchase", { actionId: intent.actionId, skuId: intent.skuId });
export const getOpcpayEntry = (orderNo: string) => api.get<PurchaseEntry>(`/payment/opcpay/purchase/${encodeURIComponent(orderNo)}/entry`);
export const getOpcpayTransaction = (orderNo: string) =>
  api.get<{ status: "PAID" | "PENDING" | "REFUNDED" | "UNKNOWN"; checkedAt: string | null }>(`/payment/opcpay/purchase/${encodeURIComponent(orderNo)}`);
