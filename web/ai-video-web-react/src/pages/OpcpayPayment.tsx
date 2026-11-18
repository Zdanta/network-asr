import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, Modal, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { useAuthStore } from "../store/auth-store";
import { createOpcpayPurchase, getOpcpayAccess, getOpcpayTransaction, getOpcpayEntry } from "../services/opcpay";
import { isPaymentUrl, isHttpsUrl, purchaseEntryExpired } from "../lib/payment-links";
import { ApiError } from "../lib/api-error";
import { refreshBillingCache } from "../lib/billing-cache";
import type { OpcpayCatalog, PurchaseIntent } from "../services/opcpay";

export function OpcpayPayment({ catalog, secondsPerPoint }: { catalog: OpcpayCatalog; secondsPerPoint?: number }) {
  const uid = useAuthStore((s) => s.user?.uid);
  const storageKey = `opcpay-intent:${uid}`;
  const pendingKey = `opcpay-pending:${uid}`;
  const { showToast } = useToast();
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentError, setPaymentError] = useState("");
  const [intent, setIntent] = useState<PurchaseIntent | null>(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) || "null") as PurchaseIntent | null; }
    catch { return null; }
  });
  function save(value: PurchaseIntent | null) {
    if (value) {
      localStorage.setItem(storageKey, JSON.stringify(value));
      let pending: Record<string, PurchaseIntent> = {};
      try { pending = JSON.parse(localStorage.getItem(pendingKey) || "{}"); } catch { /* replace malformed cache */ }
      pending[value.skuId] = value;
      localStorage.setItem(pendingKey, JSON.stringify(pending));
    }
    else localStorage.removeItem(storageKey);
    setIntent(value);
  }
  const access = useQuery({ queryKey: ["opcpay", "access", uid], queryFn: getOpcpayAccess,
    refetchInterval: intent ? 15000 : false });
  const transaction = useQuery({ queryKey: ["opcpay", "transaction", intent?.orderNo],
    queryFn: () => getOpcpayTransaction(intent!.orderNo!),
    enabled: Boolean(intent?.orderNo && catalog.transactionQuery), refetchInterval: 15000 });
  const entry = useQuery({ queryKey: ["opcpay", "entry", uid, intent?.orderNo],
    queryFn: () => getOpcpayEntry(intent!.orderNo!), enabled: Boolean(intent?.orderNo) });
  const payment = entry.data ?? intent;
  const completed = transaction.data?.status === "PAID" || transaction.data?.status === "REFUNDED";
  useEffect(() => {
    if (!completed || !intent?.orderNo) return;
    void queryClient.invalidateQueries({ queryKey: ["opcpay", "catalog"] });
    void refreshBillingCache();
    let pending: Record<string, PurchaseIntent> = {};
    try { pending = JSON.parse(localStorage.getItem(pendingKey) || "{}"); } catch { /* no pending cache */ }
    if (pending[intent.skuId]?.orderNo === intent.orderNo) delete pending[intent.skuId];
    localStorage.setItem(pendingKey, JSON.stringify(pending));
  }, [completed, intent?.orderNo, intent?.skuId, pendingKey]);
  const purchase = useMutation({ mutationFn: createOpcpayPurchase,
    onSuccess: (result, original) => {
      setPaymentError("");
      save({ ...original, orderNo: result.orderNo, payUrl: result.payUrl || undefined, qrCode: result.qrCode || undefined, expiresAt: result.expiresAt || undefined });
      void queryClient.invalidateQueries({ queryKey: ["opcpay", "entry"] });
      if (!result.payUrl && !result.qrCode) setPaymentError("暂时无法获取支付二维码，请重试。");
    }, onError: (error, original) => {
      if (error instanceof ApiError && error.code === 3013) {
        let pending: Record<string, PurchaseIntent> = {};
        try { pending = JSON.parse(localStorage.getItem(pendingKey) || "{}"); } catch { /* clear invalid cache */ }
        delete pending[original.skuId];
        localStorage.setItem(pendingKey, JSON.stringify(pending));
        localStorage.removeItem(storageKey);
        setIntent(null);
        setPaymentOpen(false);
      }
      setPaymentError(error.message);
      showToast({ tone: "error", title: "暂时无法支付", description: error.message });
      void queryClient.invalidateQueries({ queryKey: ["opcpay", "catalog"] }); } });
  function start(skuId: string) {
    sessionStorage.removeItem("asr-selected-sku");
    setPaymentError("");
    setPaymentOpen(true);
    if (intent && !completed) save(intent);
    let pending: Record<string, PurchaseIntent> = {};
    try { pending = JSON.parse(localStorage.getItem(pendingKey) || "{}"); } catch { /* replace malformed cache */ }
    const previous = pending[skuId];
    const next = previous && !purchaseEntryExpired(previous.expiresAt) && !(completed && previous.orderNo === intent?.orderNo)
      ? previous : { actionId: crypto.randomUUID(), skuId };
    save(next); // Persist BEFORE writing. An uncertain request never generates a new ID.
    purchase.mutate(next);
  }
  async function refresh() {
    await refreshBillingCache();
    await queryClient.invalidateQueries({ queryKey: ["opcpay", "catalog"] });
  }
  const entryExpired = purchaseEntryExpired(payment?.expiresAt);
  const selectedPlan = catalog.plans.find((plan) => plan.skuId === intent?.skuId);
  return <div className="page-stack">
    <section className="commerce-hero"><div><Badge tone="success">支付宝购买额度</Badge>
      <h1>购买额度</h1></div></section>
    <Card><h2>总额度：{access.data ? `${(access.data.remaining + access.data.legacyRemainingPoints).toLocaleString()} 点` : "正在查询…"}</h2>
      {access.data ? <>
        <p>购买额度：<strong>{access.data.remaining.toLocaleString()} {access.data.quotaUnit === "COUNT" ? "次" : "点"}</strong></p>
        <p>原有额度（含赠送）：<strong>{access.data.legacyRemainingPoints.toLocaleString()} 点</strong></p>
        {access.data.legacyRemainingPoints > 0 ? <p className="muted-text">原有额度优先用于可覆盖的任务，单次任务不合并扣除两份额度。</p> : null}
      </> : <p>正在查询…</p>}
      {access.isError ? <p className="error-text">权益查询失败，请稍后重试。</p> : null}
      <Button variant="ghost" loading={access.isFetching} onClick={() => void refresh()}>刷新权益</Button>
      {intent && !completed ? <Button variant="secondary" onClick={() => setPaymentOpen(true)}>继续支付</Button> : null}</Card>
    <div className="pricing-grid">{catalog.plans.map((plan) => <Card key={plan.skuId} className="pricing-card payment-plan-card">
      <Badge tone="success">支付宝积分包</Badge><h2>{plan.name}</h2><p className="price">¥{plan.price}</p>
      <div><p>{plan.quantity.toLocaleString()} 点额度</p>
        {catalog.quotaUnit === "POINT" && secondsPerPoint && secondsPerPoint > 0 ? <p className="muted-text">约可处理 {(plan.quantity * secondsPerPoint / 60).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 分钟音频</p> : null}</div>
      <Button disabled={purchase.isPending} loading={purchase.isPending && purchase.variables?.skuId === plan.skuId}
        onClick={() => start(plan.skuId)}>{intent?.skuId === plan.skuId && !completed ? "继续支付" : sessionStorage.getItem("asr-selected-sku") === plan.skuId ? "继续购买" : "购买"}</Button>
    </Card>)}</div>
    <Modal open={paymentOpen} title={selectedPlan?.name ?? "支付宝付款"} onClose={() => setPaymentOpen(false)}>
      <div className="payment-dialog">
        {completed ? <><Badge tone={transaction.data?.status === "PAID" ? "success" : "neutral"}>{transaction.data?.status === "PAID" ? "支付成功" : "已退款"}</Badge><Button onClick={() => setPaymentOpen(false)}>完成</Button></> : <>
          {selectedPlan ? <p className="price">¥{selectedPlan.price}</p> : null}
          {purchase.isPending || entry.isFetching ? <p>正在准备支付…</p> : entryExpired ? <>
            <p>二维码已过期</p><Button onClick={() => { save(null); setPaymentOpen(false); }}>重新选择套餐</Button>
          </> : <>
            {isHttpsUrl(payment?.qrCode) ? <><img src={payment!.qrCode!} alt="支付宝付款二维码" width="220" height="220" referrerPolicy="no-referrer" /><p>请使用支付宝扫码付款</p></> : null}
            {isPaymentUrl(payment?.payUrl) ? <a className="ui-button ui-button--primary" href={payment!.payUrl!} target="_blank" rel="noopener noreferrer">打开支付宝</a> : null}
          </>}
          {paymentError || entry.isError ? <><p className="error-text">{paymentError || "暂时无法获取支付信息"}</p><Button loading={purchase.isPending} onClick={() => { if (intent) purchase.mutate(intent); }}>重试</Button></> : null}
        </>}
      </div>
    </Modal>
  </div>;
}
