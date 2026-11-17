import { Localized } from "@fluent/react";
import { useState } from "react";

import { useNextSteps, usePatchNotificationSettings, type NextStep as Step } from "../api/client";
import { haptics } from "../telegram";
import { timeLabel } from "./timeLabel";

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

interface Props {
  /** The account's IANA zone. With one, the reminder step is done in one tap, right here. */
  zone: string | null;
  /** The home city's name when it names that zone (ADR-0029). */
  place?: string | undefined;
  /** The step's place: where it is done, or (the reminder) where its time is changed. */
  onOpen: (step: Step) => void;
}

/** One suggestion at a time under the day card (UI-06): the first step the server still
 * offers that the person has not put off here. It is gone once the server stops offering it
 * (the step's own data exists); nothing about it is stored. */
export function NextStep({ zone, place, onOpen }: Props) {
  const steps = useNextSteps().data;
  const remind = usePatchNotificationSettings();
  // Put off in this session, also where storage can be read but not written.
  const [skipped, setSkipped] = useState<readonly string[]>([]);
  // The reminder turned on here: the step and its time. Shown while the card is mounted, since
  // the server stops offering the step at once.
  const [asking, setAsking] = useState<{ step: Step; at: string } | null>(null);
  if (asking && zone)
    return (
      <section className="card next" aria-labelledby="next-step">
        {/* The bot's answer to "Yes, remind me". My own zone: the place, no offset (ADR-0044). */}
        <Localized
          id="remind-offer-set"
          vars={{
            time: timeLabel(asking.at, zone, new Date().toISOString().slice(0, 10), {
              place,
              viewer: zone,
            }),
          }}
        >
          <p id="next-step" role="status" />
        </Localized>
        <Localized id="remind-change-time">
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.selection();
              onOpen(asking.step);
            }}
          />
        </Localized>
      </section>
    );
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
            disabled={remind.isPending}
            onClick={() => {
              // Without a zone the reminder could not be sent yet: its setting says so.
              if (step.kind !== "reminder" || !zone) {
                haptics.selection();
                onOpen(step);
                return;
              }
              haptics.impact("light"); // feedback before the network call
              // On, and nothing else: the time is the server's default, as the Settings switch.
              remind.mutate(
                { practice: { on: true } },
                {
                  onSuccess: (saved) => {
                    setAsking({ step, at: saved.practice.at.slice(0, 5) });
                  },
                  onError: () => {
                    haptics.notify("error");
                  },
                },
              );
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
      {step.kind === "reminder" && remind.isError && (
        <Localized id="today-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
