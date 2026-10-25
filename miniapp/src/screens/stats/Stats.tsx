import { Localized } from "@fluent/react";
import { useCallback, useMemo, useState, type ReactNode } from "react";

import {
  useMe,
  useMoonCities,
  useNotificationSettings,
  useStats,
  type Stats as StatsData,
  type StatsSummary,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { cityName } from "../MoonCard";
import { DayOffQuestion } from "../DayOffQuestion";
import { autoDays, loadShowLadies, moonDates, parse, saveShowLadies } from "./cells";
import { DayEditor } from "./DayEditor";
import { Heatmap } from "./Heatmap";
import { MonthView } from "./MonthView";

interface Props {
  locale: Locale;
  zone: string | null;
  onBack: () => void;
  /** Settings, scrolled to the day off (the stats question's "Other…" and link). */
  onDayOff: () => void;
}

/** "My practice": consistency, the year heatmap, a month calendar and its summary
 * (ST-01..03). Loaded lazily, so Home stays light. */
export default function Stats({ locale, zone, onBack, onDayOff }: Props) {
  useBackButton(onBack);
  const [year, setYear] = useState<number | undefined>(undefined);
  const query = useStats(year);
  const stats = query.data;
  // Outside Telegram (or on clients without its Back button) the screen needs its own.
  const back = backButtonAvailable() ? null : (
    <Localized id="stats-back">
      <button type="button" className="link" onClick={onBack} />
    </Localized>
  );
  if (query.isError) {
    return (
      <main className="screen">
        {back}
        <Localized id="stats-load-failed">
          <p className="status" role="alert" />
        </Localized>
      </main>
    );
  }
  if (!stats) return <main className="screen" aria-busy="true" />;
  const pick = (y: number) => {
    // The current year is cached as "current": going back to it needs no refetch.
    setYear(y === Number(stats.today.slice(0, 4)) ? undefined : y);
  };
  return (
    <Loaded
      key={stats.year}
      stats={stats}
      locale={locale}
      zone={zone}
      onYear={pick}
      onDayOff={onDayOff}
      back={back}
    />
  );
}

function Loaded({
  stats,
  locale,
  zone,
  onYear,
  onDayOff,
  back,
}: {
  stats: StatsData;
  locale: Locale;
  zone: string | null;
  onYear: (year: number) => void;
  onDayOff: () => void;
  back: ReactNode;
}) {
  const cities = useMoonCities().data;
  const currentYear = Number(stats.today.slice(0, 4));
  const isCurrent = stats.year === currentYear;
  const [month, setMonth] = useState(isCurrent ? Number(stats.today.slice(5, 7)) - 1 : 11);
  const [editing, setEditing] = useState<string | null>(null);
  const [showLadies, setShowLadies] = useState(loadShowLadies);
  const moon = useMemo(() => moonDates(stats), [stats]);
  const auto = useMemo(() => autoDays(stats), [stats]);

  const fmt = useMemo(
    () => ({
      month: new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }),
      monthYear: new Intl.DateTimeFormat(locale, {
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }),
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
  const monthName = useCallback(
    (m: number) => fmt.month.format(Date.UTC(stats.year, m, 1)),
    [fmt, stats.year],
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
  const summary = stats.months[month] as StatsSummary;
  const first = stats.first_year ?? currentYear;

  return (
    <main className="screen stats">
      {back}
      <Localized id="stats-title">
        <h1 />
      </Localized>

      {isCurrent && <Consistency stats={stats} onDayOff={onDayOff} />}

      <section className="card" aria-labelledby="year-title">
        <div className="pager">
          <Localized id="stats-prev" attrs={{ "aria-label": true }}>
            <button
              type="button"
              className="link"
              disabled={stats.year <= first}
              onClick={() => {
                onYear(stats.year - 1);
              }}
            />
          </Localized>
          <h2 id="year-title">{stats.year}</h2>
          <Localized id="stats-next" attrs={{ "aria-label": true }}>
            <button
              type="button"
              className="link"
              disabled={isCurrent}
              onClick={() => {
                onYear(stats.year + 1);
              }}
            />
          </Localized>
        </div>
        <Localized
          id="stats-year-total"
          vars={{ n: stats.year_total.practiced, year: String(stats.year) }}
        >
          <p className="hint" />
        </Localized>
        <Heatmap
          stats={stats}
          moon={moon}
          auto={auto}
          city={city}
          showLadies={showLadies}
          month={month}
          onMonth={setMonth}
          monthName={monthName}
          dateLabel={dateLabel}
        />
        <Legend city={city} showLadies={showLadies} />
        <label className="toggle">
          <input
            type="checkbox"
            checked={showLadies}
            onChange={(e) => {
              setShowLadies(e.target.checked);
              saveShowLadies(e.target.checked);
            }}
          />
          <Localized id="stats-show-ladies">
            <span />
          </Localized>
        </label>
      </section>

      <section className="card" aria-labelledby="month-title">
        <h2 id="month-title" tabIndex={-1}>
          {fmt.monthYear.format(Date.UTC(stats.year, month, 1))}
        </h2>
        <MonthView
          stats={stats}
          month={month}
          moon={moon}
          auto={auto}
          city={city}
          showLadies={showLadies}
          weekdays={weekdays}
          dateLabel={dateLabel}
          onPick={setEditing}
        />
        {editing && (
          <DayEditor
            date={editing}
            label={dateLabel(editing)}
            zone={zone}
            locale={locale}
            showLadies={showLadies}
            onClose={() => {
              setEditing(null);
            }}
          />
        )}
        <MonthSummary
          summary={summary}
          showLadies={showLadies}
          current={isCurrent && month === Number(stats.today.slice(5, 7)) - 1}
        />
      </section>
    </main>
  );
}

function Consistency({ stats, onDayOff }: { stats: StatsData; onDayOff: () => void }) {
  const month = stats.months[Number(stats.today.slice(5, 7)) - 1] as StatsSummary;
  const current = stats.runs.current ?? 0;
  const unset = useMe().data?.day_off === null;
  return (
    <section className="card">
      {month.practiced === 0 ? null : month.skipped > 0 ? (
        <Localized id="stats-consistency" vars={{ x: month.practiced, y: month.possible }}>
          <p />
        </Localized>
      ) : (
        <Localized id="stats-consistency-count" vars={{ n: month.practiced }}>
          <p />
        </Localized>
      )}
      {current >= 2 && (
        <Localized id="stats-run-current" vars={{ n: current }}>
          <p />
        </Localized>
      )}
      {stats.runs.longest >= 2 && (
        <Localized id="stats-run-longest" vars={{ n: stats.runs.longest }}>
          <p className="hint" />
        </Localized>
      )}
      <Localized id="stats-consistency-hint">
        <p className="hint small" />
      </Localized>
      {/* PR-09: asked once; afterwards (or when it can't be asked) a quiet link. */}
      {unset && <DayOffLink onDayOff={onDayOff} />}
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

const LEGEND = ["practiced", "rest", "moon", "auto", "away", "skipped", "none"] as const;

function Legend({ city, showLadies }: { city: string; showLadies: boolean }) {
  const items: string[] = [...LEGEND];
  if (showLadies) items.splice(3, 0, "ladies");
  return (
    <ul className="legend">
      {items.map((k) => (
        <li key={k}>
          <span className={`swatch ${k}`} aria-hidden="true" />
          <Localized id={k === "ladies" ? "status-ladies" : `stats-legend-${k}`}>
            <span />
          </Localized>
        </li>
      ))}
      <li>
        <span className="swatch ring" aria-hidden="true" />
        <Localized id="stats-legend-moon-marker" vars={{ city }}>
          <span />
        </Localized>
      </li>
    </ul>
  );
}

function MonthSummary({
  summary: s,
  showLadies,
  current,
}: {
  summary: StatsSummary;
  showLadies: boolean;
  current: boolean;
}) {
  // Auto-rest counts as rest below, but a month with only auto days is still "empty".
  const logged =
    s.practiced + s.skipped + Object.values(s.rest).reduce((a, b) => a + b, 0) - s.auto;
  const unmarked = current && s.unlogged > 0 && (
    <Localized id="stats-unlogged" vars={{ n: s.unlogged }}>
      <p className="hint" />
    </Localized>
  );
  if (logged === 0) {
    return (
      <>
        <Localized id="stats-month-empty">
          <p className="hint" />
        </Localized>
        {unmarked}
      </>
    );
  }
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
  return (
    <div className="summary">
      <Localized id="stats-month-practices" vars={{ n: s.practiced }}>
        <p />
      </Localized>
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
      {unmarked}
    </div>
  );
}
