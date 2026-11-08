import type { Locale } from "../../i18n/negotiate";

/** Shared bits of the shala schedule (SC-02): ISO dates as strings, ISO weekdays (Monday = 1). */

export const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;
export const DASH = "–"; // "06:00–09:30"

const plainRe = /[⁨⁩]/g;
export const plain = (text: string) => text.replace(plainRe, "");

/** Today in `zone` as YYYY-MM-DD (the shala's today bounds its schedule). */
export function todayIn(zone: string, now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone }).format(now);
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** "Mon, Nov 9" / «пн, 9 нояб.» */
export function dayName(day: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${day}T00:00:00Z`));
}

/** HH:MM of an instant in a zone. */
export function timeIn(instant: string, zone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: zone,
  }).format(new Date(instant));
}

/** The YYYY-MM-DD of an instant in a zone. */
export function dateIn(instant: string, zone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone }).format(new Date(instant));
}

export function minutesOf(hm: string): number {
  const [h = "0", m = "0"] = hm.split(":");
  return Number(h) * 60 + Number(m);
}

export function hmOf(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24;
  return `${String(h).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}
