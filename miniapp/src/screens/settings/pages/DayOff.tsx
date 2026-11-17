import { Localized } from "@fluent/react";

import { useSetDayOff } from "../../../api/client";
import { haptics } from "../../../telegram";
import { Page, PAGE_TITLE, SaveFailed, type PageProps } from "./Page";

import "../../../ui/form.css";

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

const MAX_DAYS_OFF = 2; // as the server's domain limit

/** Settings → Day off (PR-09): the one day setting. Pressed = a day off (at most two; a third
 * waits until one is unpressed); the other days are the practice days, and practice reminders
 * come on them. Nothing pressed until chosen. */
export default function DayOff({ me, onBack }: PageProps) {
  const setDayOff = useSetDayOff();
  // The cached account: a tap shows at once, here and on the row behind this page.
  const current = me.day_off ?? null;
  const choose = (days: number[]) => {
    haptics.impact("light");
    setDayOff.mutate(days, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  return (
    <Page title="settings-day-off" onBack={onBack}>
      <section className="card">
        <div className="field">
          <div className="chips" role="group" aria-labelledby={PAGE_TITLE}>
            {WEEKDAYS.map((d) => {
              const off = current?.includes(d) ?? false;
              const full = !off && (current?.length ?? 0) >= MAX_DAYS_OFF;
              return (
                <Localized key={d} id="remind-weekday" vars={{ d }}>
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={off}
                    disabled={full}
                    onClick={() => {
                      const days = current ?? [];
                      choose(
                        off ? days.filter((x) => x !== d) : [...days, d].sort((a, b) => a - b),
                      );
                    }}
                  />
                </Localized>
              );
            })}
            <Localized id="day-off-none">
              <button
                type="button"
                className="chip"
                aria-pressed={current?.length === 0}
                onClick={() => {
                  choose([]);
                }}
              />
            </Localized>
          </div>
          <Localized id="settings-day-off-hint" vars={{ first: current === null ? "yes" : "no" }}>
            <p className="field-hint" />
          </Localized>
        </div>
        <SaveFailed when={setDayOff.isError} />
      </section>
    </Page>
  );
}
