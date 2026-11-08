import { Localized, useLocalization } from "@fluent/react";
import { useState, type SyntheticEvent } from "react";

import {
  useAddClosure,
  useAddSwap,
  useClearOccurrence,
  useDeleteClass,
  useMe,
  useRemoveClosure,
  useRemoveSwap,
  useSchedule,
  useSetOccurrence,
  type Occurrence,
  type OccurrenceChange,
  type Schedule,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { confirmDestructive, haptics } from "../../telegram";
import { zoneLabel } from "../practiceText";
import { deviceZone } from "../settings/zones";
import ClassForm, { useTypeName } from "./ClassForm";
import {
  DASH,
  addDays,
  dateIn,
  dayName,
  hmOf,
  minutesOf,
  plain,
  timeIn,
  todayIn,
} from "./scheduleText";

const WEEK = 7;
const WEEKS = 4;

/** The shala's week (SC-02): every member reads it in the shala's zone (the card above names
 * it once); a day whose offset differs (a DST week) names it again. Staff who manage classes
 * open an occurrence to cancel, hold anyway or restore it, and add classes, closures and
 * swaps. Silent: no one gets a message (Q122). */
export default function ShalaSchedule({ shala }: { shala: Shala }) {
  const me = useMe().data;
  const locale: Locale = me?.locale ?? "en";
  const [week, setWeek] = useState(0);
  const [adding, setAdding] = useState(false);
  const from = addDays(todayIn(shala.zone), week * WEEK);
  const query = useSchedule(shala.id, from, WEEK);
  const schedule = query.data;
  const manage = shala.me.schedule;
  return (
    <section className="card schedule">
      <Localized id="schedule-title">
        <h2 />
      </Localized>
      {query.isError && (
        <Localized id="schedule-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {schedule && (
        <Week
          shala={shala}
          schedule={schedule}
          locale={locale}
          viewer={me?.timezone ?? deviceZone()}
        />
      )}
      <div className="paging">
        {week > 0 && (
          <Localized id="page-prev">
            <button
              type="button"
              className="link"
              onClick={() => {
                setWeek(week - 1);
              }}
            />
          </Localized>
        )}
        {week < WEEKS - 1 && (
          <Localized id="page-next">
            <button
              type="button"
              className="link"
              onClick={() => {
                setWeek(week + 1);
              }}
            />
          </Localized>
        )}
      </div>
      {manage &&
        (adding ? (
          <ClassForm
            shala={shala}
            onDone={() => {
              setAdding(false);
            }}
          />
        ) : (
          <Localized id="schedule-add-class">
            <button
              type="button"
              className="row-button"
              onClick={() => {
                setAdding(true);
              }}
            />
          </Localized>
        ))}
      {manage && schedule && <Closures shala={shala} schedule={schedule} locale={locale} />}
      {manage && <SwapForm shala={shala} />}
    </section>
  );
}

/** The occurrence's length in minutes (a class may end at midnight). */
export const lengthOf = (o: Occurrence) =>
  (minutesOf(o.end) - minutesOf(o.start) + 24 * 60) % (24 * 60) || 24 * 60;

/** "06:00–09:30 Mysore · Anna" in `zone` (the shala's); a cancelled one with its reason.
 * `teacher` names the other teacher instead (a teacher's own week). */
export function useOccurrenceText(zone: string, viewer: string | null) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
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
    if (o.cancelled) {
      const reason = plain(l10n.getString("schedule-reason", { reason: o.cancelled }));
      text = `❌ ${text} (${reason})`;
    }
    return text;
  };
}

