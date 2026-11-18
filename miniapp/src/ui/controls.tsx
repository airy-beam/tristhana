import { createContext, useContext, useId, type ComponentProps, type ReactNode } from "react";

import "./form.css";

/** UI-06 stage 4: the form controls of the shala's screens. Native elements, styled with the
 * theme's tokens (`form.css`), so the phone's own pickers and screen readers keep working.
 * Imported only by lazy screens: the first chunk carries neither this nor its CSS. */

interface Wiring {
  id: string;
  describedBy: string | undefined;
  invalid: boolean;
}
const FieldContext = createContext<Wiring | null>(null);

interface FieldProps {
  label: string;
  /** A quiet line under the control. */
  hint?: string | undefined;
  /** What is wrong with the value; shown under the control and announced. */
  error?: string | false | null | undefined;
  /** One control. */
  children: ReactNode;
}

/** A label above its control; the hint and the error are the control's description. */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const described = [hint ? `${id}h` : "", error ? `${id}e` : ""].filter(Boolean).join(" ");
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <FieldContext value={{ id, describedBy: described || undefined, invalid: !!error }}>
        {children}
      </FieldContext>
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

/** What the `Field` around a control gives it. */
function useWiring() {
  const field = useContext(FieldContext);
  return {
    id: field?.id,
    "aria-describedby": field?.describedBy,
    "aria-invalid": field?.invalid ? (true as const) : undefined,
  };
}

type InputProps = Omit<ComponentProps<"input">, "type" | "className">;

export function TextInput(props: InputProps) {
  return <input type="text" className="control" {...useWiring()} {...props} />;
}

/** Wall-clock `HH:MM`; the phone's own time picker. */
export function TimeInput(props: InputProps) {
  return <input type="time" className="control" {...useWiring()} {...props} />;
}

/** A whole number with the phone's digit keys; `suffix` is its unit, beside the field (the
 * label already says it, so it is not read out again). */
export function NumberInput({ suffix, ...props }: InputProps & { suffix?: string | undefined }) {
  return (
    <span className="control-unit">
      <input type="number" inputMode="numeric" className="control" {...useWiring()} {...props} />
      {suffix && <span aria-hidden="true">{suffix}</span>}
    </span>
  );
}

/** `YYYY-MM-DD`; the phone's own date picker. */
export function DateInput(props: InputProps) {
  return <input type="date" className="control" {...useWiring()} {...props} />;
}

/** Several lines of text, full width; grows only by the person's own drag (down). */
export function TextArea(props: Omit<ComponentProps<"textarea">, "className">) {
  return <textarea className="control" {...useWiring()} {...props} />;
}

export function Select(props: Omit<ComponentProps<"select">, "className">) {
  return <select className="control" {...useWiring()} {...props} />;
}

/** A checkbox with its label beside it, the whole line the tap target. */
export function Check({ label, ...props }: InputProps & { label: string }) {
  return (
    <label className="check">
      <input type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  );
}
