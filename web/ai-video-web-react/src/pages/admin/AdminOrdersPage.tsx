import { useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, Modal } from "../../components/ui";
import { getAdminOrders } from "../../services/admin";
import type { AdminOrder } from "../../types/api";

const statuses = [
  ["ALL", "全部"], ["PAID", "已付款"], ["PENDING", "待付款"], ["UNKNOWN", "待核验"],
  ["REFUNDED", "已退款"], ["FAILED", "失败"], ["CLOSED", "已关闭"],
];
function date(value?: string | null) { return value ? new Date(value).toLocaleString("zh-CN") : "-"; }
function amount(value: string | null) { return value === null ? "-" : `¥${Number(value).toFixed(2)}`; }
function statusLabel(value: string) { return statuses.find(([status]) => status === value)?.[1] ?? value; }
function sourceLabel(value: string) { return value === "OPCPAY" ? "一人付" : "历史订单"; }
function tone(value: string): "success" | "warning" | "danger" | "neutral" {
  return value === "PAID" ? "success" : value === "PENDING" || value === "UNKNOWN" ? "warning" : value === "FAILED" ? "danger" : "neutral";
}

export function AdminOrdersPage() {
  const [input, setInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("ALL");
  const [source, setSource] = useState("ALL");
  const [pageNo, setPageNo] = useState(1);
  const [selected, setSelected] = useState<AdminOrder | null>(null);
  const orders = useQuery({ queryKey: ["admin", "orders", { keyword, status, source, pageNo }],
    queryFn: () => getAdminOrders({ keyword, status, source, pageNo, pageSize: 20 }),
    placeholderData: (previous) => previous, refetchOnWindowFocus: true });
  function search(event: FormEvent) { event.preventDefault(); setKeyword(input.trim()); setPageNo(1); }
  return <div className="page-stack admin-page">
    <div className="page-heading admin-heading"><div><p className="eyebrow">支付管理</p><h1>全部订单</h1>
      <p>查看资源包购买及历史订单，付款状态以服务端核验结果为准。</p></div>
      <Button variant="ghost" icon={<RefreshCw size={16} />} loading={orders.isFetching} onClick={() => void orders.refetch()}>刷新订单</Button></div>
    <Card className="admin-table-card">
      <div className="status-tabs">{statuses.map(([value, label]) => <Button key={value} size="sm"
        variant={status === value ? "secondary" : "ghost"} onClick={() => { setStatus(value); setPageNo(1); }}>{label}</Button>)}</div>
      <div className="admin-toolbar admin-toolbar--wide">
        <div className="status-tabs">{[["ALL", "全部来源"], ["OPCPAY", "一人付"], ["LEGACY", "历史订单"]].map(([value, label]) =>
          <Button key={value} size="sm" variant={source === value ? "secondary" : "ghost"} onClick={() => { setSource(value); setPageNo(1); }}>{label}</Button>)}</div>
        <form className="admin-search-form" onSubmit={search}><Input value={input} onChange={(event) => setInput(event.target.value)}
          placeholder="订单号 / 邮箱 / UID / 昵称 / 套餐" leftIcon={<Search size={16} />} /><Button type="submit" variant="secondary">搜索</Button></form>
      </div>
      {orders.isError ? <p className="error-text">订单读取失败，请刷新重试。</p> : null}
      {orders.isFetching && !orders.data ? <LoadingSkeleton lines={8} /> : orders.data?.records.length ? <div className="admin-table-wrap">
        <table className="admin-table"><thead><tr><th>订单</th><th>用户</th><th>套餐</th><th>金额</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>{orders.data.records.map((order) => <tr key={`${order.source}:${order.orderNo}`}>
            <td><strong>{order.orderNo}</strong><span>{sourceLabel(order.source)}</span></td>
            <td><strong>{order.nickname || order.email || order.userUid || "用户已删除"}</strong><span>{order.email || order.userUid || "-"}</span></td>
            <td>{order.productName}</td><td>{amount(order.amount)}</td><td><Badge tone={tone(order.status)}>{statusLabel(order.status)}</Badge></td>
            <td>{date(order.createdAt)}</td><td><Button size="sm" variant="ghost" onClick={() => setSelected(order)}>详情</Button></td>
          </tr>)}</tbody></table></div> : !orders.isError ? <EmptyState title="暂无订单" description="可调整筛选条件，或等待用户创建购买订单。" /> : null}
      {orders.data ? <div className="admin-row-actions"><span>共 {orders.data.total} 笔 · 第 {orders.data.pageNo} 页</span>
        <Button size="sm" variant="ghost" disabled={orders.isFetching || pageNo <= 1} onClick={() => setPageNo((page) => page - 1)}>上一页</Button>
        <Button size="sm" variant="ghost" disabled={orders.isFetching || !orders.data.hasMore} onClick={() => setPageNo((page) => page + 1)}>下一页</Button></div> : null}
    </Card>
    <Modal open={Boolean(selected)} title="订单详情" onClose={() => setSelected(null)}>
      {selected ? <div className="admin-kv-list">
        <span>订单号</span><strong style={{ overflowWrap: "anywhere" }}>{selected.orderNo}</strong>
        <span>用户</span><strong>{selected.email || selected.userUid || "用户已删除"}</strong>
        <span>来源</span><strong>{sourceLabel(selected.source)}</strong>
        <span>套餐</span><strong>{selected.productName}</strong>
        <span>订单金额</span><strong>{amount(selected.amount)}</strong>
        <span>套餐额度</span><strong>{selected.quantity === null ? "-" : `${selected.quantity.toLocaleString()} 点`}</strong>
        <span>状态</span><strong>{statusLabel(selected.status)}</strong>
        <span>创建时间</span><strong>{date(selected.createdAt)}</strong>
        <span>付款确认时间</span><strong>{date(selected.paymentConfirmedAt)}</strong>
        <span>最近核验时间</span><strong>{date(selected.checkedAt)}</strong>
      </div> : null}
    </Modal>
  </div>;
}
