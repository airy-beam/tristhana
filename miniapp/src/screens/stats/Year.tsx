import { Localized, useLocalization } from "@fluent/react";
import { useCallback, useMemo, useState } from "react";

import { useMoonCities } from "../../api/client";
import { monthTitle } from "../../i18n/dates";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, haptics, useBackButton } from "../../telegram";
import { cityName } from "../cityName";
import { ShareButton } from "../share/ShareButton";
import { autoDays, monthOf, moonDates, parse, type Month } from "./cells";
import { Heatmap } from "./Heatmap";
import { Legend } from "./Legend";
import { useKeptStats } from "./useKeptStats";

import "./stats.css";

interface Props {
  locale: Locale;
  /** The month the Practice tab shows: the year to open on, and the month marked here. */
  shown: Month;
  /** The server's today: the last year, and the last month that can be opened. */
  today: string;
  /** The first year with anything logged. */
  first: number;
  /** A tap on a month: the tab shows it, and this layer closes. */
  onPick: (month: Month) => void;
  onBack: () => void;
}

/** The year behind the Practice tab's "📅 2026" row (UI-06 stage 3, QD): the year's total with
 * Share, twelve small months and the legend. A layer over the tab, in its own chunk: Back
 * returns to the month that was shown, a tap on a month opens that one. */
export default function Year({ locale, shown, today, first, onPick, onBack }: Props) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const cities = useMoonCities().data;
  const now = monthOf(today);
  const [year, setYear] = useState(shown.year);
  const { stats, failed } = useKeptStats(year, today);
  const moon = useMemo(() => stats && moonDates(stats), [stats]);
  const auto = useMemo(() => stats && autoDays(stats), [stats]);
  const fmt = useMemo(
    () => ({
      day: new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
        timeZone: "UTC",
      }),
    }),
    [locale],
  );
  // The layer's heading takes the focus when it opens.
  const heading = useCallback((element: HTMLHeadingElement | null) => {
    element?.focus({ preventScroll: true });
  }, []);
  const step = (to: number) => {
    haptics.selection();
    setYear(to);
  };
  // While another year loads, the one before stays, under its own number.
  const on = stats?.year ?? year;
  return (
    <main className="screen stats" aria-busy={!stats && !failed ? true : undefined}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <div className="pager">
        <Localized id="stats-prev" attrs={{ "aria-label": true }}>
          <button
            type="button"
            className="link"
            disabled={year <= first}
            onClick={() => {
              step(year - 1);
            }}
          />
        </Localized>
        <h1 ref={heading} tabIndex={-1}>
          {on}
        </h1>
        <Localized id="stats-next" attrs={{ "aria-label": true }}>
          <button
            type="button"
            className="link"
            disabled={year >= now.year}
            onClick={() => {
              step(year + 1);
            }}
          />
        </Localized>
      </div>
      {failed && (
        <Localized id="stats-load-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
      {stats && moon && auto && (
        <section className="card">
          <div className="card-head">
            <Localized
              id="stats-year-total"
              vars={{ n: stats.year_total.practiced, year: String(stats.year) }}
            >
              <p className="total" />
            </Localized>
            {stats.year_total.practiced > 0 && (
              <ShareButton
                subject={{ kind: "year", year: stats.year }}
                label={l10n.getString("share-entry", { entry: String(stats.year) })}
              />
            )}
          </div>
          <Heatmap
            stats={stats}
            moon={moon}
            auto={auto}
            city={cityName(
              cities?.find((c) => c.slug === stats.moon.location),
              stats.moon.location,
              locale,
            )}
            shown={stats.year === shown.year ? shown.month : undefined}
            last={stats.year < now.year ? 11 : now.month}
            onMonth={(month) => {
              haptics.selection();
              onPick({ year: stats.year, month });
            }}
            monthName={(m) => monthTitle(stats.year, m, locale, { year: false })}
            dateLabel={(day) => fmt.day.format(parse(day))}
          />
          <Legend />
        </section>
      )}
    </main>
  );
}
