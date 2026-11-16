import { useLocalization } from "@fluent/react";

import type { ClassType, Occurrence } from "../../api/client";
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
