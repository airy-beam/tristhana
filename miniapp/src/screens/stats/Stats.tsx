import { Localized, useLocalization } from "@fluent/react";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type Ref } from "react";

import {
  useMe,
  useMoonCities,
  useNotificationSettings,
  type Stats as StatsData,
  type StatsSummary,
} from "../../api/client";
import { monthTitle } from "../../i18n/dates";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import { haptics } from "../../telegram";
import { More } from "../../ui/More";
import { cityName } from "../cityName";
import { DayOffQuestion } from "../DayOffQuestion";
import { ShareButton } from "../share/ShareButton";
import {
  autoDays,
  monthAt,
  monthIndex,
  monthOf,
  moonDates,
  parse,
  useShowLadies,
  type Month,
} from "./cells";
import { DayEditor } from "./DayEditor";
import { Legend } from "./Legend";
import { MonthView } from "./MonthView";
import { useKeptStats } from "./useKeptStats";

import "./practiceCopy";
import "./stats.css";

// GM-02: its own chunk (with its copy), so My practice doesn't pay for it.
const Badges = lazyRetry(() => import("../badges/Badges"));
// ST-05: likewise.
const Trends = lazyRetry(() => import("../trends/Trends"));
// UI-06 stage 3: the year's twelve months, behind their row.
const Year = lazyRetry(() => import("./Year"));

type Over = "badges" | "trends" | "year";

interface Props {
  locale: Locale;
  zone: string | null;
  /** My asanas (PR-08), the first row under the month. */
  onAsanas: () => void;
  /** Settings, at the day off (the stats question's "Other…" and link). */
  onDayOff: () => void;
  /** The shell focuses the heading after a tab switch. */
  headingRef?: Ref<HTMLHeadingElement> | undefined;
}

/** The Practice tab's root (UI-06 stage 3): one month (its calendar, four marks, one number,
 * the rest folded), then the rows: My asanas, the year, Badges, Check-ins (ST-01..03). A root
 * registers no Back layer; its inner layers (the year, Badges, Check-ins, the day card) do.
 * Loaded lazily, so Today stays light. */
