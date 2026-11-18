import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, QrCode, RefreshCw } from "lucide-react";

import { Badge, Button, Card, EmptyState, LoadingSkeleton, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { getPaymentOrder, mockPayOrder } from "../services/payment";

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "SUCCESS") return "success";
  if (status === "FAIL" || status === "CLOSED") return "danger";
  if (status === "INIT") return "warning";
  return "neutral";
}

function statusText(status: string) {
  const map: Record<string, string> = {
    INIT: "等待支付",
    SUCCESS: "支付成功",
    FAIL: "支付失败",
    CLOSED: "订单已关闭",
  };
  return map[status] ?? status;
}

export function PaymentOrderPage() {
  const { orderNo = "" } = useParams();
  const { showToast } = useToast();

  const orderQuery = useQuery({
    queryKey: ["payment", "order", orderNo],
    queryFn: () => getPaymentOrder(orderNo),
    enabled: Boolean(orderNo),
    placeholderData: (previousData) => previousData,
    refetchInterval: (query) => (query.state.data?.status === "INIT" ? 2500 : false),
  });

  const order = orderQuery.data;

  const mockPayMutation = useMutation({
    mutationFn: () => mockPayOrder(orderNo, order?.amount ?? "0"),
    onSuccess: async () => {
      showToast({ tone: "success", title: "支付成功", description: "额度已发放到账户。" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["payment", "order", orderNo] }),
        queryClient.invalidateQueries({ queryKey: ["quota"] }),
        queryClient.invalidateQueries({ queryKey: ["user", "info"] }),
        queryClient.invalidateQueries({ queryKey: ["profile", "quota-logs"] }),
        queryClient.invalidateQueries({ queryKey: ["invite"] }),
      ]);
    },
    onError: (error) => {
      showToast({ tone: "error", title: "支付失败", description: error.message });
    },
  });

  return (
    <div className="page-stack">
      <div className="detail-topbar">
        <Link className="text-link detail-back" to="/payment">
          <ArrowLeft size={16} />
          返回套餐
        </Link>
        <Button
          type="button"
          variant="ghost"
          icon={<RefreshCw size={16} />}
          loading={orderQuery.isFetching && Boolean(order)}
          onClick={() => void orderQuery.refetch()}
        >
          刷新支付状态
        </Button>
      </div>

      {orderQuery.isFetching && !order ? (
        <Card>
          <LoadingSkeleton lines={8} />
        </Card>
      ) : order ? (
        <section className="payment-order-grid">
          <Card className="payment-order-card">
            <Badge tone={statusTone(order.status)}>{statusText(order.status)}</Badge>
            <h1>确认支付</h1>
            <p className="price">¥{order.amount}</p>
            <p className="muted-text">订单编号 {order.orderNo}</p>
            {order.paidAt ? <p className="muted-text">支付时间 {new Date(order.paidAt).toLocaleString()}</p> : null}
            {order.status === "SUCCESS" ? (
              <div className="success-panel">
                <CheckCircle2 size={26} />
                <div>
                  <strong>额度已到账</strong>
                  <p>现在可以继续上传素材，也可以在“我的”页面查看额度明细。</p>
                </div>
              </div>
            ) : (
              <Button type="button" loading={mockPayMutation.isPending} onClick={() => mockPayMutation.mutate()}>
                确认支付
              </Button>
            )}
          </Card>

          <Card title="扫码支付" eyebrow="支付方式">
            <div className="mock-qr">
              <QrCode size={72} />
              <span>{order.orderNo}</span>
            </div>
            <p className="muted-text">支付完成后，额度会自动加入你的账户。</p>
          </Card>
        </section>
      ) : (
        <EmptyState title="没有找到订单" description="请返回套餐页重新创建订单。" />
      )}
    </div>
  );
}
