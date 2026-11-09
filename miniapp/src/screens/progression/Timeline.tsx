import { Localized, useLocalization, type ReactLocalization } from "@fluent/react";
import { useMemo, type ReactNode } from "react";

import {
  useCatalog,
  useTimeline,
  type Catalog,
  type Celebration,
  type TimelineEntry,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { lengthText } from "../practiceText";
import { ShareButton } from "../share/ShareButton";
import { celebrationLines, get, isStanding, itemLabel, stopLabel } from "./progressionText";

interface Props {
  locale: Locale;
  onBack: () => void;
}

/** "🗓 My asanas over time" (ST-04): the whole record, newest first under year headings, each
 * entry with what it meant when it happened (computed on the server, ADR-0020). Read-only: undo
 * stays in My asanas → History. Its own chunk, opened from My asanas. */
export default function Timeline({ locale, onBack }: Props) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const catalog = useCatalog().data;
  const timeline = useTimeline().data;
  return (
    <main className="screen progression timeline">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="timeline-title">
        <h1 />
      </Localized>
      {!catalog || !timeline ? (
        <div aria-busy="true" />
      ) : !timeline.set ? (
        <section className="card">
          <Localized id="timeline-empty-unset">
            <p />
          </Localized>
          <Localized id="progression-open">
            <button type="button" className="link" onClick={onBack} />
          </Localized>
        </section>
      ) : (
        <Entries catalog={catalog} entries={timeline.entries} locale={locale}>
          {timeline.entries.length === 1 && (
            <Localized id="timeline-empty-start">
              <p className="hint" />
            </Localized>
          )}
          {timeline.truncated && (
            <p className="hint">
              {get(l10n, "timeline-truncated", { count: timeline.entries.length })}
            </p>
          )}
        </Entries>
      )}
    </main>
  );
}

function Entries({
  catalog,
  entries,
  locale,
  children,
}: {
  catalog: Catalog;
  entries: readonly TimelineEntry[];
  locale: Locale;
  children?: ReactNode;
}) {
  const { l10n } = useLocalization();
  const format = useMemo(
    () => new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }),
    [locale],
  );
  const years: { year: string; entries: TimelineEntry[] }[] = [];
  for (const e of entries) {
    const year = e.occurred_on.slice(0, 4);
    const last = years.at(-1);
    if (last?.year === year) last.entries.push(e);
    else years.push({ year, entries: [e] });
  }
  return (
    <>
      {children}
      {years.map(({ year, entries: inYear }, index) => (
        // Dates aren't monotonic in id (a zone change around New Year): a year can repeat.
        <section key={`${year}-${String(index)}`} className="card history">
          <h2>{year}</h2>
          <ol>
            {inYear.map((e) => (
              <Entry
                key={e.id}
                entry={e}
                day={format.format(new Date(`${e.occurred_on}T00:00:00Z`))}
                catalog={catalog}
                locale={locale}
                l10n={l10n}
              />
            ))}
          </ol>
        </section>
      ))}
    </>
  );
}

const SERIES_KINDS = new Set(["series_begins", "series_complete"]);

/** The series lines of one give in practice order: a series is full before the next begins. */
export function markersInOrder(catalog: Catalog, found: readonly Celebration[]): Celebration[] {
  const number = (slug: string | null) =>
    catalog.series.find((s) => s.slug === slug)?.number ?? Number.MAX_SAFE_INTEGER;
  const rank = (c: Celebration) => number(c.series) * 2 + (c.kind === "series_complete" ? 1 : 0);
  return found.filter((c) => SERIES_KINDS.has(c.kind)).sort((a, b) => rank(a) - rank(b));
}

function seriesName(l10n: ReactLocalization, catalog: Catalog, slug: string | null | undefined) {
  const series = catalog.series.find((s) => s.slug === slug);
  return series ? get(l10n, "series-name", { n: series.number }) : null;
}

function teacherBy(l10n: ReactLocalization, e: TimelineEntry): string {
  if (e.by !== "teacher") return "";
  const teacher = e.by_name ?? get(l10n, "progression-by-teacher");
  return ` ${get(l10n, "progression-event-by", { teacher })}`;
}

function Entry({
  entry: e,
  day,
  catalog,
  locale,
  l10n,
}: {
  entry: TimelineEntry;
  day: string;
  catalog: Catalog;
  locale: Locale;
  l10n: ReactLocalization;
}) {
  const asana = isStanding(e.to)
    ? get(l10n, "progression-standing-only")
    : stopLabel(catalog, e.to, locale);
  const by = teacherBy(l10n, e);
  if (e.kind === "start") {
    const length = e.length ? lengthText(l10n, catalog, e.length, locale) : asana;
    return (
      <li>
        <span className="hint">{day}</span> {get(l10n, "timeline-start", { length })}
        {by}
      </li>
    );
  }
  if (e.kind !== "given") {
    const item = e.item ? itemLabel(l10n, catalog, e.item, locale) : "";
    const quiet = e.kind === "changed" || e.kind === "item_removed";
    return (
      <li className={quiet ? "muted" : undefined}>
        <span className="hint">{day}</span>{" "}
        {e.kind === "item_removed"
          ? get(l10n, "timeline-item-removed", { item }) // past-safe (Q229)
          : get(l10n, "progression-event", { kind: e.kind, asana, item })}
        {by}
      </li>
    );
  }
  const found = e.celebrations;
  const isNew = found.find((c) => c.kind === "new_asana");
  const markers = celebrationLines(l10n, catalog, markersInOrder(catalog, found), locale);
  const series = seriesName(l10n, catalog, e.to?.series);
  const across = !!isNew?.first && isNew.first.series !== e.to?.series;
  let line: string;
  if (!isNew) {
    line = get(l10n, "timeline-given-again", { asana }); // past-safe, no 🎉 (Q223, Q229)
  } else if (isNew.first && across) {
    line = get(l10n, "timeline-given-across", {
      from: stopLabel(catalog, isNew.first, locale),
      from_series: seriesName(l10n, catalog, isNew.first.series) ?? "",
      asana,
      series: series ?? "",
    });
  } else if (isNew.first) {
    line = get(l10n, "timeline-given-range", {
      from: stopLabel(catalog, isNew.first, locale),
      asana,
    });
  } else {
    line = get(l10n, "progression-event", { kind: "given", asana, item: "" });
  }
  const label = series && !across ? ` · ${get(l10n, "timeline-series", { series })}` : "";
  return (
    <li>
      {markers.map((m) => (
        <p key={m} className="milestone">
          {m}
        </p>
      ))}
      <span className="hint">{day}</span> {line}
      <span className="hint">{label}</span>
      {by}{" "}
      <ShareButton
        subject={{ kind: "asana", event_id: e.id }}
        label={get(l10n, "share-entry", { entry: `${day}: ${line}` })}
      />
    </li>
  );
}