export default function Stats({ locale, zone, onAsanas, onDayOff, headingRef }: Props) {
  // The month asked for; null is the current one, by the server's today.
  const [want, setWant] = useState<Month | null>(null);
  // A step whose year did not load: the pager is back on the month shown, and the line stays.
  const [stuck, setStuck] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  // The year, Badges and Check-ins over time open over My practice, which stays mounted
  // (hidden): Back returns to the same month, day card and scroll position.
  const [over, setOver] = useState<Over | null>(null);
  const left = useRef<{ top: number; focus: Element | null } | null>(null);
  // `from` is the row that was tapped: the focus returns to it (a tap focuses nothing on iOS).
  const open = useCallback((screen: Over, from: Element) => {
    haptics.selection();
    left.current = { top: window.scrollY, focus: from };
    setOver(screen);
    window.scrollTo({ top: 0 });
  }, []);
  const closeOver = useCallback(() => {
    setOver(null);
  }, []);
  useEffect(() => {
    const was = left.current;
    if (over || !was) return;
    left.current = null;
    window.scrollTo({ top: was.top });
    if (was.focus instanceof HTMLElement && was.focus.isConnected) {
      was.focus.focus({ preventScroll: true });
    }
  }, [over]);

  const { stats, failed } = useKeptStats(want ? want.year : null);
  const now = stats && monthOf(stats.today);
  const at = want ?? now;
  // The month on screen. While the year asked for loads, the year before it stays, on its
  // first or last month.
  const shown: Month | undefined = stats &&
    at && {
      year: stats.year,
      month: stats.year === at.year ? at.month : stats.year > at.year ? 0 : 11,
    };
  // The year asked for did not come: the pager returns to the month on screen, so its arrows
  // and the title agree, and the next tap asks again.
  if (failed && want && shown && want.year !== shown.year) {
    setWant(shown);
    setStuck(true);
  }
  // The open day and the open fold belong to the month on screen: when it changes for any
  // reason (the pager, a month picked in the year, the server's today moving on), both close.
  const key = shown ? monthIndex(shown) : null;
  const [last, setLast] = useState(key);
  if (key !== last) {
    setLast(key);
    setEditing(null);
    setMore(false);
  }
  const show = useCallback((month: Month) => {
    setWant(month);
    setStuck(false);
    setEditing(null);
  }, []);
  // A month picked in the year: the layer closes on it, at the top, where the month is.
  const pick = useCallback(
    (month: Month) => {
      show(month);
      left.current = { top: 0, focus: document.getElementById("month-title") };
      setOver(null);
    },
    [show],
  );

  return (
    <>
      {over && (
        <Suspense fallback={<main className="screen" aria-busy="true" />}>
          {over === "badges" ? (
            <Badges locale={locale} onBack={closeOver} />
          ) : over === "trends" ? (
            <Trends locale={locale} onBack={closeOver} />
          ) : (
            stats &&
            shown && (
              <Year
                locale={locale}
                shown={shown}
                today={stats.today}
                first={stats.first_year ?? monthOf(stats.today).year}
                onPick={pick}
                onBack={closeOver}
              />
            )
          )}
        </Suspense>
      )}
      <main
        className="screen stats"
        hidden={over !== null}
        aria-busy={!stats && !failed ? true : undefined}
      >
        <Localized id="stats-title">
          <h1 ref={headingRef} tabIndex={-1} />
        </Localized>
        {(failed || stuck) && (
          <Localized id="stats-load-failed">
            <p className="status" role="alert" />
          </Localized>
        )}
        {stats && at && shown && (
          <MonthCard
            stats={stats}
            at={at}
            month={shown.month}
            // Only a day of the month on screen has its card here.
            editing={editing && monthIndex(monthOf(editing)) === key ? editing : null}
            more={more}
            locale={locale}
            zone={zone}
            onMonth={show}
            onEdit={setEditing}
            onMore={setMore}
            onDayOff={onDayOff}
          />
        )}
        {/* Outside the loaded part: the rows are there while stats load and when they fail. */}
        <Localized id="progression-open">
          <button
            type="button"
            className="row-button"
            onClick={() => {
              haptics.selection();
              onAsanas();
            }}
          />
        </Localized>
        {stats && (
          <Localized
            id="stats-year-open"
            vars={{ year: String(stats.year), n: stats.year_total.practiced }}
          >
            <button
              type="button"
              className="row-button"
              onClick={(event) => {
                open("year", event.currentTarget);
              }}
            />
          </Localized>
        )}
        <Localized id="badges-open">
          <button
            type="button"
            className="row-button"
            onClick={(event) => {
              open("badges", event.currentTarget);
            }}
          />
        </Localized>
        <Localized id="trends-open">
          <button
            type="button"
            className="row-button"
            onClick={(event) => {
              open("trends", event.currentTarget);
            }}
          />
        </Localized>
      </main>
    </>
  );
}

/** One month: ‹ November 2026 ›, the calendar, the day card of an opened day, the legend, one
 * number (or a quiet line when there is no practice to count); on the current month what is in
 * a row and where to tap; the rest in a fold. */
