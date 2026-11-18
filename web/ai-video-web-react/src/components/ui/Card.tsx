import type { HTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
};

export function Card({ className, title, eyebrow, action, children, ...props }: CardProps) {
  return (
    <section className={clsx("ui-card", className)} {...props}>
      {(title || eyebrow || action) && (
        <header className="ui-card__header">
          <div>
            {eyebrow ? <p className="ui-card__eyebrow">{eyebrow}</p> : null}
            {title ? <h2 className="ui-card__title">{title}</h2> : null}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
