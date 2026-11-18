import { useLocalization } from "@fluent/react";

import type { ClassSeries, ClassType, Occurrence } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { DASH, dayName, hmOf, minutesOf, plain, timeIn } from "./scheduleText";

/** How a class reads on a schedule row (SC-02, SC-03): shared by the shala's week, My schedule
 * and the roster, so none of them loads the class form to name a class. */

export const CLASS_TYPES: ClassType[] = [
  "mysore",
  "led",
  "private",
  "conference",
  "pranayama",
  "chanting",
  "workshop",
];
const CONTEXT: Partial<Record<ClassType, string>> = {
  mysore: "context-mysore",
  led: "context-led",
  private: "context-private",
};

/** Mysore, Led and 1:1 reuse the practice words; the rest have their own. */
export function useTypeName() {
  const { l10n } = useLocalization();
  return (type: ClassType) => {
    const context = CONTEXT[type];
    return context ? l10n.getString(context) : l10n.getString("class-type", { type });
  };
}

/** The occurrence's length in minutes (a class may end at midnight). */
export const lengthOf = (o: Occurrence) =>
  (minutesOf(o.end) - minutesOf(o.start) + 24 * 60) % (24 * 60) || 24 * 60;

/** "06:00–09:30 Mysore · Anna" in `zone` (the shala's); a cancelled one with its reason.
 * `teacher` names the other teacher instead (a teacher's own week). */
export function useOccurrenceText(zone: string, viewer: string | null, locale: Locale = "en") {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const marked = useRowMarks(locale);
  return (o: Occurrence, teacher?: string) => {
    const start = timeIn(o.starts_at, zone);
    const end = hmOf(minutesOf(start) + lengthOf(o));
    let text = `${start}${DASH}${end} ${typeName(o.type)}${o.title ? ` ${o.title}` : ""}`;
    if (teacher !== undefined) {
      if (teacher) text += ` · ${teacher}`;
    } else if (o.teacher) {
      const name = o.teacher.name ?? l10n.getString("link-no-name");
      text += ` · ${o.substitute ? plain(l10n.getString("schedule-substitute", { name })) : name}`;
    }
    if (o.online) {
      text += " 🌐";
      const mine = viewer ? timeIn(o.starts_at, viewer) : null;
      if (mine && viewer !== zone && mine !== timeIn(o.starts_at, zone))
        text += ` ${plain(l10n.getString("schedule-your-time", { time: mine }))}`;
    }
    return marked(o, text);
  };
}

/** The row marks (SC-03, expert items 1, 3, 4), shared by the shala's week and My schedule:
 * 🌙 leads a moon cancellation and ❌ a closure or a manual cancel; a class held on its moon
 * day ends with " · 🌙"; a cancelled original names where it went. */
export function useRowMarks(locale: Locale) {
  const { l10n } = useLocalization();
  return (o: Occurrence, text: string) => {
    if (!o.cancelled)
      return o.moon ? `${text} ${plain(l10n.getString("schedule-held-moon"))}` : text;
    const reason = plain(l10n.getString("schedule-reason", { reason: o.cancelled }));
    let out = `${o.cancelled === "moon" ? "🌙" : "❌"} ${text} (${reason})`;
    if (o.swapped_to)
      out += ` · ${plain(l10n.getString("schedule-swapped-inline", { day: dayName(o.swapped_to, locale) }))}`;
    return out;
  };
}

// UI-06 stage 6 (spec §3.1): a shala's Classes list, the rules as they stand. Mirrors of the
// backend's `domain/classes.py` `current_classes` and `day_runs`; one table of cases drives
// both (data/classes/class_list_cases.json).

/** What the two rules read of a saved class. */
export type ClassRule = Pick<
  ClassSeries,
  "id" | "type" | "start" | "weekdays" | "starts_on" | "ends_on"
>;

/** The series a shala runs from `today` (the shala's) on: `GET …/classes` also returns ended
 * series (ADR-0048). Weekly first, by first weekday, start, type (the catalog's order) and id;
 * then the one-date classes by date, start, type and id. */
export function currentClasses<T extends ClassRule>(classes: readonly T[], today: string): T[] {
  const current = (c: T) =>
    c.weekdays.length === 0 ? c.starts_on >= today : c.ends_on === null || c.ends_on >= today;
  const key = (c: T) => {
    const weekly = c.weekdays.length > 0;
    return [
      weekly ? 0 : 1,
      weekly ? Math.min(...c.weekdays) : 0,
      weekly ? "" : c.starts_on,
      c.start.slice(0, 5),
      CLASS_TYPES.indexOf(c.type),
      c.id,
    ] as const;
  };
  const compare = (a: T, b: T) => {
    const [x, y] = [key(a), key(b)];
    for (let i = 0; i < x.length; i++) {
      const [p, q] = [x[i] ?? 0, y[i] ?? 0];
      if (p < q) return -1;
      if (p > q) return 1;
    }
    return 0;
  };
  return classes.filter(current).sort(compare);
}

/** ISO weekdays, the first and the last of a run, both included. */
export type Run = readonly [number, number];
const RUN_MIN = 3; // days in a row that read as one run ("Mon–Fri"); two read as "Mon, Tue"

/** [1, 2, 3, 4, 5] → [[1, 5]] "Mon–Fri"; [1, 3] → [[1, 1], [3, 3]] "Mon, Wed". Three or more
 * days in a row are one run, shorter stretches single days, Monday first (a run never wraps
 * past Sunday); all seven are [1, 7], "every day". */
export function dayRuns(weekdays: readonly number[]): Run[] {
  const days = [...new Set(weekdays)].sort((a, b) => a - b);
  const runs: Run[] = [];
  let start = 0;
  for (let i = 1; i <= days.length; i++) {
    if (i < days.length && days[i] === (days[i - 1] ?? 0) + 1) continue;
    const stretch = days.slice(start, i);
    const [first = 0, last = 0] = [stretch[0], stretch.at(-1)];
    if (stretch.length >= RUN_MIN) runs.push([first, last]);
    else for (const d of stretch) runs.push([d, d]);
    start = i;
  }
  return runs;
}
