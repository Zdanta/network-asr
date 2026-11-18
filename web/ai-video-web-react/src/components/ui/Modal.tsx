import type { ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "./Button";

type ModalProps = {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
};

export function Modal({ open, title, children, footer, onClose }: ModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="ui-modal" role="dialog" aria-modal="true" aria-label={title}>
      <div className="ui-modal__backdrop" onClick={onClose} />
      <section className="ui-modal__panel">
        <header className="ui-modal__header">
          <h2>{title}</h2>
          <Button type="button" variant="ghost" size="sm" icon={<X size={16} />} onClick={onClose} aria-label="关闭">
            关闭
          </Button>
        </header>
        <div className="ui-modal__body">{children}</div>
        {footer ? <footer className="ui-modal__footer">{footer}</footer> : null}
      </section>
    </div>
  );
}
