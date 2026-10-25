import { Localized } from "@fluent/react";

import {
  DAY_STATUSES,
  useDays,
  useMoonCities,
  useMoonDays,
  useSetDay,
  type DayStatus,
} from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";
import { AutoNote } from "./AutoNote";
import { cityName } from "./MoonCard";
import { PracticeDetails } from "./PracticeDetails";

interface Props {
  /** The account's IANA zone (null until the device reported it). */
  zone: string | null;
  locale: Locale;
}

const LOGGED_KEY = "onboard.logged";

function loggedBefore(): boolean {
  try {
    return localStorage.getItem(LOGGED_KEY) === "1";
  } catch {
    return true; // storage blocked: never nag
  }
}

function markLogged(): void {
  try {
    localStorage.setItem(LOGGED_KEY, "1");
  } catch {
    // Blocked storage: the hint just isn't remembered.
  }
}

/** Today's status chips on Home (PR-01). "Today" comes from the server, never the device. */
export function TodayCard({ zone, locale }: Props) {
  const days = useDays();
  const setDay = useSetDay();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  if (days.isError) {
    return (
      <Localized id="today-load-failed">
        <p className="status" role="status" />
      </Localized>
    );
  }
  if (!days.data) return null;

  const { today } = days.data;
  const todayLog = days.data.days.find((d) => d.date === today);
  // Auto-rest is a note, never a pressed chip: logging anything replaces it (PR-09). It
  // names the city itself, so the moon line isn't shown twice.
  const auto = todayLog ? undefined : days.data.auto.find((a) => a.date === today);
  const moonToday = auto ? undefined : moon?.days.find((d) => d.date === today);
  const current = todayLog?.status ?? null;
  // UI-01: a first nudge until this device has saved a day (no extra request).
  // People who already log in the bot have days here, so they never see it.
  const firstHint = current === null && days.data.days.length === 0 && !loggedBefore();
  const save = (status: DayStatus | null) => {
    haptics.impact("light"); // feedback before the network call
    setDay.mutate(
      { date: today, status },
      {
        onSuccess: () => {
          if (status !== null) markLogged(); // a clear isn't a saved day
        },
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
      {moonToday && moon && (
        <Localized
          id="moon-today"
          vars={{
            phase: moonToday.phase,
            city: cityName(
              cities?.find((c) => c.slug === moon.location.slug),
              moon.location.slug,
              locale,
            ),
          }}
        >
          <p className="hint" />
        </Localized>
      )}
      {auto && <AutoNote auto={auto} location={days.data.moon_location} locale={locale} />}
      {firstHint && (
        <Localized id="home-first-hint">
          <p className="hint" />
        </Localized>
      )}
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
      {current === "practiced" && (
        <PracticeDetails
          date={today}
          practice={todayLog?.practices[0] ?? null}
          zone={zone}
          locale={locale}
        />
      )}
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
