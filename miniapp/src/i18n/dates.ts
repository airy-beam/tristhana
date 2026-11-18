import type { Locale } from "./negotiate";

/** UI-06 stage 5 (Q352a): a month as a title, the same on every screen. "November 2026" /
 * «Ноябрь 2026»: Russian in the nominative, capitalised, without the «г.» Intl adds. `year:
 * false` names the month alone ("November" / «Ноябрь»), for months under a year's heading.
 * `capital: false` keeps the language's own case, for a month inside running text («сверено:
 * ноябрь 2026», as the bot's Babel `LLLL y` says it); English months stay capitalised.
 * `month` is 0-based, as in `Date.UTC`; read in UTC, so no device zone moves it. */
export function monthTitle(
  year: number,
  month: number,
  locale: Locale,
  { year: withYear = true, capital = true }: { year?: boolean; capital?: boolean } = {},
): string {
  const text = formatter(locale, withYear).format(Date.UTC(year, month, 1));
  const bare = text.replace(/\s*г\.$/, "");
  if (!capital) return bare;
  return bare.charAt(0).toLocaleUpperCase(locale) + bare.slice(1);
}

const SHORT = new Map<string, Intl.DateTimeFormat>();

/** A calendar date (YYYY-MM-DD) in short words with its year: "Nov 18, 2026" / «18 нояб. 2026»,
 * without the «г.» Intl adds in Russian, as `monthTitle`. `weekday` adds the day's short name
 * ("Thu, Oct 1, 2025" / «чт, 1 окт. 2025»); `year: false` leaves the year out ("Thu, Oct 1").
 * Read in UTC: a date is not an instant, so no device zone moves it. */
export function shortDate(
  day: string,
  locale: Locale,
  { weekday = false, year = true }: { weekday?: boolean; year?: boolean } = {},
): string {
  const key = `${locale}:${weekday ? "w" : "-"}${year ? "y" : "-"}`;
  let format = SHORT.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat(locale, {
      ...(weekday ? { weekday: "short" } : {}),
      day: "numeric",
      month: "short",
      ...(year ? { year: "numeric" } : {}),
      timeZone: "UTC",
    });
    SHORT.set(key, format);
  }
  return format.format(Date.parse(`${day}T00:00:00Z`)).replace(/\s*г\.$/, "");
}

const FORMATS = new Map<string, Intl.DateTimeFormat>();

function formatter(locale: Locale, withYear: boolean): Intl.DateTimeFormat {
  const key = `${locale}:${withYear ? "y" : "-"}`;
  let format = FORMATS.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat(locale, {
      month: "long",
      ...(withYear ? { year: "numeric" } : {}),
      timeZone: "UTC",
    });
    FORMATS.set(key, format);
  }
  return format;
}
