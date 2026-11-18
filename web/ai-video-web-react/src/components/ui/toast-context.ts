import { createContext } from "react";

export type ToastTone = "success" | "error" | "info" | "warning";

export type ToastMessage = {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
};

export type ToastContextValue = {
  showToast: (toast: Omit<ToastMessage, "id">) => void;
};

export const ToastContext = createContext<ToastContextValue | null>(null);
