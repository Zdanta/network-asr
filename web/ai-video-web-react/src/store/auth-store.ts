import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { LoginResult, UserInfo } from "../types/api";

type AuthSnapshot = {
  token: string | null;
  user: UserInfo | null;
};

type AuthState = AuthSnapshot & {
  isAuthenticated: boolean;
  sessionReady: boolean;
  setSessionReady: () => void;
  setLogin: (login: LoginResult) => void;
  setUser: (user: UserInfo | null) => void;
  logoutLocal: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      sessionReady: false,
      setSessionReady: () => set({ sessionReady: true }),
      setLogin: (login) =>
        set({
          token: login.token,
          user: {
            uid: login.uid,
            userId: login.userId,
            mobile: login.mobile,
            email: login.email,
            nickname: login.nickname,
            inviteCode: login.inviteCode,
            remainingPoints: login.remainingPoints,
            remainingCount: login.remainingCount ?? login.remainingPoints,
            admin: Boolean(login.admin),
          },
          isAuthenticated: true,
          sessionReady: true,
        }),
      setUser: (user) => set((state) => ({ user, isAuthenticated: Boolean(state.token && user) })),
      logoutLocal: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    {
      name: "ai-video-auth",
      partialize: (state): AuthSnapshot => ({ token: state.token, user: state.token ? state.user : null }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isAuthenticated = Boolean(state.token);
        }
      },
    },
  ),
);
