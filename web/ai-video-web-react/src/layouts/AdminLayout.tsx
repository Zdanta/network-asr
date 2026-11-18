import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { ArrowLeft, BarChart3, HandCoins, UsersRound, WalletCards } from "lucide-react";

import { Button } from "../components/ui";

const adminNav = [
  { to: "/admin", label: "经营概览", icon: BarChart3 },
  { to: "/admin/users", label: "用户积分", icon: UsersRound },
  { to: "/admin/orders", label: "全部订单", icon: WalletCards },
  { to: "/admin/guests", label: "访客体验", icon: UsersRound },
  { to: "/admin/withdrawals", label: "提现处理", icon: HandCoins },
];

export function AdminLayout() {
  const navigate = useNavigate();
  return (
    <div className="admin-shell">
      <aside className="admin-nav">
        <Button type="button" variant="ghost" size="sm" icon={<ArrowLeft size={16} />} onClick={() => navigate("/")}>
          返回前台
        </Button>
        <div className="admin-nav__title">
          <img className="app-brand-icon" src="/brand/video-to-text-icon-v1.png" alt="网络ASR" width="48" height="48" />
          <span>管理控制台</span>
          <strong>网络ASR 管理后台</strong>
        </div>
        <nav>
          {adminNav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.to === "/admin"}>
                <Icon size={18} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <main className="admin-frame">
        <Outlet />
      </main>
    </div>
  );
}
