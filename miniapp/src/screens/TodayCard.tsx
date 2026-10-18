import { Localized } from "@fluent/react";

import { DAY_STATUSES, useDays, useSetDay, type DayStatus } from "../api/client";
import { haptics } from "../telegram";

/** Today's status chips on Home (PR-01). "Today" comes from the server, never the device. */
export function TodayCard() {
  const days = useDays();
  const setDay = useSetDay();
  if (days.isError) {
    return (
      <Localized id="today-load-failed">
        <p className="status" role="status" />
      </Localized>
    );
  }
  if (!days.data) return null;

  const { today } = days.data;
  const current = days.data.days.find((d) => d.date === today)?.status ?? null;
  const save = (status: DayStatus | null) => {
    haptics.impact("light"); // feedback before the network call
    setDay.mutate(
      { date: today, status },
      {
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };

  return (
    <section className="card" aria-labelledby="today-title">
      <Localized id="today-title">
        <h2 id="today-title" />
      </Localized>
      <div className="chips" role="group" aria-labelledby="today-title">
        {DAY_STATUSES.map((status) => (
          <Localized key={status} id={`status-${status}`}>
            <button
              type="button"
              className="chip"
              aria-pressed={status === current}
              onClick={() => {
                if (status !== current) save(status);
              }}
            />
          </Localized>
        ))}
      </div>
      {current === "ladies" && (
        <Localized id="today-private-note">
          <p className="hint" />
        </Localized>
      )}
      {current !== null && (
        <Localized id="today-clear">
          <button
            type="button"
            className="link"
            onClick={() => {
              save(null);
            }}
          />
        </Localized>
      )}
      {setDay.isError && (
        <Localized id="today-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
