import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CreditCard, RefreshCw, UsersRound, WalletCards } from "lucide-react";

import { Badge, Button, Card, LoadingSkeleton } from "../../components/ui";
import { getAdminDashboardOverview } from "../../services/admin";
import { Link } from "react-router-dom";

function money(value?: string | number | null) {
  return Number(value ?? 0).toFixed(2);
}

export function AdminDashboardPage() {
  const overviewQuery = useQuery({
    queryKey: ["admin", "dashboard", "overview"],
    queryFn: getAdminDashboardOverview,
  });
  const overview = overviewQuery.data;

  const metrics = [
    { label: "总用户", value: overview?.totalUsers ?? 0, sub: `今日新增 ${overview?.todayNewUsers ?? 0}`, icon: UsersRound },
    { label: "今日任务", value: overview?.todayTasks ?? 0, sub: `成功 ${overview?.todaySuccessTasks ?? 0} / 失败 ${overview?.todayFailTasks ?? 0}`, icon: CreditCard },
    { label: "今日确认支付", value: overview?.todayPaidOrders ?? 0, sub: `¥${money(overview?.todayPaidAmount)}`, icon: WalletCards },
    { label: "待处理提现", value: overview?.pendingWithdrawals ?? 0, sub: `¥${money(overview?.pendingWithdrawalAmount)}`, icon: AlertTriangle },
  ];

  return (
    <div className="page-stack admin-page">
      <div className="page-heading admin-heading">
        <div>
          <p className="eyebrow">管理概览</p>
          <h1>经营概览</h1>
          <p>查看用户、任务及支付情况。支付按北京时间的付款核验日期统计。</p>
          <Link to="/admin/orders">查看全部订单</Link>
        </div>
        <Button
          type="button"
          variant="ghost"
          icon={<RefreshCw size={16} />}
          loading={overviewQuery.isFetching}
          onClick={() => void overviewQuery.refetch()}
        >
          刷新概览
        </Button>
      </div>

      {overviewQuery.isError ? <p className="error-text">概览读取失败，请刷新重试。</p> : null}

      <div className="admin-metric-grid">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <Card key={metric.label} className="admin-metric-card">
              <div>
                <Icon size={18} />
                <span>{metric.label}</span>
              </div>
              {overviewQuery.isFetching && !overview ? (
                <LoadingSkeleton lines={2} />
              ) : (
                <>
                  <strong>{metric.value}</strong>
                  <p>{metric.sub}</p>
                </>
              )}
            </Card>
          );
        })}
      </div>

      <section className="admin-dense-grid">
        <Card title="任务风险" eyebrow="任务">
          <div className="admin-kv-list">
            <span>失败任务总量</span>
            <strong>{overview?.pendingFailTasks ?? 0}</strong>
            <span>今日成功率</span>
            <strong>
              {overview && overview.todayTasks > 0
                ? `${Math.round((overview.todaySuccessTasks / overview.todayTasks) * 100)}%`
                : "-"}
            </strong>
          </div>
        </Card>
        <Card title="提现队列" eyebrow="提现">
          <div className="admin-kv-list">
            <span>待处理笔数</span>
            <strong>{overview?.pendingWithdrawals ?? 0}</strong>
            <span>待处理金额</span>
            <strong>¥{money(overview?.pendingWithdrawalAmount)}</strong>
          </div>
          <Badge tone={(overview?.pendingWithdrawals ?? 0) > 0 ? "warning" : "success"}>
            {(overview?.pendingWithdrawals ?? 0) > 0 ? "需要处理" : "队列清爽"}
          </Badge>
        </Card>
      </section>
    </div>
  );
}
