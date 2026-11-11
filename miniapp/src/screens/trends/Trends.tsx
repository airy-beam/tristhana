import { Localized, useLocalization } from "@fluent/react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";

import { api, fail, useMoonCities, type CheckInTrends, type TrendScales } from "../../api/client";
import { addMessages } from "../../i18n/lazyMessages";
import type { Locale } from "../../i18n/negotiate";
import enTrends from "../../locales/en/trends.ftl?raw";
import ruTrends from "../../locales/ru/trends.ftl?raw";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { cityName } from "../MoonCard";
import { get } from "../progression/progressionText";

addMessages({ en: enTrends, ru: ruTrends });

const SCALES = ["mood", "energy", "effort"] as const;
type Scale = (typeof SCALES)[number];
interface Column {
  key: string;
  /** Short, for the header cell. */
  head: string;
  /** Full, for what is read aloud. */
  where: string;
  scales: TrendScales;
}

function useTrends() {
  return useQuery({
    queryKey: ["me", "check-in-trends"],
    queryFn: async (): Promise<CheckInTrends> => {
      const { data, error, response } = await api.GET("/api/v1/me/check-in-trends");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 0, // opened rarely; every opening reads the current numbers
  });
}

/** "✨ Check-ins over time" (ST-05): the person's own averages by month, by weekday and near a
 * full or new moon. The server decides what has enough check-ins behind it; this only draws.
 * Figures and their counts, nothing else: no comparison, no colour for high or low, no advice.
 * Its own chunk (with its copy), opened from My practice. */
export default function TrendsScreen({ locale, onBack }: { locale: Locale; onBack: () => void }) {
  useBackButton(onBack);
  const query = useTrends();
  const data = query.data;
  return (
    <main className="screen trends">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="trends-title">
        <h1 />
      </Localized>
      {query.isError ? (
        <Localized id="trends-load-failed">
          <p className="status" role="alert" />
        </Localized>
      ) : !data ? (
        <div aria-busy="true" />
      ) : data.total === 0 ? (
        <Localized id="trends-empty">
          <p className="card" />
        </Localized>
      ) : !data.enough ? (
        <Localized id="trends-too-few" vars={{ min: data.min_total }}>
          <p className="card" />
        </Localized>
      ) : (
        <Views data={data} locale={locale} />
      )}
      <Localized id="trends-note">
        <p className="hint small" />
      </Localized>
    </main>
  );
}

const utc = (iso: string) => new Date(`${iso}T00:00:00Z`);

function Views({ data, locale }: { data: CheckInTrends; locale: Locale }) {
  const { l10n } = useLocalization();
  const cities = useMoonCities().data;
  const columns = useMemo(() => {
    const narrow = new Intl.DateTimeFormat(locale, { month: "narrow", timeZone: "UTC" });
    const long = new Intl.DateTimeFormat(locale, {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
    const short = new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" });
    const full = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" });
    const months: Column[] = data.months.map((m) => {
      const first = utc(`${m.month}-01`);
      return { key: m.month, head: narrow.format(first), where: long.format(first), scales: m };
    });
    const weekdays: Column[] | null =
      data.weekdays?.map((scales, i) => {
        const day = utc(`2024-01-0${String(i + 1)}`); // 1 January 2024 was a Monday
        return { key: String(i), head: short.format(day), where: full.format(day), scales };
      }) ?? null;
    return { months, weekdays };
  }, [data, locale]);
  const byMoon = data.moon;
  const moon: Column[] | null = byMoon
    ? (["full", "new", "other"] as const).map((bucket) => {
        const label = get(l10n, `trends-moon-${bucket}`);
        return { key: bucket, head: label, where: label, scales: byMoon[bucket] };
      })
    : null;
  const number = useMemo(
    () => new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    [locale],
  );
  const shown = [...(columns.weekdays ?? []), ...(moon ?? [])];
  const gap = shown.some((c) => SCALES.some((s) => c.scales[s] === null));
  const city = byMoon
    ? cityName(
        cities?.find((c) => c.slug === byMoon.location),
        byMoon.location,
        locale,
      )
    : "";
  return (
    <>
      <Localized id="trends-window">
        <p className="hint" />
      </Localized>
      <Section id="trends-by-month">
        {SCALES.map((scale) => (
          <Strip key={scale} scale={scale} months={columns.months} />
        ))}
        <div className="visually-hidden">
          <Grid caption="trends-by-month" columns={columns.months} format={number} />
        </div>
      </Section>
      {columns.weekdays && (
        <Section id="trends-by-weekday">
          <Grid caption="trends-by-weekday" columns={columns.weekdays} format={number} />
        </Section>
      )}
      {moon && (
        <Section id="trends-by-moon">
          <Grid caption="trends-by-moon" columns={moon} format={number} />
          <Localized id="trends-moon-note" vars={{ city }}>
            <p className="hint small" />
          </Localized>
        </Section>
      )}
      {shown.length > 0 && (
        <Localized id="trends-count-hint">
          <p className="hint small" />
        </Localized>
      )}
      {gap && (
        <Localized id="trends-gap-note" vars={{ min: data.min_bucket }}>
          <p className="hint small" />
        </Localized>
      )}
    </>
  );
}

function Section({ id, children }: { id: string; children: ReactNode }) {
  return (
    <section className="card" aria-labelledby={id}>
      <Localized id={id}>
        <h2 id={id} />
      </Localized>
      {children}
    </section>
  );
}

const WIDTH = 240;
const TOP = 6;
const BOTTOM = 46; // the 1-5 axis runs from BOTTOM up to TOP
const y = (value: number) => BOTTOM - ((value - 1) / 4) * (BOTTOM - TOP);

/** One scale over the 12 months: a dot per month that has an average, on a fixed 1-5 axis.
 * Dots only, never a line: a line would draw values for months that have none. The picture
 * is decorative; the same numbers are in the hidden table beside it. */
function Strip({ scale, months }: { scale: Scale; months: readonly Column[] }) {
  const step = WIDTH / months.length;
  return (
    <figure className="trend-strip">
      {/* The caption names the scale and the ends of its axis. */}
      <Localized id={scale === "mood" ? "trends-mood-ends" : `checkin-${scale}`}>
        <figcaption className="hint small" />
      </Localized>
      <svg viewBox={`0 0 ${String(WIDTH)} 60`} aria-hidden="true">
        {[1, 3, 5].map((v) => (
          <line key={v} x1={0} x2={WIDTH} y1={y(v)} y2={y(v)} />
        ))}
        {months.map((m, i) => {
          const found = m.scales[scale];
          const x = step * (i + 0.5);
          return (
            <g key={m.key}>
              {found && <circle cx={x} cy={y(found.mean)} r={3} />}
              <text x={x} y={58}>
                {m.head}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/** Scales down, columns across; each cell is the average with its count under it, or "—". */
function Grid({
  caption,
  columns,
  format,
}: {
  caption: string;
  columns: readonly Column[];
  format: Intl.NumberFormat;
}) {
  const { l10n } = useLocalization();
  return (
    <table className="trend-grid" aria-labelledby={caption}>
      <thead>
        <tr>
          <td />
          {columns.map((c) => (
            <th key={c.key} scope="col" aria-label={c.where}>
              {c.head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {SCALES.map((scale) => {
          const name = get(l10n, "trends-scale", { scale });
          return (
            <tr key={scale}>
              <th scope="row" aria-label={name}>
                {get(l10n, "trends-scale-icon", { scale })}
              </th>
              {columns.map((c) => {
                const found = c.scales[scale];
                const vars = { scale: name, where: c.where };
                return found ? (
                  <td
                    key={c.key}
                    aria-label={get(l10n, "trends-cell-label", {
                      ...vars,
                      mean: format.format(found.mean),
                      n: found.n,
                    })}
                  >
                    {format.format(found.mean)}
                    <small>{found.n}</small>
                  </td>
                ) : (
                  <td key={c.key} aria-label={get(l10n, "trends-cell-none", vars)}>
                    {get(l10n, "trends-none")}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
