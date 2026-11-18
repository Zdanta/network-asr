import { useAuthStore } from "../store/auth-store";
import type { ApiEnvelope } from "../types/api";
import { ApiError } from "./api-error";
import { queryClient } from "./query-client";

const API_PREFIX = "/api/v1";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

function toChineseApiMessage(message: string | undefined, status: number, code: number) {
  const value = (message || "").trim();
  if (!value) return "操作失败，请稍后重试";
  if (!/[A-Za-z]/.test(value)) return value;

  const lower = value.toLowerCase();
  if (lower.includes("first recharge gift")) return "首充礼包仅限首次支付前购买";
  if (lower.includes("insufficient points")) return "额度不足，请先购买额度";
  if (lower.includes("not found")) return "记录不存在或无权访问";
  if (lower.includes("invalid")) return "请求参数不正确，请检查后重试";
  if (lower.includes("timeout")) return "请求超时，请稍后重试";
  if (lower.includes("network")) return "网络异常，请稍后重试";
  if (lower.includes("internal server error")) return "服务暂时不可用，请稍后重试";
  if (lower.includes("bad gateway") || lower.includes("service unavailable")) return "服务暂时不可用，请稍后重试";
  if (status === 401 || code === 1002) return "登录状态已过期，请重新登录";
  if (status === 403 || code === 1003) return "没有权限执行此操作";
  if (status === 404) return "记录不存在或无权访问";
  if (status >= 500) return "服务暂时不可用，请稍后重试";
  return "操作失败，请稍后重试";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (token) {
    headers.set("satoken", token);
  }

  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...options,
    headers,
    body,
  });

  const text = await response.text();
  const envelope = text ? (JSON.parse(text) as ApiEnvelope<T>) : null;

  if (!response.ok || !envelope || envelope.code !== 0) {
    const code = envelope?.code ?? response.status;
    const message = toChineseApiMessage(envelope?.message ?? response.statusText, response.status, code);
    if (code === 2101) window.dispatchEvent(new CustomEvent("guest:required", { detail: message }));
    if (code === 2001) window.dispatchEvent(new CustomEvent("quota:insufficient"));
    if (response.status === 401 || code === 1002) {
      const wasGuest = useAuthStore.getState().user?.guest;
      useAuthStore.getState().logoutLocal();
      queryClient.clear();
      window.dispatchEvent(new CustomEvent(wasGuest ? "guest:required" : "auth:expired", { detail: "体验身份已过期，请登录后继续" }));
    }
    throw new ApiError(message, code, response.status);
  }

  return envelope.data;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "DELETE" }),
};
