import type { InputHTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
};

export function Input({ className, label, hint, error, leftIcon, id, ...props }: InputProps) {
  const inputId = id ?? props.name;
  return (
    <label className="ui-field" htmlFor={inputId}>
      {label ? <span className="ui-field__label">{label}</span> : null}
      <span className={clsx("ui-input-wrap", error && "ui-input-wrap--error", className)}>
        {leftIcon ? <span className="ui-input-wrap__icon">{leftIcon}</span> : null}
        <input id={inputId} className="ui-input" {...props} />
      </span>
      {error ? <span className="ui-field__error">{error}</span> : hint ? <span className="ui-field__hint">{hint}</span> : null}
    </label>
  );
}
