import { Localized, useLocalization } from "@fluent/react";

import { useDays, useMoonCities, useMoonDays } from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { cityName } from "./cityName";
import { DayLog } from "./DayLog";
import { useDateLabel } from "./PauseOffer";

interface Props {
  /** The account's IANA zone (null until the device reported it). */
  zone: string | null;
  locale: Locale;
}

/** Today's day card (PR-01, UI-06): the one day card for the server's today, with the moon
 * line when today is a moon day. "Today" and its date come from the server, never the device. */
export function TodayCard({ zone, locale }: Props) {
  const { l10n } = useLocalization();
  const days = useDays();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  const dateLabel = useDateLabel();
  if (days.isError) {
    return (
      <Localized id="today-load-failed">
        <p className="status" role="status" />
      </Localized>
    );
  }
  if (!days.data) return null;

  const { today } = days.data;
  // An unlogged moon day is auto-rest: its own line names the city, so not twice (PR-09).
  const auto =
    !days.data.days.some((d) => d.date === today) && days.data.auto.some((a) => a.date === today);
  const moonToday = auto ? undefined : moon?.days.find((d) => d.date === today);
  return (
    <DayLog
      id="today-title"
      // Without Fluent's bidi marks round the date: the heading names the card for a reader.
      title={l10n
        .getString("today-title", { date: dateLabel(today) })
        .replace(/[\u2068\u2069]/g, "")}
      date={today}
      days={days.data}
      zone={zone}
      locale={locale}
    >
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
    </DayLog>
  );
}
