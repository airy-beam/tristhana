// Labels for progression (PR-08) and its celebrations (GM-01). Mirrors the bot's wording
// (backend bots/telegram/progression.py) through the same Fluent keys.
import type { ReactLocalization } from "@fluent/react";

import type { Catalog, Celebration, ProgressionPosition } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

/** A composed label without Fluent's bidi isolation marks (as `practiceText`). */
export function get(
  l10n: ReactLocalization,
  id: string,
  args?: Record<string, string | number>,
): string {
  return plain(l10n.getString(id, args));
}

/** The stop's display name; a stale key (the catalog changed) stays readable. */
export function stopLabel(
  catalog: Catalog,
  p: { series: string | null; last: string | null } | null | undefined,
  locale: Locale,
): string {
  if (!p?.last) return "";
  const stop = catalog.series.find((s) => s.slug === p.series)?.stops.find((s) => s.key === p.last);
  return stop ? (locale === "ru" ? stop.ru : stop.latin) : p.last;
}

/** The catalog name, plus "(tic-tacs)" where people use one (Fluent `milestone-label`). */
export function itemLabel(
  l10n: ReactLocalization,
  catalog: Catalog,
  key: string,
  locale: Locale,
): string {
  const item = catalog.milestone_items.find((i) => i.key === key);
  const name = item ? (locale === "ru" ? item.ru : item.latin) : key;
  return get(l10n, "milestone-label", { slug: key, name });
}

export const isStanding = (p: ProgressionPosition | null | undefined) =>
  !!p && p.series === null && p.last === null;

export function celebrationLines(
  l10n: ReactLocalization,
  catalog: Catalog,
  found: readonly Celebration[],
  locale: Locale,
): string[] {
  const lines: string[] = [];
  for (const c of found) {
    if (c.kind === "new_asana") {
      const asana = stopLabel(catalog, { series: c.series, last: c.key }, locale);
      lines.push(
        c.first
          ? get(l10n, "celebrate-new-asanas", {
              from: stopLabel(catalog, c.first, locale),
              asana,
            })
          : get(l10n, "celebrate-new-asana", { asana }),
      );
    } else if (c.kind === "item") {
      lines.push(
        get(l10n, "celebrate-item", { item: itemLabel(l10n, catalog, c.key ?? "", locale) }),
      );
    } else {
      const series = catalog.series.find((s) => s.slug === c.series);
      if (!series) continue;
      const names = series.traditional;
      const id =
        c.kind === "series_complete" ? "celebrate-series-complete" : "celebrate-series-begins";
      lines.push(
        get(l10n, id, {
          series: get(l10n, "series-name", { n: series.number }),
          traditional: names ? (locale === "ru" ? names.ru : names.latin) : "none",
        }),
      );
    }
  }
  return lines;
}
