import { useId } from "react";

import "./form.css";

interface Option<T> {
  value: T;
  /** What the chip shows. */
  label: string;
  /** Its accessible name, when the label is an abbreviation ("Mon" → "Monday"). */
  name?: string | undefined;
  /** A choice that can't be taken now (a time inside quiet hours). */
  disabled?: boolean | undefined;
}

interface Props<T extends string | number> {
  /** The group's label, shown above the chips. */
  label: string;
  options: readonly Option<T>[];
  /** The chosen one, or the chosen ones. */
  value: T | readonly T[];
  /** A chip was tapped; the owner decides what that means (choose, or toggle). */
  onPick: (value: T) => void;
  hint?: string | undefined;
  error?: string | false | null | undefined;
  disabled?: boolean | undefined;
}

/** A row of chips that wraps: one choice of a few, or several (UI-06 stage 4). */
export function Chips<T extends string | number>({
  label,
  options,
  value,
  onPick,
  hint,
  error,
  disabled,
}: Props<T>) {
  const id = useId();
  const chosen = (v: T) =>
    Array.isArray(value) ? (value as readonly T[]).includes(v) : value === v;
  const described = [hint ? `${id}h` : "", error ? `${id}e` : ""].filter(Boolean).join(" ");
  return (
    <div className="field">
      <span id={id} className="field-label">
        {label}
      </span>
      <div
        className="chips"
        role="group"
        aria-labelledby={id}
        aria-describedby={described || undefined}
      >
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className="chip"
            aria-pressed={chosen(o.value)}
            aria-label={o.name}
            disabled={disabled || o.disabled}
            onClick={() => {
              onPick(o.value);
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      {hint && (
        <p id={`${id}h`} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}e`} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
