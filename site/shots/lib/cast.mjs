// UI-05: the demo cast. Invented people, one set per language, because an account has one
// language and the screenshots exist in both. Telegram ids are from a made-up range.

/** @typedef {import("./client.mjs").DemoUser} DemoUser */
/** @typedef {{ student: DemoUser, teacher: DemoUser, newcomer: DemoUser }} Cast */

export const CITY = { slug: "almaty", zone: "Asia/Almaty" };

/** @type {Record<"en" | "ru", Cast>} */
export const CAST = {
  en: {
    student: { id: 9001, name: "Maya", lang: "en" },
    teacher: { id: 9002, name: "Arjun", lang: "en" },
    newcomer: { id: 9003, name: "Maya", lang: "en" },
  },
  ru: {
    student: { id: 9101, name: "Майя", lang: "ru" },
    teacher: { id: 9102, name: "Арджун", lang: "ru" },
    newcomer: { id: 9103, name: "Майя", lang: "ru" },
  },
};

/** `YYYY-MM-DD` of the day `back` days before `today` (both in the demo city's zone). */
export function dayBefore(/** @type {string} */ today, /** @type {number} */ back) {
  const date = new Date(`${today}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - back);
  return date.toISOString().slice(0, 10);
}

/** Today's date in the demo city, where the demo accounts live. */
export function todayIn(/** @type {string} */ zone, now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone }).format(now);
}

const FULL_PRIMARY = { series: ["primary"] };
const HALF_PRIMARY = { series: ["primary"], end: "navasana" };

/**
 * What the demo student logged on a day `back` days ago: a steady, ordinary practice life.
 * Saturdays off, moon days off, a few quiet days and one short trip; half Primary at first,
 * full Primary for the last six weeks. Deterministic, so two runs on the same date give the
 * same pictures.
 * @param {string} date
 * @param {number} back
 * @param {Set<string>} [moonDays] dates of the followed moon days
 * @returns {{ status: string, practice?: { context: string, duration_min: number, length: object } }}
 */
export function demoDay(date, back, moonDays = new Set()) {
  const weekday = new Date(`${date}T12:00:00Z`).getUTCDay(); // 0 = Sunday
  if (moonDays.has(date)) return { status: "moon" };
  if (weekday === 6) return { status: "rest" };
  if (back >= 40 && back <= 43) return { status: "travel" };
  if (back % 17 === 9) return { status: "skipped" };
  const length = back > 42 ? HALF_PRIMARY : FULL_PRIMARY;
  const duration_min = back > 42 ? 60 : 90;
  const context = weekday === 0 ? "self" : weekday === 5 ? "led" : "mysore";
  return { status: "practiced", practice: { context, duration_min, length } };
}
