import { Link, NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { Crown, FileText, Home, UploadCloud, UserRound, WalletCards, Rocket } from "lucide-react";

import { Badge, Button } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { useAuthStore } from "../store/auth-store";
import { readUploadDraft } from "../lib/upload-draft";
import { logout } from "../services/auth";

const navItems = [
  { to: "/", label: "首页", icon: Home },
  { to: "/upload", label: "开始提取", icon: UploadCloud },
  { to: "/tasks", label: "处理记录", icon: FileText },
  { to: "/payment", label: "购买额度", icon: WalletCards },
  { to: "/invite", label: "邀请返现", icon: Crown },
  { to: "/profile", label: "我的", icon: UserRound },
];

export function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const logoutLocal = useAuthStore((state) => state.logoutLocal);
  const token = useAuthStore((state) => state.token);
  const draft = readUploadDraft();

  async function handleLogout() {
    try { await logout(); } finally {
      logoutLocal(); queryClient.clear(); navigate("/", { replace: true });
    }
  }

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand">
          <img className="app-brand-icon" src="/brand/video-to-text-icon-v1.png" alt="网络ASR" width="48" height="48" />
          <div>
            <strong>网络ASR</strong>
            <span>把声音整理成文稿</span>
          </div>
        </div>

        <nav>
          {navItems.filter((item) => token || !["/invite", "/profile"].includes(item.to)).map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}>
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
          {user?.admin ? (
            <NavLink to="/admin">
              <Rocket size={18} />
              <span>后台管理</span>
            </NavLink>
          ) : null}
        </nav>

        <div className="side-nav__footer">
          <Badge tone="info">{user ? `${user.remainingPoints} 点${user.guest ? "体验额度" : "额度"}` : "免注册体验"}</Badge>
          {token ? <Button type="button" variant="ghost" size="sm" onClick={() => void handleLogout().catch(() => undefined)}>退出</Button>
            : <Button variant="secondary" size="sm" onClick={() => navigate("/login", { state: { from: draft?.fileNo ? "/upload?resume=1" : draft?.link ? "/upload?mode=link" : location.pathname + location.search } })}>登录 / 注册</Button>}
        </div>
      </aside>

      <main className="app-main">
        {draft?.fileNo && draft.ownerUid === user?.uid ? <p><Link className="text-link" to="/upload?resume=1">继续处理已上传的素材</Link></p> : null}
        <Outlet />
      </main>
    </div>
  );
}
