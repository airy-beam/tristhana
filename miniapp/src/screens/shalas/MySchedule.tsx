import { Localized, useLocalization } from "@fluent/react";
import { lazy, Suspense, useState } from "react";

import { useMe, useMySchedule, type MyRow, type MySchedule as Week } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { zoneLabel } from "../practiceText";
import { placeFor } from "../settings/zones";
import { useTypeName } from "./ClassForm";
import { lengthOf, useRowMarks } from "./ShalaSchedule";
import { DASH, addDays, dateIn, dayName, hmOf, minutesOf, plain, timeIn } from "./scheduleText";

// The shala card is its own lazy chunk (as from Links).
const ShalaScreen = lazy(() => import("./ShalaScreen"));

const WEEKS = 4;
type Filter = "all" | "teachers" | "mine";
const FILTER_KEY = "tristhana.my-schedule.filter";
const SHIFT_MARK = "⚠";

/** "Mon, Nov 9 – Sun, Nov 15" */
function span(data: Week, locale: Locale): string {
  const first = data.days[0];
  const last = data.days[data.days.length - 1];
  return first && last
    ? `${dayName(first.date, locale)} ${DASH} ${dayName(last.date, locale)}`
    : "";
}

interface Props {
  locale: Locale;
  onBack: () => void;
}

interface Choice {
  filter: Filter;
  shala: string | null;
}

/** Per-device convenience only: the last filter and shala chip. */
function remembered(): Choice {
  try {
    const raw = localStorage.getItem(FILTER_KEY);
    const found = raw ? (JSON.parse(raw) as Partial<Choice>) : {};
    const filter = ["all", "teachers", "mine"].includes(found.filter ?? "") ? found.filter : "all";
    return {
      filter: filter as Filter,
      shala: typeof found.shala === "string" ? found.shala : null,
    };
  } catch {
    return { filter: "all", shala: null };
  }
}

function remember(choice: Choice) {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify(choice));
  } catch {
    // private mode or blocked storage: the choice just isn't kept
  }
}

/** "🗓 My schedule" (SC-03, ADR-0035): every shala I'm in, a week at a time (0-3), in my zone,
 * with the class's own time when its offset differs. Filters and shala chips work on the same
 * answer. A row opens its shala's week. Read only. Loaded lazily. */
export default function MySchedule({ locale, onBack }: Props) {
  const [open, setOpen] = useState<{ id: string; week: number } | null>(null);
  if (open)
    return (
      <Suspense fallback={null}>
        <ShalaScreen
          id={open.id}
          week={open.week}
          onBack={() => {
            setOpen(null);
          }}
        />
      </Suspense>
    );
  return (
    <Weeks
      locale={locale}
      onBack={onBack}
      onOpen={(id, week) => {
        setOpen({ id, week });
      }}
    />
  );
}

function Weeks({
  locale,
  onBack,
  onOpen,
}: Props & { onOpen: (shala: string, week: number) => void }) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const [week, setWeek] = useState(0);
  const [choice, setChoice] = useState<Choice>(remembered);
  const base = useMySchedule(null);
  const from = week > 0 && base.data ? addDays(base.data.today, week * 7) : null;
  const query = useMySchedule(from);
  const data = week > 0 && !from ? undefined : query.data;
  const choose = (next: Choice) => {
    setChoice(next);
    remember(next);
  };
  const filter: Filter =
    (choice.filter === "teachers" && data && !data.has_teachers) ||
    (choice.filter === "mine" && data && !data.is_staff)
      ? "all"
      : choice.filter;
  const shala = data?.shalas.some((s) => s.id === choice.shala) ? choice.shala : null;
  return (
    <main className="screen my-schedule" aria-busy={query.isPending}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="my-schedule-open">
        <h1 />
      </Localized>
      {query.isError && (
        <Localized id="my-schedule-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {data && (
        <>
          <Header data={data} locale={locale} />
          <div className="chips" role="group">
            {(["all", "teachers", "mine"] as const)
              .filter((f) => f === "all" || (f === "teachers" ? data.has_teachers : data.is_staff))
              .map((f) => (
                <button
                  key={f}
                  type="button"
                  className="chip"
                  aria-pressed={filter === f}
                  onClick={() => {
                    choose({ ...choice, filter: f });
                  }}
                >
                  {plain(l10n.getString("my-schedule-filter", { f }))}
                </button>
              ))}
            {data.shalas.length > 1 &&
              data.shalas.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="chip"
                  aria-pressed={shala === s.id}
                  onClick={() => {
                    choose({ ...choice, shala: shala === s.id ? null : s.id });
                  }}
                >
                  {s.name}
                </button>
              ))}
          </div>
          <nav className="pager">
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
            <span className="label">{span(data, locale)}</span>
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
          <Days
            data={data}
            locale={locale}
            rows={data.occurrences.filter(
              (r) =>
                (filter === "all" || (filter === "teachers" ? r.my_teacher : r.role !== null)) &&
                (shala === null || r.shala_id === shala),
            )}
            filter={filter}
            onOpen={(id) => {
              onOpen(id, week);
            }}
          />
        </>
      )}
    </main>
  );
}

