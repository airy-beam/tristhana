import { Localized, useLocalization } from "@fluent/react";

import {
  useEndRestPeriod,
  useNotificationSettings,
  usePatchNotificationSettings,
  type NotificationSettings,
} from "../api/client";
import { haptics } from "../telegram";
import { useDateLabel } from "./PauseOffer";
import { zoneLabel } from "./practiceText";

const TIMES = ["09:00", "10:00", "12:00", "18:00", "20:00", "21:00"] as const;

type Practice = NotificationSettings["practice"];

const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

/** As the server's QuietHours.contains: may wrap midnight; start == end means none. */
export function inQuiet(quiet: NotificationSettings["quiet"], at: string): boolean {
  const [s, e, a] = [minutes(quiet.start), minutes(quiet.end), minutes(at)];
  if (s === e) return false;
  return s < e ? s <= a && a < e : a >= s || a < e;
}

/** The daily practice reminder (PR-10): on/off and time. It comes on the practice days,
 * which the Day off section decides (PR-09). Off until chosen. */
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
      {pausedStart && pausedUntil && (
        <>
          <Localized id="remind-paused-until" vars={{ until: dateLabel(pausedUntil) }}>
            <p className="hint" />
          </Localized>
          <Localized id="remind-resume">
            <button
              type="button"
              className="link"
              onClick={() => {
                haptics.impact("light");
                resume.mutate({ start: pausedStart }); // the server's "today" decides the end
              }}
            />
          </Localized>
        </>
      )}
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
            <Localized id="remind-days-follow" vars={{ days: daysText(practice.days) }}>
              <p className="hint small" />
            </Localized>
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
