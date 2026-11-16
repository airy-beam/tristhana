import { useId, type ReactNode } from "react";

import "./form.css";

interface Props {
  /** "More options". */
  label: string;
  /** One line saying what is set inside; shown while closed. */
  summary?: string | undefined;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}

/** The rarely needed part of a form, folded under one list row (UI-06 stage 4). Closed, the
 * row says in one line what is set there; its fields are not in the page, so they take no part
 * in the form's own validation. */
export function More({ label, summary, open, onToggle, children }: Props) {
  const id = useId();
  const sub = !open && summary ? summary : undefined;
  return (
    <div className="more">
      <button
        type="button"
        className="lrow"
        aria-expanded={open}
        aria-controls={`${id}p`}
        aria-labelledby={`${id}l`}
        aria-describedby={sub ? `${id}s` : undefined}
        onClick={onToggle}
      >
        <span className="lrow-text">
          <span id={`${id}l`} className="lrow-label">
            <span className="lrow-title">{label}</span>
          </span>
          {sub && (
            <span id={`${id}s`} className="lrow-sub">
              {sub}
            </span>
          )}
        </span>
      </button>
      <div id={`${id}p`} className="more-body">
        {open && children}
      </div>
    </div>
  );
}
