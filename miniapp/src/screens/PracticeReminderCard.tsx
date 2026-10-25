import { Localized } from "@fluent/react";

import {
  useMe,
  useNotificationSettings,
  usePatchNotificationSettings,
  useSetDayOff,
  type NotificationSettings,
} from "../api/client";
import { haptics } from "../telegram";
import { zoneLabel } from "./practiceText";

const TIMES = ["09:00", "10:00", "12:00", "18:00", "20:00", "21:00"] as const;
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
// One-tap "Day off: Sat / Sun": they set the day off itself; reminder days follow (PR-09).
const DAY_OFF = [6, 7] as const;

type Practice = NotificationSettings["practice"];

const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

/** As the server's QuietHours.contains: may wrap midnight; start == end means none. */
export function inQuiet(quiet: NotificationSettings["quiet"], at: string): boolean {
  const [s, e, a] = [minutes(quiet.start), minutes(quiet.end), minutes(at)];
  if (s === e) return false;
  return s < e ? s <= a && a < e : a >= s || a < e;
}

/** The daily practice reminder (PR-10): on/off, time, weekdays. Off until chosen. */
export function PracticeReminderCard({ zone }: { zone: string | null }) {
  const query = useNotificationSettings();
  const save = usePatchNotificationSettings();
  const setDayOff = useSetDayOff();
  const dayOff = useMe().data?.day_off ?? null;
  const settings = query.data;
  if (!settings) return null;
  const practice = settings.practice;
  const on = practice.on === true;

  const update = (change: Partial<Practice>) => {
    haptics.impact("light");
    if (change.days) setDayOff.reset(); // customised again: the follow note is stale
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
                  // A time inside quiet hours would never fire (the server refuses it too).
                  disabled={inQuiet(settings.quiet, t)}
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
              {DAY_OFF.map((d) => (
                <Localized key={d} id="remind-day-off" vars={{ d }}>
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={dayOff?.length === 1 && dayOff[0] === d}
                    onClick={() => {
                      haptics.impact("light");
                      setDayOff.mutate([d]);
                    }}
                  />
                </Localized>
              ))}
            </div>
            {setDayOff.data?.reminder_days_reset && (
              <Localized id="day-off-reminders-follow">
                <p className="hint" role="status" />
              </Localized>
            )}
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
      {(save.isError || setDayOff.isError) && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