function MonthCard({
  stats,
  at,
  month,
  editing,
  more,
  locale,
  zone,
  onMonth,
  onEdit,
  onMore,
  onDayOff,
}: {
  stats: StatsData;
  /** The pager's month. While its year loads, `stats` is still the year before it. */
  at: Month;
  /** The month of `stats.year` on screen. */
  month: number;
  editing: string | null;
  more: boolean;
  locale: Locale;
  zone: string | null;
  onMonth: (month: Month) => void;
  onEdit: (day: string | null) => void;
  onMore: (open: boolean) => void;
  onDayOff: () => void;
}) {
  const { l10n } = useLocalization();
  const cities = useMoonCities().data;
  const showLadies = useShowLadies();
  const unset = useMe().data?.day_off === null;
  const opener = useRef<HTMLElement | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const moon = useMemo(() => moonDates(stats), [stats]);
  const auto = useMemo(() => autoDays(stats), [stats]);
  const fmt = useMemo(
    () => ({
      day: new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
        timeZone: "UTC",
      }),
      weekday: new Intl.DateTimeFormat(locale, { weekday: "narrow", timeZone: "UTC" }),
    }),
    [locale],
  );
  const dateLabel = useCallback((day: string) => fmt.day.format(parse(day)), [fmt]);
  // 2024-01-01 was a Monday.
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    fmt.weekday.format(Date.UTC(2024, 0, 1 + i)),
  );
  const city = cityName(
    cities?.find((c) => c.slug === stats.moon.location),
    stats.moon.location,
    locale,
  );

  // "Today" and the current month are the server's, never the device's.
  const now = monthOf(stats.today);
  const thisYear = stats.year === now.year;
  // The year asked for is still loading: the month that stays is not the pager's, so its days
  // wait (a day tapped now would open under the month that arrives).
  const waiting = stats.year !== at.year;
  const current = thisYear && month === now.month;
  const summary = stats.months[month] as StatsSummary;
  const title = monthTitle(stats.year, month, locale);
  // From January of the first year with anything logged to the current month.
  const first = (stats.first_year ?? now.year) * 12;
  const end = monthIndex(now);
  const step = (by: number, arrow: HTMLElement) => {
    haptics.selection();
    const to = monthIndex(at) + by;
    // The arrow that reaches an end is disabled next: the focus moves to the month's name
    // rather than staying on a dead button.
    if ((by < 0 ? to <= first : to >= end) && document.activeElement === arrow) {
      heading.current?.focus({ preventScroll: true });
    }
    onMonth(monthAt(to));
  };
  // Auto-rest counts as rest, but a month with only auto days is still "empty".
  const logged =
    summary.practiced +
    summary.skipped +
    Object.values(summary.rest).reduce((a, b) => a + b, 0) -
    summary.auto;
  const moonDay = editing ? stats.moon.days.find((d) => d.date === editing) : undefined;

  return (
    <section className="card month" aria-labelledby="month-title">
      <div className="pager">
        <Localized id="stats-month-prev" attrs={{ "aria-label": true }}>
          <button
            type="button"
            className="link"
            disabled={monthIndex(at) <= first}
            onClick={(event) => {
              step(-1, event.currentTarget);
            }}
          />
        </Localized>
        {/* Polite: a step says the month it reached. */}
        <h2 id="month-title" ref={heading} tabIndex={-1} aria-live="polite">
          {title}
        </h2>
        <Localized id="stats-month-next" attrs={{ "aria-label": true }}>
          <button
            type="button"
            className="link"
            disabled={monthIndex(at) >= end}
            onClick={(event) => {
              step(1, event.currentTarget);
            }}
          />
        </Localized>
      </div>
      <MonthView
        stats={stats}
        month={month}
        moon={moon}
        auto={auto}
        city={city}
        showLadies={showLadies}
        weekdays={weekdays}
        dateLabel={dateLabel}
        frozen={waiting}
        onPick={(day, from) => {
          haptics.selection();
          opener.current = from;
          onEdit(day);
        }}
      />
      {editing && (
        // Another day is another card: it comes into view and takes the focus anew.
        <DayEditor
          key={editing}
          date={editing}
          label={dateLabel(editing)}
          zone={zone}
          locale={locale}
          onClose={() => {
            onEdit(null);
            // Back to the day that was tapped.
            if (opener.current?.isConnected) opener.current.focus({ preventScroll: true });
          }}
        >
          {moonDay && (
            <Localized id="stats-day-moon" vars={{ phase: moonDay.phase, city }}>
              <p className="hint" />
            </Localized>
          )}
        </DayEditor>
      )}
      <Legend />
      {summary.practiced > 0 ? (
        <div className="card-head">
          <Localized id="stats-month-practices" vars={{ n: summary.practiced }}>
            <p className="total" />
          </Localized>
          <ShareButton
            subject={{ kind: "month", year: stats.year, month: month + 1 }}
            label={l10n.getString("share-entry", { entry: title })}
          />
        </div>
      ) : (
        // No practice to count: never a bold zero. Nothing logged at all invites a tap; rest
        // (or "No practice") gets a quiet word.
        <Localized id={logged === 0 ? "stats-month-empty" : "stats-month-rest"}>
          <p className="hint" />
        </Localized>
      )}
      {current && (stats.runs.current ?? 0) >= 2 && (
        <Localized id="stats-run-current" vars={{ n: stats.runs.current ?? 0 }}>
          <p />
        </Localized>
      )}
      {/* Not beside the empty month's own invitation to tap. */}
      {current && logged > 0 && summary.unlogged > 0 && (
        <Localized id="stats-unlogged">
          <p className="hint" />
        </Localized>
      )}
      {/* PR-09: asked once; afterwards (or when it can't be asked) a quiet link. */}
      {current && unset && <DayOffLink onDayOff={onDayOff} />}
      {logged > 0 && (
        <More
          label={l10n.getString("stats-more")}
          open={more}
          onToggle={() => {
            haptics.selection();
            onMore(!more);
          }}
        >
          <MonthNumbers
            summary={summary}
            showLadies={showLadies}
            longest={thisYear ? stats.runs.longest : 0}
          />
        </More>
      )}
    </section>
  );
}