function Week({
  shala,
  schedule,
  locale,
  viewer,
}: {
  shala: Shala;
  schedule: Schedule;
  locale: Locale;
  viewer: string | null;
}) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState<string | null>(null);
  const removeSwap = useRemoveSwap(shala.id);
  const first = schedule.days[0]?.date ?? todayIn(schedule.zone);
  const header = zoneLabel(schedule.zone, first);
  // Times and days in the shala's zone, from the instant: an online class may run in another
  // city's zone (Q124), and its wall clock there is not the one under this header.
  const localDay = (o: Occurrence) => dateIn(o.starts_at, schedule.zone);
  const shown = schedule.days.filter(
    (d) =>
      d.moon ||
      d.day_off ||
      d.swap_from ||
      schedule.occurrences.some((o) => localDay(o) === d.date),
  );
  const row = useOccurrenceText(schedule.zone, viewer);
  if (shown.length === 0)
    return (
      <Localized id="schedule-empty">
        <p className="hint" />
      </Localized>
    );
  return (
    <>
      {shown.map((d) => {
        const label = zoneLabel(schedule.zone, d.date);
        const marks = [
          d.moon ? l10n.getString("schedule-moon-day") : null,
          d.day_off ? l10n.getString("schedule-day-off") : null,
          d.swap_from
            ? plain(l10n.getString("schedule-swap", { day: dayName(d.swap_from, locale) }))
            : null,
          label === header ? null : label,
        ].filter((m): m is string => m !== null);
        return (
          <div key={d.date} className="schedule-day">
            <h3 className="label">{[dayName(d.date, locale), ...marks].join(" · ")}</h3>
            {d.swap_from && shala.me.schedule && (
              <Localized id="swap-remove">
                <button
                  type="button"
                  className="link"
                  disabled={removeSwap.isPending}
                  onClick={() => {
                    haptics.impact("light");
                    if (d.swap_from) removeSwap.mutate(d.swap_from);
                  }}
                />
              </Localized>
            )}
            {schedule.occurrences
              .filter((o) => localDay(o) === d.date)
              .map((o) => {
                const id = `${o.class_id}:${o.key}`;
                return shala.me.schedule ? (
                  <div key={id}>
                    <button
                      type="button"
                      className="row-button"
                      aria-expanded={open === id}
                      onClick={() => {
                        haptics.selection();
                        setOpen(open === id ? null : id);
                      }}
                    >
                      {row(o)}
                    </button>
                    {open === id && (
                      <Sheet
                        shala={shala}
                        occurrence={o}
                        onDone={() => {
                          setOpen(null);
                        }}
                      />
                    )}
                  </div>
                ) : (
                  <p key={id} className="link-person">
                    {row(o)}
                  </p>
                );
              })}
          </div>
        );
      })}
    </>
  );
}

