import { Localized } from "@fluent/react";
import { useState } from "react";

import { useNextSteps, type NextStep as Step } from "../api/client";
import { haptics } from "../telegram";

// The sentence for each step; its button is the same key with "-do".
const COPY: Partial<Record<string, string>> = {
  add_class: "next-class",
  invite_shala_students: "next-shala-invite",
  invite_student: "next-invite",
  reminder: "next-reminder",
  position: "next-position",
};

// "Not now" is remembered on this device only (Q333): no flag on the server.
const keyOf = (step: Step) => `next.skip.${step.kind}${step.shala_id ? `.${step.shala_id}` : ""}`;

/** Blocked storage counts as "not now": never a nag. */
function putOff(step: Step): boolean {
  try {
    return localStorage.getItem(keyOf(step)) === "1";
  } catch {
    return true;
  }
}

/** One suggestion at a time under the day card (UI-06): the first step the server still
 * offers that the person has not put off here. It is gone once the server stops offering it
 * (the step's own data exists); nothing about it is stored. */
export function NextStep({ onOpen }: { onOpen: (step: Step) => void }) {
  const steps = useNextSteps().data;
  // Put off in this session, also where storage can be read but not written.
  const [skipped, setSkipped] = useState<readonly string[]>([]);
  const step = steps?.find(
    (s) => COPY[s.kind] !== undefined && !skipped.includes(keyOf(s)) && !putOff(s),
  );
  const copy = step && COPY[step.kind];
  if (!step || !copy) return null;
  return (
    <section className="card next" aria-labelledby="next-step">
      <Localized id={copy}>
        <p id="next-step" />
      </Localized>
      <div className="row">
        <Localized id={`${copy}-do`}>
          <button
            type="button"
            className="chip primary"
            onClick={() => {
              haptics.selection();
              onOpen(step);
            }}
          />
        </Localized>
        <Localized id="next-not-now">
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.selection();
              try {
                localStorage.setItem(keyOf(step), "1");
              } catch {
                // Blocked storage: put off until the app is opened again.
              }
              setSkipped([...skipped, keyOf(step)]);
            }}
          />
        </Localized>
      </div>
    </section>
  );
}
