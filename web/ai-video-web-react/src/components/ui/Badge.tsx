import type { HTMLAttributes } from "react";
import { clsx } from "clsx";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ className, tone = "neutral", children, ...props }: BadgeProps) {
  return (
    <span className={clsx("ui-badge", `ui-badge--${tone}`, className)} {...props}>
      {children}
    </span>
  );
}
