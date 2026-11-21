import type { ReactLocalization } from "@fluent/react";

import type { MoonDays } from "../api/client";
import type { Locale } from "../i18n/negotiate";

const DAY_MS = 86_400_000;
/** Whole days from one calendar date to another. */
export const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);

/** ST-10: a moon day card can be shared from this many days before the day through the day. */
export const MOON_CARD_LEAD = 3;
/** Whether the moon day card for `day` can be made, counted from the server's today. */
export const moonShareable = (today: string, day: string) => {
  const away = daysBetween(today, day);
  return away >= 0 && away <= MOON_CARD_LEAD;
};

/** "Thu, 5 Nov" for a calendar date (no zone: a date is not an instant). */
export const moonDate = (locale: Locale) => {
  const format = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  return (day: string) => format.format(new Date(`${day}T00:00:00Z`));
};

/** One upcoming moon day (MD-03): phase · date · "in 3 days", counted from the server's today. */
export function moonDayLine(
  l10n: ReactLocalization,
  day: MoonDays["days"][number],
  today: string,
  date: (day: string) => string,
): string {
  return l10n.getString("moon-day-line", {
    phase: l10n.getString("moon-phase-long", { phase: day.phase }),
    date: date(day.date),
    in: l10n.getString("moon-in-days", { n: daysBetween(today, day.date) }),
  });
}
