import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button, useToast } from "./ui";
import { sendEmailCode } from "../services/auth";

export function EmailCodeButton({ email }: { email: string }) {
  const [remaining, setRemaining] = useState(0);
  const { showToast } = useToast();
  useEffect(() => {
    if (!remaining) return;
    const timer = window.setTimeout(() => setRemaining((n) => Math.max(0, n - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [remaining]);
  const send = useMutation({ mutationFn: sendEmailCode,
    onSuccess: (data) => { setRemaining(data.retryAfter); showToast({ tone: "success", title: "验证码已发送", description: "请查收邮件，也可检查垃圾邮件文件夹。" }); },
    onError: (error) => showToast({ tone: "error", title: "邮件发送失败", description: error.message }) });
  return <Button type="button" variant="secondary" loading={send.isPending} disabled={!email.trim() || remaining > 0}
    onClick={() => send.mutate(email.trim())}>{remaining ? `${remaining} 秒后重发` : "发送邮箱验证码"}</Button>;
}
