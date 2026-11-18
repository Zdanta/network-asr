import { Link } from "react-router-dom";

import { Button, EmptyState } from "../components/ui";

export function NotFoundPage() {
  return (
    <div className="center-page">
      <EmptyState title="页面走丢了" description="这个页面暂时不存在，先回到首页继续处理素材吧。" />
      <Link to="/">
        <Button>回到首页</Button>
      </Link>
    </div>
  );
}