/** Staff on one occurrence: cancel, hold anyway (auto-cancelled only, Q126), restore. */
function Sheet({
  shala,
  occurrence: o,
  onDone,
}: {
  shala: Shala;
  occurrence: Occurrence;
  onDone: () => void;
}) {
  const { l10n } = useLocalization();
  const set = useSetOccurrence(shala.id);
  const clear = useClearOccurrence(shala.id);
  const remove = useDeleteClass(shala.id);
  const removeAll = async () => {
    const ok = await confirmDestructive(
      l10n.getString("occurrence-delete-ask"),
      l10n.getString("occurrence-delete-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("heavy");
    remove.mutate(o.class_id, { onSuccess: onDone });
  };
  const target = { classId: o.class_id, key: o.key };
  // A write replaces the date's changes: send its move, substitute and hold again (Q126). A
  // swapped date's own move ends on `swapped_from`, not on the swap's day.
  const kept = (): OccurrenceChange => ({
    status: o.held ? "held" : null,
    teacher_id: o.substitute && o.teacher ? o.teacher.id : null,
    ...(o.moved ? { on: o.swapped_from ?? o.on, start: o.start, minutes: lengthOf(o) } : {}),
  });
  const change = (status: "cancelled" | "held") => {
    haptics.impact("light");
    const body = status === "held" ? { ...kept(), status } : { status };
    set.mutate({ ...target, body }, { onSuccess: onDone });
  };
  const restore = () => {
    haptics.impact("light");
    clear.mutate(target, { onSuccess: onDone });
  };
  // "Usual teacher" names no one for the date: it follows the class's teacher.
  const substitute = (teacher: string) => {
    haptics.impact("light");
    const body = { ...kept(), teacher_id: teacher || null };
    set.mutate({ ...target, body }, { onSuccess: onDone });
  };
  const named = o.substitute && o.teacher ? o.teacher : null;
  const pending = set.isPending || clear.isPending || remove.isPending;
  return (
    <div className="role-editor">
      {o.cancelled === null && (
        <label className="label">
          <Localized id="occurrence-teacher">
            <span />
          </Localized>
          <select
            value={named?.id ?? ""}
            disabled={pending}
            onChange={(e) => {
              substitute(e.target.value);
            }}
          >
            <option value="">
              {plain(
                l10n.getString("occurrence-usual-teacher", {
                  name: o.usual_teacher?.name ?? l10n.getString("class-form-no-teacher"),
                }),
              )}
            </option>
            {named && !shala.staff.some((s) => s.id === named.id) && (
              <option value={named.id}>{named.name ?? l10n.getString("link-no-name")}</option>
            )}
            {shala.staff
              .filter((s) => s.id !== o.usual_teacher?.id)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name ?? l10n.getString("link-no-name")}
                </option>
              ))}
          </select>
        </label>
      )}
      {o.cancelled === null && (
        <Localized id="occurrence-cancel">
          <button
            type="button"
            className="row-button"
            disabled={pending}
            onClick={() => {
              change("cancelled");
            }}
          />
        </Localized>
      )}
      {(o.cancelled === "moon" || o.cancelled === "closure") && (
        <Localized id="occurrence-hold">
          <button
            type="button"
            className="row-button"
            disabled={pending}
            onClick={() => {
              change("held");
            }}
          />
        </Localized>
      )}
      {(o.cancelled === "cancelled" || o.moved || o.substitute) && (
        <Localized id="occurrence-restore">
          <button type="button" className="row-button" disabled={pending} onClick={restore} />
        </Localized>
      )}
      <Localized id="occurrence-note">
        <p className="hint small" />
      </Localized>
      <Localized id="occurrence-delete">
        <button
          type="button"
          className="link danger"
          disabled={pending}
          onClick={() => {
            void removeAll();
          }}
        />
      </Localized>
      {(set.isError || clear.isError || remove.isError) && (
        <Localized id="occurrence-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </div>
  );
}

function Closures({
  shala,
  schedule,
  locale,
}: {
  shala: Shala;
  schedule: Schedule;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const add = useAddClosure(shala.id);
  const remove = useRemoveClosure(shala.id);
  const today = todayIn(shala.zone);
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    haptics.impact("light");
    add.mutate({ start, end });
  };
  return (
    <form className="shala-form" onSubmit={submit}>
      <Localized id="closure-title">
        <h3 className="label" />
      </Localized>
      {schedule.closures.map((c) => (
        <div key={c.id} className="link-person">
          <span>
            {plain(
              l10n.getString("closure-line", {
                start: dayName(c.start, locale),
                end: dayName(c.end, locale),
              }),
            )}
          </span>
          <Localized id="closure-remove">
            <button
              type="button"
              className="link"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(c.id);
              }}
            />
          </Localized>
        </div>
      ))}
      <label className="label">
        <Localized id="closure-start">
          <span />
        </Localized>
        <input
          type="date"
          value={start}
          min={today}
          onChange={(e) => {
            setStart(e.target.value);
          }}
        />
      </label>
      <label className="label">
        <Localized id="closure-end">
          <span />
        </Localized>
        <input
          type="date"
          value={end}
          min={start}
          onChange={(e) => {
            setEnd(e.target.value);
          }}
        />
      </label>
      <Localized id="closure-add">
        <button type="submit" className="row-button" disabled={add.isPending} />
      </Localized>
      {(add.isError || remove.isError) && (
        <Localized id="closure-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}

function SwapForm({ shala }: { shala: Shala }) {
  const add = useAddSwap(shala.id);
  const today = todayIn(shala.zone);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(addDays(today, 1));
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    haptics.impact("light");
    add.mutate({ from, to });
  };
  return (
    <form className="shala-form" onSubmit={submit}>
      <Localized id="swap-title">
        <h3 className="label" />
      </Localized>
      <Localized id="swap-hint">
        <p className="hint small" />
      </Localized>
      <label className="label">
        <Localized id="swap-from">
          <span />
        </Localized>
        <input
          type="date"
          value={from}
          min={today}
          onChange={(e) => {
            setFrom(e.target.value);
          }}
        />
      </label>
      <label className="label">
        <Localized id="swap-to">
          <span />
        </Localized>
        <input
          type="date"
          value={to}
          min={today}
          onChange={(e) => {
            setTo(e.target.value);
          }}
        />
      </label>
      <Localized id="swap-add">
        <button type="submit" className="row-button" disabled={add.isPending} />
      </Localized>
      {add.isError && (
        <Localized id="swap-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}
