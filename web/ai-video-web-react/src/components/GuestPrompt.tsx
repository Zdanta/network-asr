import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, Modal } from "./ui";
import { readUploadDraft } from "../lib/upload-draft";

export function GuestPrompt() {
  const [message, setMessage] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const listener = (event: Event) => setMessage((event as CustomEvent<string>).detail || "体验额度不足，请登录后继续。");
    window.addEventListener("guest:required", listener);
    return () => window.removeEventListener("guest:required", listener);
  }, []);
  function login(purchase: boolean) {
    setMessage("");
    const draft = readUploadDraft();
    const resume = draft?.fileNo ? "/upload?resume=1" : draft?.link ? "/upload?mode=link" : location.pathname + location.search;
    navigate("/login", { state: { from: purchase ? "/payment" : resume } });
  }
  return <Modal open={Boolean(message)} title="继续整理你的素材" onClose={() => setMessage("")}
    footer={<><Button variant="ghost" onClick={() => setMessage("")}>稍后再说</Button>
      <Button variant="secondary" onClick={() => login(false)}>登录 / 注册</Button><Button onClick={() => login(true)}>登录并购买额度</Button></>}>
    <p>{message}</p><p className="muted-text">已上传的素材会暂时保留；新邮箱注册后继承剩余体验额度，不重复赠送。</p>
  </Modal>;
}
