import { FormEvent, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, Mail } from "lucide-react";
import { EmailCodeButton } from "../components/EmailCodeButton";

import { Button, Card, Input, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { login } from "../services/auth";
import { useAuthStore } from "../store/auth-store";
import { readUploadDraft, saveUploadDraft, clearUploadDraft } from "../lib/upload-draft";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const initialInviteCode = useMemo(() => searchParams.get("inviteCode") ?? "", [searchParams]);
  const { showToast } = useToast();
  const setLogin = useAuthStore((state) => state.setLogin);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [inviteCode, setInviteCode] = useState(initialInviteCode);

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: async (data) => {
      const draft = readUploadDraft();
      if (draft && (data.guestConverted || (!draft.ownerUid && draft.link && !draft.fileNo))) saveUploadDraft({ ownerUid: data.uid });
      else if (draft && draft.ownerUid !== data.uid) clearUploadDraft();
      queryClient.clear();
      setLogin(data);
      await queryClient.invalidateQueries({ queryKey: ["user", "info"] });
      showToast({ tone: "success", title: "登录成功", description: "欢迎回来，可以继续处理视频了。" });
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(from, { replace: true });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "登录失败", description: error.message });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ email: email.trim(), code: code.trim(), inviteCode: inviteCode.trim() || undefined });
  }

  return (
    <main className="login-page">
      <section className="login-hero">
        <div className="login-brand"><img className="app-brand-icon" src="/brand/video-to-text-icon-v1.png" alt="网络ASR" width="48" height="48" />
        <strong>网络ASR</strong></div>
        <h1>把声音，整理成文字。</h1>
        <p>上传本地音视频，或粘贴抖音分享链接。完成后直接查看完整文稿，适合整理课程、访谈、短视频和会议素材。</p>
        <Link className="text-link" to="/">先免注册体验</Link>
      </section>

      <Card className="login-card" eyebrow="邮箱验证登录 / 注册" title="进入我的工作台">
        <form className="login-form" onSubmit={handleSubmit}>
          <Input
            label="邮箱"
            type="email"
            name="email"
            autoComplete="email"
            maxLength={254}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="请输入邮箱地址"
            leftIcon={<Mail size={16} />}
            required
          />
          <EmailCodeButton email={email} />
          <Input
            label="验证码"
            name="code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            leftIcon={<KeyRound size={16} />}
            hint="验证码10分钟内有效，首次验证后自动注册。"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            required
          />
          <Input
            label="邀请码"
            name="inviteCode"
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value)}
            placeholder="有邀请码可填写"
          />
          <Button type="submit" size="lg" loading={mutation.isPending}>
            登录并继续
          </Button>
        </form>
      </Card>
    </main>
  );
}
