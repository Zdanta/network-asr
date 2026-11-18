import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button, Card, Input, useToast } from "./ui";
import { EmailCodeButton } from "./EmailCodeButton";
import { bindEmail } from "../services/auth";
import { queryClient } from "../lib/query-client";

export function BindEmailCard() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const { showToast } = useToast();
  const mutation = useMutation({ mutationFn: () => bindEmail(email.trim(), code.trim()),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["user", "info"] }); showToast({ tone: "success", title: "邮箱已绑定", description: "以后可使用邮箱验证码登录原账号。" }); },
    onError: (error) => showToast({ tone: "error", title: "绑定失败", description: error.message }) });
  return <Card title="为原账号绑定邮箱" eyebrow="保留历史数据"><p>验证邮箱后，继续使用原账号的积分、素材和邀请记录。</p>
    <form className="login-form" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <Input type="email" label="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} />
      <EmailCodeButton email={email} />
      <Input label="邮箱验证码" value={code} onChange={(e) => setCode(e.target.value)} pattern="[0-9]{6}" maxLength={6} required />
      <Button type="submit" loading={mutation.isPending}>验证并绑定邮箱</Button>
    </form></Card>;
}
