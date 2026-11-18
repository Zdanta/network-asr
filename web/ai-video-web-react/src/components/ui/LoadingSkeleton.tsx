import { clsx } from "clsx";

type LoadingSkeletonProps = {
  lines?: number;
  className?: string;
};

export function LoadingSkeleton({ lines = 3, className }: LoadingSkeletonProps) {
  return (
    <div className={clsx("ui-skeleton", className)} aria-label="加载中">
      {Array.from({ length: lines }).map((_, index) => (
        <span key={index} className="ui-skeleton__line" style={{ width: `${92 - index * 12}%` }} />
      ))}
    </div>
  );
}
