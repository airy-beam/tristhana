import { Localized, useLocalization } from "@fluent/react";

import {
  useEndRestPeriod,
  useNotificationSettings,
  usePatchNotificationSettings,
  type NotificationSettings,
} from "../api/client";
import { haptics } from "../telegram";
import { Chips } from "../ui/Chips";
import { Check } from "../ui/controls";
import { useDateLabel } from "./PauseOffer";

const TIMES = ["09:00", "10:00", "12:00", "18:00", "20:00", "21:00"] as const;

type Practice = NotificationSettings["practice"];

const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

/** As the server's QuietHours.contains: may wrap midnight; start == end means none. */
export function inQuiet(quiet: NotificationSettings["quiet"], at: string): boolean {
  const [s, e, a] = [minutes(quiet.start), minutes(quiet.end), minutes(at)];
  if (s === e) return false;
  return s < e ? s <= a && a < e : a >= s || a < e;
}

/** The daily practice reminder (PR-10): on/off and time, first on Settings → Reminders. It
 * comes on the practice days, which Day off decides (PR-09). Off until chosen. The page names
 * the place of its times once, above this card (ADR-0044), and says so when no zone is known. */
export function PracticeReminderCard({ zone }: { zone: string | null }) {
  const query = useNotificationSettings();
  const save = usePatchNotificationSettings();
  const resume = useEndRestPeriod();
  const { l10n } = useLocalization();
  const dateLabel = useDateLabel();
  const settings = query.data;
  if (!settings) return null;
  const practice = settings.practice;
  const on = practice.on === true;
  // A rest period covers today (WH-01): reminders skip its days.
  const pausedStart = on ? practice.paused_start : null;
  const pausedUntil = on ? practice.paused_until : null;

  const daysText = (days: readonly number[]) =>
    days.length === 7
      ? l10n.getString("remind-every-day")
      : days.map((d) => l10n.getString("remind-weekday", { d })).join(", ");

  const update = (change: Partial<Practice>) => {
    haptics.impact("light");
    save.mutate(
      { practice: change },
      {
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };

  return (
    <section className="card" aria-labelledby="remind-title">
      <Localized id="remind-card-title">
        <h2 id="remind-title" />
      </Localized>
      <div className="switch">
        <Check
          label={l10n.getString("remind-switch")}
          checked={on}
          aria-describedby="remind-explain"
          onChange={(e) => {
            update({ on: e.target.checked });
          }}
        />
        <Localized id="remind-explain-app">
          <p id="remind-explain" className="field-hint" />
        </Localized>
      </div>
      {pausedStart && pausedUntil && (
        <div className="field">
          <Localized id="remind-paused-until" vars={{ until: dateLabel(pausedUntil) }}>
            <p className="hint" />
          </Localized>
          <Localized id="remind-resume">
            <button
              type="button"
              className="link tap"
              onClick={() => {
                haptics.impact("light");
                resume.mutate({ start: pausedStart }); // the server's "today" decides the end
              }}
            />
          </Localized>
        </div>
      )}
      {on && zone && (
        <Chips
          label={l10n.getString("settings-moon-time")}
          options={TIMES.map((t) => ({
            value: t,
            label: t,
            // A time inside quiet hours would never fire (the server refuses it too).
            disabled: inQuiet(settings.quiet, t),
          }))}
          value={practice.at.slice(0, 5)}
          onPick={(t) => {
            update({ at: `${t}:00` });
          }}
          hint={l10n.getString("remind-days-follow", { days: daysText(practice.days) })}
        />
      )}
      {save.isError && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
