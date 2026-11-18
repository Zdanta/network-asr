import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

import { Button } from "./Button";

type EmptyStateProps = {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: ReactNode;
};

export function EmptyState({ title, description, actionLabel, onAction, icon }: EmptyStateProps) {
  return (
    <div className="ui-empty">
      <div className="ui-empty__icon">{icon ?? <Sparkles size={24} />}</div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {actionLabel ? (
        <Button variant="secondary" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
