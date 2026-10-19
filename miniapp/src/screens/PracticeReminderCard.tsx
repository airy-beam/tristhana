import { Localized } from "@fluent/react";

import {
  useNotificationSettings,
  useSaveNotificationSettings,
  type NotificationSettings,
} from "../api/client";
import { haptics } from "../telegram";
import { zoneLabel } from "./practiceText";

const TIMES = ["09:00", "10:00", "12:00", "18:00", "20:00", "21:00"] as const;
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
// One-tap "Day off: Sat / Sun" (ISO weekday off, the days that stay on).
const DAY_OFF = [
  [6, [1, 2, 3, 4, 5, 7]],
  [7, [1, 2, 3, 4, 5, 6]],
] as const;

const same = (a: readonly number[], b: readonly number[]) =>
  a.length === b.length && [...a].sort().every((x, i) => x === [...b].sort()[i]);

type Practice = NotificationSettings["practice"];

/** The daily practice reminder (PR-10): on/off, time, weekdays. Off until chosen. */
export function PracticeReminderCard({ zone }: { zone: string | null }) {
  const query = useNotificationSettings();
  const save = useSaveNotificationSettings({ withPractice: true });
  const settings = query.data;
  if (!settings) return null;
  const practice = settings.practice;
  const on = practice.on === true;

  const update = (change: Partial<Practice>) => {
    haptics.impact("light");
    save.mutate(
      { ...settings, practice: { ...practice, ...change } },
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
      <div className="chips" role="group">
        <Localized id="remind-switch">
          <button
            type="button"
            className="chip"
            aria-pressed={on}
            onClick={() => {
              update({ on: !on });
            }}
          />
        </Localized>
      </div>
      <Localized id="remind-explain-app">
        <p className="hint small" />
      </Localized>
      {on &&
        (zone ? (
          <>
            <Localized
              id="remind-time-label"
              vars={{ zone: zoneLabel(zone, new Date().toISOString().slice(0, 10)) }}
            >
              <p className="label" />
            </Localized>
            <div className="chips" role="group">
              {TIMES.map((t) => (
                <button
                  key={t}
                  type="button"
                  className="chip"
                  aria-pressed={practice.at.startsWith(t)}
                  onClick={() => {
                    update({ at: `${t}:00` });
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
            <Localized id="remind-days-label">
              <p className="label" />
            </Localized>
            <div className="chips" role="group">
              {DAY_OFF.map(([d, days]) => (
                <Localized key={d} id="remind-day-off" vars={{ d }}>
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={same(practice.days, days)}
                    onClick={() => {
                      update({ days: [...days] });
                    }}
                  />
                </Localized>
              ))}
            </div>
            <div className="chips" role="group">
              {WEEKDAYS.map((d) => {
                const picked = practice.days.includes(d);
                const last = picked && practice.days.length === 1;
                return (
                  <Localized key={d} id="remind-weekday" vars={{ d }}>
                    <button
                      type="button"
                      className="chip"
                      aria-pressed={picked}
                      disabled={last}
                      onClick={() => {
                        update({
                          days: picked
                            ? practice.days.filter((x) => x !== d)
                            : [...practice.days, d].sort((a, b) => a - b),
                        });
                      }}
                    />
                  </Localized>
                );
              })}
            </div>
          </>
        ) : (
          <Localized id="moon-zone-needed-app">
            <p className="hint" />
          </Localized>
        ))}
      {save.isError && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
