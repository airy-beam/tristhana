import { Localized, useLocalization } from "@fluent/react";
import { useState, type SyntheticEvent } from "react";

import {
  useAddClosure,
  useAddSwap,
  useMe,
  useRemoveClosure,
  useRemoveSwap,
  useSchedule,
  type Occurrence,
  type Schedule,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { DateInput, Field } from "../../ui/controls";
import { Row } from "../Row";
import { deviceZone } from "../settings/zones";
import { zoneLabel } from "../timeLabel";
import { useOccurrenceText } from "./classText";
import OccurrenceSheet from "./OccurrenceSheet";
import { addDays, dateIn, dayName, plain, spanName, todayIn } from "./scheduleText";
import "./shalaCopy";
import "./shala.css";

const WEEK = 7;
const WEEKS = 4;

interface Props {
  shala: Shala;
  week?: number;
  /** The class a person tried to change is gone: say so over the week (UI-06 stage 4). */
  gone?: boolean;
  /** "Add a class": the form opens as a layer of its own. */
  onAdd: () => void;
  /** "Change the class…" on an occurrence. */
  onEdit: (occurrence: Occurrence) => void;
  /** "Tell students…" after a cancel, with the text to start from. */
  onTell: (draft: string) => void;
}

/** The shala's week (SC-02): every member reads it in the shala's zone (the card above names
 * it once); a day whose offset differs (a DST week) names it again. Staff who manage classes
 * add a class from the first row, open an occurrence for its date or the whole class, and set
 * closures and swaps from two rows under the week. Silent: no one gets a message (Q122). */
export default function ShalaSchedule({
  shala,
  week: first = 0,
  gone = false,
  onAdd,
  onEdit,
  onTell,
}: Props) {
  const { l10n } = useLocalization();
  const me = useMe().data;
  const locale: Locale = me?.locale ?? "en";
  const [week, setWeek] = useState(Math.min(Math.max(first, 0), WEEKS - 1));
  const [tool, setTool] = useState<"closure" | "swap" | null>(null);
  // A date was opened whose class has since changed: the same line as for the form (`gone`),
  // until another date is opened.
  const [stale, setStale] = useState(false);
  const manage = shala.me.schedule;
  const from = addDays(todayIn(shala.zone), week * WEEK);
  // "Nov 16 – 22": the week on screen, on one line between its arrows also at 320px in
  // Russian; the day rows under it carry the weekdays.
  const span = spanName(from, addDays(from, WEEK - 1), locale);
  const query = useSchedule(shala.id, from, WEEK);
  const schedule = query.data;
  const toggle = (next: "closure" | "swap") => () => {
    haptics.selection();
    setTool(tool === next ? null : next);
  };
  return (
    <section className="card schedule">
      <Localized id="schedule-title">
        <h2 />
      </Localized>
      {manage && (
        <div className="list">
          <Row
            label={l10n.getString("schedule-add-class")}
            action
            onClick={() => {
              haptics.selection();
              onAdd();
            }}
          />
        </div>
      )}
      {/* Which week this is, between its two arrows: over the days, where one looks first. */}
      <nav className="week-nav">
        <Localized id="page-prev">
          <button
            type="button"
            className="link"
            disabled={week === 0}
            onClick={() => {
              setWeek(week - 1);
            }}
          />
        </Localized>
        <span>{span}</span>
        <Localized id="page-next">
          <button
            type="button"
            className="link"
            disabled={week === WEEKS - 1}
            onClick={() => {
              setWeek(week + 1);
            }}
          />
        </Localized>
      </nav>
      {(gone || stale) && (
        <Localized id="class-form-gone">
          <p className="hint" role="status" />
        </Localized>
      )}
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
          onEdit={onEdit}
          onTell={onTell}
          onStale={setStale}
        />
      )}
      {manage && (
        <div className="list tools">
          <Row
            label={l10n.getString("closure-title")}
            expanded={tool === "closure"}
            onClick={toggle("closure")}
          />
          {tool === "closure" && schedule && (
            <Closures shala={shala} schedule={schedule} locale={locale} />
          )}
          <Row
            label={l10n.getString("swap-title")}
            expanded={tool === "swap"}
            onClick={toggle("swap")}
          />
          {tool === "swap" && <SwapForm shala={shala} />}
        </div>
      )}
    </section>
  );
}

function Week({
  shala,
  schedule,
  locale,
  viewer,
  onEdit,
  onTell,
  onStale,
}: {
  shala: Shala;
  schedule: Schedule;
  locale: Locale;
  viewer: string | null;
  onEdit: (occurrence: Occurrence) => void;
  onTell: (draft: string) => void;
  /** A date's class has changed under its open sheet (true), or another date was opened. */
  onStale: (stale: boolean) => void;
}) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState<string | null>(null);
  const removeSwap = useRemoveSwap(shala.id);
  const first = schedule.days[0]?.date ?? todayIn(schedule.zone);
  // Full labels, no viewer: a day row that names its zone again marks a daylight-saving
  // change, where the offset is the information (ADR-0044).
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
  const row = useOccurrenceText(schedule.zone, viewer, locale);
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
                // Staff who manage classes, and any staff seat for attendance (SC-05, Q181).
                return shala.me.schedule || o.attendance_counts ? (
                  <div key={id}>
                    <button
                      type="button"
                      className="row-button"
                      aria-expanded={open === id}
                      onClick={() => {
                        haptics.selection();
                        onStale(false);
                        setOpen(open === id ? null : id);
                      }}
                    >
                      {row(o)}
                    </button>
                    {open === id && (
                      <OccurrenceSheet
                        shala={shala}
                        occurrence={o}
                        locale={locale}
                        onDone={() => {
                          setOpen(null);
                        }}
                        onEdit={onEdit}
                        onTell={onTell}
                        onGone={() => {
                          setOpen(null);
                          onStale(true);
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
    <form className="panel" onSubmit={submit}>
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
              className="link tap"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(c.id);
              }}
            />
          </Localized>
        </div>
      ))}
      <Field label={l10n.getString("closure-start")}>
        <DateInput
          value={start}
          min={today}
          onChange={(e) => {
            setStart(e.target.value);
          }}
        />
      </Field>
      <Field label={l10n.getString("closure-end")}>
        <DateInput
          value={end}
          min={start}
          onChange={(e) => {
            setEnd(e.target.value);
          }}
        />
      </Field>
      <Localized id="closure-add">
        <button type="submit" className="btn" disabled={add.isPending} />
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
  const { l10n } = useLocalization();
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
    <form className="panel" onSubmit={submit}>
      <Localized id="swap-hint">
        <p className="hint small" />
      </Localized>
      <Field label={l10n.getString("swap-from")}>
        <DateInput
          value={from}
          min={today}
          onChange={(e) => {
            setFrom(e.target.value);
          }}
        />
      </Field>
      <Field label={l10n.getString("swap-to")}>
        <DateInput
          value={to}
          min={today}
          onChange={(e) => {
            setTo(e.target.value);
          }}
        />
      </Field>
      <Localized id="swap-add">
        <button type="submit" className="btn" disabled={add.isPending} />
      </Localized>
      {add.isError && (
        <Localized id="swap-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}