function Header({ data, locale }: { data: Week; locale: Locale }) {
  const { l10n } = useLocalization();
  const me = useMe().data;
  const first = data.days[0]?.date ?? data.today;
  const home = data.zone_known ? placeFor(me?.home_city, data.zone, locale) : undefined;
  const label = zoneLabel(data.zone, first, "12:00", home);
  // "15 November" / «15 ноября» (the month's genitive in Russian), as the bot's.
  const longDay = (day: string) => {
    const parts = new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "long",
      timeZone: "UTC",
    }).formatToParts(new Date(`${day}T00:00:00Z`));
    const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    return `${part("day")} ${part("month")}`;
  };
  return (
    <>
      <p className="hint small">
        {plain(
          data.zone_known
            ? l10n.getString("schedule-zone", { zone: label })
            : l10n.getString("my-schedule-zone-unknown", { zone: label }),
        )}
      </p>
      {data.shifts.map((s) => {
        const names = data.shalas.filter((x) => s.shala_ids.includes(x.id)).map((x) => x.name);
        const where =
          names.length === 1 && names[0]
            ? names[0]
            : zoneLabel(s.zone, s.on).replace(/ \(.*\)$/, "");
        const weekday = new Date(`${s.on}T00:00:00Z`).getUTCDay() || 7;
        return (
          <p key={`${s.zone}:${s.on}`} className="hint small" role="note">
            {plain(
              l10n.getString("schedule-shift", {
                weekday,
                date: longDay(s.on),
                where,
                hours: Math.abs(s.minutes) / 60,
                dir: s.minutes > 0 ? "earlier" : "later",
              }),
            )}
          </p>
        );
      })}
    </>
  );
}

function Days({
  data,
  rows,
  locale,
  filter,
  onOpen,
}: {
  data: Week;
  rows: MyRow[];
  locale: Locale;
  filter: Filter;
  onOpen: (shala: string) => void;
}) {
  const { l10n } = useLocalization();
  const text = useMyRowText(data, locale);
  const shifted = new Set(data.shifts.map((s) => s.on));
  const named = new Set(rows.map((r) => r.shala_id)).size > 1;
  const shown = data.days.filter(
    (d) =>
      d.my_moon ||
      shifted.has(d.date) ||
      rows.some((r) => dateIn(r.starts_at, data.zone) === d.date),
  );
  return (
    <>
      {rows.length === 0 && (
        <p className="hint">{plain(l10n.getString("my-schedule-empty", { f: filter }))}</p>
      )}
      {shown.map((d) => (
        <div key={d.date} className="card schedule-day">
          <h3
            className="label"
            aria-label={
              d.my_moon
                ? `${dayName(d.date, locale)}, ${plain(l10n.getString("my-schedule-my-moon-label"))}`
                : undefined
            }
          >
            {[
              dayName(d.date, locale),
              d.my_moon ? plain(l10n.getString("my-schedule-my-moon")) : null,
              shifted.has(d.date) ? SHIFT_MARK : null,
            ]
              .filter(Boolean)
              .join(" ")}
          </h3>
          {rows
            .filter((r) => dateIn(r.starts_at, data.zone) === d.date)
            .map((r) => {
              const [main, more] = text(r, named);
              return (
                <button
                  key={`${r.shala_id}:${r.class_id}:${r.key}:${r.on}`}
                  type="button"
                  className="row-button my-schedule-row"
                  onClick={() => {
                    onOpen(r.shala_id);
                  }}
                >
                  <span className="link-person">{main}</span>
                  {more && <span className="hint small">{more}</span>}
                </button>
              );
            })}
        </div>
      ))}
    </>
  );
}

/** Two lines: "🌙 06:00–09:30 Mysore · Anna 👤 (moon day)" and "Ashtanga Almaty · 17:30
 * Berlin (UTC+1)". Times in my zone; the class's own time when its offset differs. */
function useMyRowText(data: Week, locale: Locale) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const marked = useRowMarks(locale);
  const shalaName = (id: string) => data.shalas.find((s) => s.id === id)?.name ?? "";
  const name = (t: { name: string | null } | null) => t?.name ?? l10n.getString("link-no-name");
  return (r: MyRow, named: boolean): [string, string] => {
    const start = timeIn(r.starts_at, data.zone);
    const end = hmOf(minutesOf(start) + lengthOf(r));
    let main = `${start}${DASH}${end} ${typeName(r.type)}${r.title ? ` ${r.title}` : ""}`;
    if (r.role === "covered") {
      main += ` · ${plain(l10n.getString("my-classes-covered", { name: name(r.teacher) }))}`;
    } else if (r.role === "covering" && r.usual_teacher) {
      main += ` · ${plain(l10n.getString("my-classes-covering", { name: name(r.usual_teacher) }))}`;
    } else if (r.role === null && r.teacher) {
      let who = name(r.teacher);
      if (r.substitute && r.usual_teacher)
        who = plain(
          l10n.getString("schedule-covering-for", { name: who, teacher: name(r.usual_teacher) }),
        );
      else if (r.substitute) who = plain(l10n.getString("schedule-substitute", { name: who }));
      if (r.my_teacher) who += ` ${plain(l10n.getString("my-schedule-teacher-mark"))}`;
      main += ` · ${who}`;
    }
    if (r.online) main += " 🌐";
    if (r.moved && r.on !== r.key && r.planned)
      main += ` · ${plain(l10n.getString("schedule-moved", { day: dayName(r.key, locale), time: r.planned }))}`;
    if (r.swapped_from)
      main += ` · ${plain(l10n.getString("schedule-swapped-from", { day: dayName(r.swapped_from, locale) }))}`;
    const more: string[] = [];
    if (named) more.push(shalaName(r.shala_id));
    const there = timeIn(r.starts_at, r.zone);
    const own = zoneLabel(r.zone, r.on, there);
    const mine = zoneLabel(data.zone, dateIn(r.starts_at, data.zone), start);
    if (own.replace(/^.* \(/, "") !== mine.replace(/^.* \(/, "")) more.push(`${there} ${own}`);
    return [marked(r, main), more.join(" · ")];
  };
}
