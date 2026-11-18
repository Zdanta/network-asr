import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Check, Sparkles, WalletCards } from "lucide-react";

import { Badge, Button, Card, useToast } from "../components/ui";
import { createPaymentOrder } from "../services/payment";
import type { PaymentProductType } from "../types/api";
import { getOpcpayCatalog } from "../services/opcpay";
import { OpcpayPayment } from "./OpcpayPayment";
import { useAuthStore } from "../store/auth-store";
import { getQuota } from "../services/quota";
import { api } from "../lib/api-client";
import type { OpcpayCatalog } from "../services/opcpay";
import { getExperience } from "../services/guest";

const paymentPlans: Array<{
  productType: PaymentProductType;
  name: string;
  price: string;
  points: number;
  tone: "success" | "info" | "warning";
  highlight: string;
  features: string[];
}> = [
  {
    productType: "FIRST_RECHARGE_GIFT",
    name: "体验包",
    price: "9.90",
    points: 1000,
    tone: "success",
    highlight: "首次购买推荐",
    features: ["适合先体验完整流程", "上传和抖音链接都可用", "支付成功后立即到账"],
  },
  {
    productType: "POINT_PACK",
    name: "日常包",
    price: "19.90",
    points: 1100,
    tone: "info",
    highlight: "轻量整理",
    features: ["适合日常短视频和课程整理", "可查看每次消耗明细", "余额不足时会提前提醒"],
  },
  {
    productType: "POINT_PACK_PLUS",
    name: "高阶包",
    price: "59.90",
    points: 3500,
    tone: "warning",
    highlight: "更适合批量处理",
    features: ["适合批量整理素材", "单次购买额度更多", "邀请好友还能获得返现"],
  },
];

export function PaymentPage() {
  const token = useAuthStore((state) => state.token);
  return token ? <MemberPaymentPage /> : <PublicPlansPage />;
}

function PublicPlansPage() {
  const navigate = useNavigate();
  const catalog = useQuery({ queryKey: ["public", "catalog"], queryFn: () => api.get<OpcpayCatalog>("/public/catalog") });
  const experience = useQuery({ queryKey: ["public", "experience"], queryFn: getExperience });
  return <div className="page-stack"><section className="commerce-hero"><div><Badge tone="success">选择适合你的额度</Badge><h1>购买额度</h1><p>先体验提取效果，需要更多额度时再登录购买。</p></div></section>
    {catalog.isError ? <Card><p>套餐暂时无法读取</p><Button loading={catalog.isFetching} onClick={() => void catalog.refetch()}>重试</Button></Card>
      : catalog.data?.enabled ? <div className="pricing-grid">{catalog.data.plans.map((plan) => <Card key={plan.skuId} className="pricing-card payment-plan-card">
        <Badge tone="success">支付宝积分包</Badge><h2>{plan.name}</h2><p className="price">¥{plan.price}</p><div><p>{plan.quantity.toLocaleString()} 点额度</p>
          {experience.data ? <p className="muted-text">约可处理 {(plan.quantity * experience.data.secondsPerPoint / 60).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 分钟音频</p> : null}</div>
        <Button onClick={() => { sessionStorage.setItem("asr-selected-sku", plan.skuId); navigate("/login", { state: { from: "/payment" } }); }}>登录后购买</Button>
      </Card>)}</div> : <Card><p>{catalog.isFetching ? "正在读取套餐…" : "套餐暂未开放，请稍后再试。"}</p></Card>}
  </div>;
}

function MemberPaymentPage() {
  const uid = useAuthStore((state) => state.user?.uid);
  const catalog = useQuery({ queryKey: ["opcpay", "catalog", uid], queryFn: getOpcpayCatalog });
  const quota = useQuery({ queryKey: ["quota", uid], queryFn: getQuota });
  const secondsPerPoint = quota.data?.secondsPerPoint;
  if (catalog.data?.enabled) return <OpcpayPayment catalog={catalog.data} secondsPerPoint={secondsPerPoint} />;
  if (catalog.data && !catalog.data.enabled) return <LegacyPaymentPage secondsPerPoint={secondsPerPoint} />;
  return <Card><h2>购买额度</h2><p>{catalog.isError ? "套餐暂时无法读取，请稍后重试。" : "正在读取可用套餐…"}</p>
    <Button loading={catalog.isFetching} onClick={() => void catalog.refetch()}>刷新套餐</Button></Card>;
}

function LegacyPaymentPage({ secondsPerPoint }: { secondsPerPoint?: number }) {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const createOrderMutation = useMutation({
    mutationFn: createPaymentOrder,
    onSuccess: (order) => {
      showToast({ tone: "success", title: "订单已创建", description: "请继续完成支付。" });
      navigate(`/payment/order/${order.orderNo}`);
    },
    onError: (error) => {
      showToast({ tone: "error", title: "创建订单失败", description: error.message });
    },
  });

  return (
    <div className="page-stack">
      <section className="commerce-hero">
        <div>
          <Badge tone="success">购买额度</Badge>
          <h1>为接下来的视频整理准备好额度。</h1>
          <p>选择适合的套餐。提交素材前会先预估所需额度，余额不足时不会开始处理，避免产生不必要的等待。</p>
        </div>
        <WalletCards size={46} />
      </section>

      <div className="pricing-grid">
        {paymentPlans.map((plan) => (
          <Card key={plan.productType} className="pricing-card payment-plan-card">
            <div className="payment-plan-card__top">
              <Badge tone={plan.tone}>{plan.highlight}</Badge>
              <Sparkles size={20} />
            </div>
            <div>
              <h2>{plan.name}</h2>
              <p className="price">¥{plan.price}</p>
              <p className="muted-text">{plan.points.toLocaleString()} 点额度</p>
              {secondsPerPoint && secondsPerPoint > 0 ? <p className="muted-text">约可处理 {(plan.points * secondsPerPoint / 60).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 分钟音频</p> : null}
            </div>
            <ul className="feature-list">
              {plan.features.map((feature) => (
                <li key={feature}>
                  <Check size={15} />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant={plan.productType === "POINT_PACK_PLUS" ? "secondary" : "primary"}
              loading={createOrderMutation.isPending && createOrderMutation.variables === plan.productType}
              onClick={() => createOrderMutation.mutate(plan.productType)}
            >
              选择这个套餐
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}