function DayOffLink({ onDayOff }: { onDayOff: () => void }) {
  const question = useNotificationSettings().data?.day_off_question;
  if (question) return <DayOffQuestion onOther={onDayOff} />;
  return (
    <Localized id="stats-day-off-link">
      <button type="button" className="link" onClick={onDayOff} />
    </Localized>
  );
}

/** "The month in numbers": rest by kind, where, online, by series, time; then the two counts
 * that need a word of explanation, with it. "X of Y" exists only once the person chose "No
 * practice" themselves, and never at zero. */
function MonthNumbers({
  summary: s,
  showLadies,
  longest,
}: {
  summary: StatsSummary;
  showLadies: boolean;
  /** The most in a row this year; 0 for a month of another year. */
  longest: number;
}) {
  // 🌸 merges into rest unless shown on this device.
  const rest = { ...s.rest };
  if (!showLadies) {
    rest.rest += rest.ladies;
    rest.ladies = 0;
  }
  const restRows = (["rest", "moon", "ladies", "sick", "travel"] as const).filter(
    (k) => rest[k] > 0,
  );
  const contexts = (["mysore", "led", "private", "self"] as const).filter((k) => s.contexts[k] > 0);
  const avg = s.duration.count ? Math.round(s.duration.total_min / s.duration.count) : 0;
  const ofDays = s.practiced > 0 && s.skipped > 0;
  return (
    <>
      {(restRows.length > 0 || s.skipped > 0) && (
        <ul className="counts">
          {restRows.map((k) => (
            <li key={k}>
              <Localized id={`status-${k}`}>
                <span />
              </Localized>
              <span>{rest[k]}</span>
            </li>
          ))}
          {s.skipped > 0 && (
            <li>
              <Localized id="status-skipped">
                <span />
              </Localized>
              <span>{s.skipped}</span>
            </li>
          )}
        </ul>
      )}
      {contexts.length > 0 && (
        <ul className="counts">
          {contexts.map((k) => (
            <li key={k}>
              <Localized id={`context-${k}`}>
                <span />
              </Localized>
              <span>{s.contexts[k]}</span>
            </li>
          ))}
          {s.online > 0 && (
            <li>
              <Localized id="stats-online" vars={{ n: s.online }}>
                <span />
              </Localized>
            </li>
          )}
        </ul>
      )}
      {(s.series.length > 0 || s.unspecified > 0) && (
        <>
          <Localized id="stats-by-series">
            <p className="label" />
          </Localized>
          <ul className="counts">
            {s.series.map((b) => (
              <li key={b.number}>
                {b.number === 0 ? (
                  <Localized id="stats-series-short">
                    <span />
                  </Localized>
                ) : (
                  <Localized id="series-name" vars={{ n: b.number }}>
                    <span />
                  </Localized>
                )}
                <span>{b.practices}</span>
              </li>
            ))}
            {s.unspecified > 0 && (
              <li>
                <Localized id="stats-no-details">
                  <span />
                </Localized>
                <span>{s.unspecified}</span>
              </li>
            )}
          </ul>
        </>
      )}
      {s.duration.count > 0 && (
        <Localized
          id="stats-duration"
          vars={{
            th: Math.floor(s.duration.total_min / 60),
            tm: s.duration.total_min % 60,
            avg,
          }}
        >
          <p className="hint" />
        </Localized>
      )}
      {ofDays && (
        <Localized id="stats-consistency" vars={{ x: s.practiced, y: s.possible }}>
          <p />
        </Localized>
      )}
      {longest >= 2 && (
        <Localized id="stats-run-longest" vars={{ n: longest }}>
          <p className="hint" />
        </Localized>
      )}
      {(ofDays || longest >= 2) && (
        <Localized id="stats-consistency-hint">
          <p className="hint small" />
        </Localized>
      )}
    </>
  );
}
