import { useEffect } from "react";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { ToastProvider, useToast } from "./components/ui";
import { SiteFooter } from "./components/SiteFooter";
import { AdminLayout } from "./layouts/AdminLayout";
import { MainLayout } from "./layouts/MainLayout";
import { queryClient } from "./lib/query-client";
import { AdminDashboardPage } from "./pages/admin/AdminDashboardPage";
import { AdminUsersPage } from "./pages/admin/AdminUsersPage";
import { AdminOrdersPage } from "./pages/admin/AdminOrdersPage";
import { AdminGuestsPage } from "./pages/admin/AdminGuestsPage";
import { AdminWithdrawalsPage } from "./pages/admin/AdminWithdrawalsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InvitePage } from "./pages/InvitePage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PaymentOrderPage } from "./pages/PaymentOrderPage";
import { PaymentPage } from "./pages/PaymentPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { TasksPage } from "./pages/TasksPage";
import { UploadPage } from "./pages/UploadPage";
import { RequireAdmin, RequireAuth, RequireMember } from "./router/guards";
import { getUserInfo } from "./services/auth";
import { useAuthStore } from "./store/auth-store";
import { getGuestSession } from "./services/guest";
import { GuestPrompt } from "./components/GuestPrompt";

function HomePage() {
  const token = useAuthStore((state) => state.token);
  return token ? <DashboardPage /> : <UploadPage publicHome />;
}

function AuthBootstrap() {
  const token = useAuthStore((state) => state.token);
  const setUser = useAuthStore((state) => state.setUser);
  const guest = useAuthStore((state) => state.user?.guest);
  const ready = useAuthStore((state) => state.setSessionReady);
  const session = useQuery({ queryKey: ["auth", "guest-session"], queryFn: getGuestSession, enabled: !token, retry: false });

  const userQuery = useQuery({
    queryKey: ["user", "info"],
    queryFn: getUserInfo,
    enabled: Boolean(token || guest),
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (userQuery.data) {
      setUser(userQuery.data);
    }
  }, [setUser, userQuery.data]);
  useEffect(() => {
    if (!token && session.isFetched) { setUser(session.data ?? null); ready(); }
    if (token) ready();
  }, [token, session.isFetched, session.data, setUser, ready]);

  return null;
}

function AuthExpiredListener() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  useEffect(() => {
    function handleExpired() {
      showToast({ tone: "warning", title: "登录状态已过期", description: "请重新登录后继续使用。" });
      navigate("/login", { replace: true });
    }
    window.addEventListener("auth:expired", handleExpired);
    function handleQuota() {
      showToast({ tone: "warning", title: "额度不足", description: "请前往购买额度页面选择支付宝套餐。" });
      navigate("/payment");
    }
    window.addEventListener("quota:insufficient", handleQuota);
    return () => {
      window.removeEventListener("auth:expired", handleExpired);
      window.removeEventListener("quota:insufficient", handleQuota);
    };
  }, [navigate, showToast]);

  return null;
}

function AppRoutes() {
  return (
    <>
      <AuthBootstrap />
      <AuthExpiredListener />
      <GuestPrompt />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <MainLayout />
          }
        >
          <Route index element={<HomePage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="tasks" element={<RequireAuth><TasksPage /></RequireAuth>} />
          <Route path="tasks/:taskNo" element={<RequireAuth><TaskDetailPage /></RequireAuth>} />
          <Route path="payment" element={<PaymentPage />} />
          <Route path="payment/order/:orderNo" element={<RequireMember><PaymentOrderPage /></RequireMember>} />
          <Route path="pricing" element={<Navigate to="/payment" replace />} />
          <Route path="invite" element={<RequireMember><InvitePage /></RequireMember>} />
          <Route path="profile" element={<RequireMember><ProfilePage /></RequireMember>} />
        </Route>
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <RequireAdmin>
                <AdminLayout />
              </RequireAdmin>
            </RequireAuth>
          }
        >
          <Route index element={<AdminDashboardPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="orders" element={<AdminOrdersPage />} />
          <Route path="guests" element={<AdminGuestsPage />} />
          <Route path="withdrawals" element={<AdminWithdrawalsPage />} />
        </Route>
        <Route path="/404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
      <SiteFooter />
    </>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
