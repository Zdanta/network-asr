import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuthStore } from "../store/auth-store";

export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const token = useAuthStore((state) => state.token);
  const guest = useAuthStore((state) => state.user?.guest);
  const ready = useAuthStore((state) => state.sessionReady);
  if (!token && !ready) return <p>正在恢复体验…</p>;
  if (!token && !guest) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export function RequireMember({ children }: { children: ReactNode }) {
  const location = useLocation();
  const token = useAuthStore((state) => state.token);
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user);
  if (!user?.admin) {
    return <Navigate to="/" replace />;
  }
  return children;
}
