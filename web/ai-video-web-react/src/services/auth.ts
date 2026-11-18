import { api } from "../lib/api-client";
import type { LoginPayload, LoginResult, UserInfo } from "../types/api";

export function login(payload: LoginPayload) {
  return api.post<LoginResult>("/auth/login", payload);
}

export const sendEmailCode = (email: string) => api.post<{ sent: boolean; retryAfter: number; expiresIn: number }>("/auth/email-code", { email });
export const bindEmail = (email: string, code: string) => api.post<{ email: string }>("/auth/bind-email", { email, code });

export function logout() {
  return api.post<{ ok?: boolean }>("/auth/logout");
}

export function getUserInfo() {
  return api.get<UserInfo>("/user/info");
}
