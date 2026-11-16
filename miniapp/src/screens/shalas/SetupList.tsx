import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import type { Shala } from "../../api/client";
import { haptics } from "../../telegram";
import "../../ui/form.css";
import "./shalaCopy";
import "./shala.css";

export type SetupStep = NonNullable<Shala["setup"]>[number];

// The list's order, and each row's label.
const STEPS: readonly (readonly [SetupStep, string])[] = [
  ["add_class", "setup-class"],
  ["invite_students", "setup-students"],
  ["invite_staff", "setup-staff"],
];
const CHECK = "✓";

// "I teach alone" is remembered on this device only (Q339): no flag on the server.
const keyOf = (shala: string) => `setup.solo.${shala}`;

/** Blocked storage counts as "I teach alone": never a list that cannot be put away. */
function teachesAlone(shala: string): boolean {
  try {
    return localStorage.getItem(keyOf(shala)) === "1";
  } catch {
    return true;
  }
}

interface Props {
  shala: Shala;
  /** The step's place: the class form, the student invite, the staff invite. */
  onOpen: (step: SetupStep) => void;
}

/** The owner's first steps on a new shala (UI-06 stage 4): add a class, invite students,
 * invite teachers. The server says which are still due (`setup`, the same rule as Today's
 * next step); done ones are ticked, the first one due is the button, later ones are quiet. The
 * third is optional: "I teach alone" puts it away. Gone when nothing is due. */
export function SetupList({ shala, onOpen }: Props) {
  const { l10n } = useLocalization();
  const [alone, setAlone] = useState(() => teachesAlone(shala.id));
  const due = (shala.setup ?? []).filter((step) => !(alone && step === "invite_staff"));
  const next = due[0];
  if (!next) return null;
  const open = (step: SetupStep) => () => {
    haptics.selection();
    onOpen(step);
  };
  return (
    <section className="card setup" aria-labelledby="setup-title">
      <Localized id="setup-title">
        <h2 id="setup-title" />
      </Localized>
      <ol>
        {STEPS.filter(([step]) => !(alone && step === "invite_staff")).map(([step, label]) => {
          if (!due.includes(step))
            return (
              <li key={step} className="done">
                <span className="mark" role="img" aria-label={l10n.getString("setup-done-mark")}>
                  {CHECK}
                </span>
                {l10n.getString(label)}
              </li>
            );
          if (step !== next)
            return (
              <li key={step}>
                <span className="mark" />
                <button type="button" className="link tap" onClick={open(step)}>
                  {l10n.getString(label)}
                </button>
              </li>
            );
          return (
            <li key={step}>
              <button type="button" className="btn" aria-current="step" onClick={open(step)}>
                {l10n.getString(label)}
              </button>
              {step === "invite_staff" && (
                <Localized id="setup-staff-skip">
                  <button
                    type="button"
                    className="link tap"
                    onClick={() => {
                      haptics.selection();
                      try {
                        localStorage.setItem(keyOf(shala.id), "1");
                      } catch {
                        // Blocked storage: put away until the card is opened again.
                      }
                      setAlone(true);
                    }}
                  />
                </Localized>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
