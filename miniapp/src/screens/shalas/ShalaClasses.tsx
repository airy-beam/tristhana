import { Localized, useLocalization } from "@fluent/react";

import { useClasses, useMoonCities, type ClassSeries, type Shala } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { cityName } from "../cityName";
import { Row } from "../Row";
import { labelOf } from "../settings/zones";
import type { ClassEdit } from "./ClassForm";
import { currentClasses, dayRuns, useTypeName } from "./classText";
import { DASH, dayName, hmOf, minutesOf, plain, todayIn, weekdayShort } from "./scheduleText";
import "./shalaCopy";
import "./shala.css";

interface Props {
  shala: Shala;
  locale: Locale;
  /** The account's zone: an online class timed elsewhere names its zone, with the offset only
   * outside this one (ADR-0044). */
  viewer: string | null | undefined;
  /** A class was saved from the form during this visit: say so, and "Add another class". */
  added: boolean;
  /** "➕ Add a class": the form opens as a layer of its own. */
  onAdd: () => void;
  /** A class's row: its form, from the date a change would apply (ADR-0048). */
  onOpen: (edit: ClassEdit) => void;
}

/** A shala's Classes (UI-06 stage 6, spec §3.1, B2): each class as it stands, one row each
 * ("Mysore · Mon–Fri · 06:00–09:30"), so Mysore on weekdays and Led on Sunday read as the two
 * classes they are. For those who may manage the schedule (the API's own guard: a student or
 * an assistant never reads the list); the Schedule below stays by date. A tap opens the
 * class's form; "➕ Add a class" is under the rows, the main row while there are none, unless
 * the setup list above already shows "Add a class" as its step: one main action per screen. */
export default function ShalaClasses({ shala, locale, viewer, added, onAdd, onOpen }: Props) {
  const { l10n } = useLocalization();
  const manage = shala.me.schedule;
  const query = useClasses(shala.id, manage);
  const text = useClassText(shala, locale, viewer);
  if (!manage) return null;
  const today = todayIn(shala.zone);
  const current = query.data ? currentClasses(query.data, today) : undefined;
  const settled = current !== undefined || query.isError;
  const none = current?.length === 0;
  // The owner's setup list leads with the same step: then this one is a plain row.
  const setupAdds = (shala.setup ?? []).includes("add_class");
  const add = l10n.getString(added ? "class-add-another" : "schedule-add-class");
  const tapAdd = () => {
    haptics.selection();
    onAdd();
  };
  return (
    <section className="card classes" aria-busy={settled ? undefined : true}>
      <Localized id="shala-classes-title">
        <h2 />
      </Localized>
      {added && (
        <Localized id="class-form-saved">
          <p className="hint" role="status" />
        </Localized>
      )}
      {query.isError && (
        <Localized id="schedule-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {none && (
        <Localized id="shala-classes-none">
          <p className="hint" />
        </Localized>
      )}
      {none && !setupAdds && (
        <button type="button" className="btn" onClick={tapAdd}>
          {add}
        </button>
      )}
      {none && setupAdds && (
        <div className="list">
          <Row label={add} action onClick={tapAdd} />
        </div>
      )}
      {settled && !none && (
        <div className="list">
          {current?.map((c) => {
            const { label, sub } = text(c, today);
            return (
              <Row
                key={c.id}
                label={label}
                sub={sub || undefined}
                onClick={() => {
                  haptics.selection();
                  // The form proposes this date to apply a change from: today, or the first
                  // date of a class that has not begun.
                  onOpen({ classId: c.id, date: c.starts_on > today ? c.starts_on : today });
                }}
              />
            );
          })}
          <Row label={add} action onClick={tapAdd} />
        </div>
      )}
    </section>
  );
}

/** A class's row: "Mysore · Mon–Fri · 06:00–09:30", then what else is set, " · " between:
 * the teacher, every N weeks, a first date still to come, a last date, 🌐 for an online class
 * (with the zone it is timed in when that is another city's). */
function useClassText(shala: Shala, locale: Locale, viewer: string | null | undefined) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const cities = useMoonCities().data;
  const weekday = (d: number) => weekdayShort(d, locale);
  const daysOf = (c: ClassSeries) => {
    if (c.weekdays.length === 0)
      return plain(
        l10n.getString("day-label", { rel: "other", date: dayName(c.starts_on, locale) }),
      );
    const runs = dayRuns(c.weekdays);
    if (runs.length === 1 && runs[0]?.[0] === 1 && runs[0][1] === 7)
      return l10n.getString("shala-class-every-day");
    return runs
      .map(([a, b]) => (a === b ? weekday(a) : `${weekday(a)}${DASH}${weekday(b)}`))
      .join(", ");
  };
  return (c: ClassSeries, today: string) => {
    const start = c.start.slice(0, 5);
    const label = plain(
      l10n.getString("shala-class-row", {
        class: c.title ? `${typeName(c.type)} ${c.title}` : typeName(c.type),
        days: daysOf(c),
        start,
        end: hmOf(minutesOf(start) + c.minutes),
      }),
    );
    const weekly = c.weekdays.length > 0;
    const teacher = shala.staff.find((s) => s.id === c.teacher_id);
    // `city` is set only for an online class timed in another listed city (Q124).
    const runsIn = c.online && c.city ? cities?.find((x) => x.slug === c.city) : undefined;
    const online =
      c.online &&
      (runsIn
        ? `🌐 ${labelOf(runsIn.timezone, cityName(runsIn, runsIn.slug, locale), viewer)}`
        : "🌐");
    const sub = [
      teacher && (teacher.name ?? l10n.getString("link-no-name")),
      weekly && c.every > 1 && plain(l10n.getString("class-form-every-n", { n: c.every })),
      weekly &&
        c.starts_on > today &&
        plain(l10n.getString("class-form-sum-from", { date: dayName(c.starts_on, locale) })),
      weekly &&
        c.ends_on &&
        plain(l10n.getString("class-form-sum-end", { date: dayName(c.ends_on, locale) })),
      online,
    ]
      .filter(Boolean)
      .join(" · ");
    return { label, sub };
  };
}
