import { api } from "../lib/api-client";
import type { PaymentNotifyResult, PaymentOrderCreateResult, PaymentOrderInfo, PaymentProductType } from "../types/api";

export function createPaymentOrder(productType: PaymentProductType) {
  return api.post<PaymentOrderCreateResult>("/payment/order", { productType });
}

export function getPaymentOrder(orderNo: string) {
  return api.get<PaymentOrderInfo>(`/payment/order/${orderNo}`);
}

export function mockPayOrder(orderNo: string, amount: string) {
  return api.post<PaymentNotifyResult>("/payment/notify", {
    orderNo,
    amount,
    payChannel: "MOCK",
    payStatus: "SUCCESS",
  });
}
