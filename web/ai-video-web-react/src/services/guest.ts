import { api } from "../lib/api-client";
import { queryClient } from "../lib/query-client";
import { useAuthStore } from "../store/auth-store";
import type { UserInfo } from "../types/api";

export type Experience = { enabled: boolean; points: number; secondsPerPoint: number; uploadMb: number; sessionDays: number };
export const getExperience = () => api.get<Experience>("/public/experience");
export const getGuestSession = () => api.get<UserInfo | null>("/auth/guest-session");
let creating: Promise<void> | null = null;
export async function ensureExperience() {
  if (useAuthStore.getState().token || useAuthStore.getState().user?.guest) return;
  if (!creating) creating = (async () => {
    const existing = await queryClient.ensureQueryData({ queryKey: ["auth", "guest-session"], queryFn: getGuestSession });
    let user = existing;
    if (!user) {
      let device = localStorage.getItem("asr-device");
      if (!device) { device = crypto.randomUUID(); localStorage.setItem("asr-device", device); }
      user = await api.post<UserInfo>("/auth/guest", { deviceId: device });
    }
    useAuthStore.getState().setUser(user);
    useAuthStore.getState().setSessionReady();
    queryClient.setQueryData(["auth", "guest-session"], user);
  })().finally(() => { creating = null; });
  return creating;
}
