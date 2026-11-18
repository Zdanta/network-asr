import type { ReactNode } from "react";
import { useCallback, useMemo, useState } from "react";
import { CheckCircle2, Info, TriangleAlert, XCircle } from "lucide-react";

import { ToastContext, type ToastMessage, type ToastTone } from "./toast-context";

const icons: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 size={18} />,
  error: <XCircle size={18} />,
  info: <Info size={18} />,
  warning: <TriangleAlert size={18} />,
};

let toastSequence = 0;

function createToastId() {
  if (
    typeof globalThis.crypto !== "undefined" &&
    typeof globalThis.crypto.randomUUID === "function"
  ) {
    return globalThis.crypto.randomUUID();
  }

  toastSequence += 1;
  return `toast-${Date.now()}-${toastSequence}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const showToast = useCallback((toast: Omit<ToastMessage, "id">) => {
    const id = createToastId();
    setMessages((items) => [...items, { ...toast, id }]);
    window.setTimeout(() => {
      setMessages((items) => items.filter((item) => item.id !== id));
    }, 3600);
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-stack" aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`ui-toast ui-toast--${message.tone}`}>
            <span className="ui-toast__icon">{icons[message.tone]}</span>
            <div>
              <strong>{message.title}</strong>
              {message.description ? <p>{message.description}</p> : null}
            </div>
          </article>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
