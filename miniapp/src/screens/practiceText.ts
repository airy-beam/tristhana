// Length labels and zone labels for practice details. Mirrors the bot's wording
// (backend bots/telegram/practice.py) through the same Fluent keys.
import type { ReactLocalization } from "@fluent/react";

import type { Catalog, Length } from "../api/client";
import type { Locale } from "../i18n/negotiate";

/** Fluent isolates placeables with invisible bidi marks; these labels are composed from
 * several messages, so drop the marks to keep them clean. */
const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");

export interface Range {
  first: number; // 0 = short practice
  last: number;
  firstPart: "first_half" | "second_half" | null;
}

export const sameLength = (a: Length | null | undefined, b: Length | null | undefined) =>
  !!a &&
  !!b &&
  a.series.join() === b.series.join() &&
  (a.end ?? null) === (b.end ?? null) &&
  (a.first_part ?? null) === (b.first_part ?? null);

export function rangeOf(catalog: Catalog, length: Length): Range | null {
  if (length.series.length === 0) return { first: 0, last: 0, firstPart: null };
  const numbers = length.series.map((slug) => catalog.series.find((s) => s.slug === slug)?.number);
  const [first, last] = [numbers[0], numbers[numbers.length - 1]];
  if (first === undefined || last === undefined) return null;
  return { first, last, firstPart: length.first_part ?? null };
}

export function lengthOf(catalog: Catalog, range: Range, end: string | null): Length {
  const series = catalog.series
    .filter((s) => range.first > 0 && s.number >= range.first && s.number <= range.last)
    .map((s) => s.slug);
  return { series, end, first_part: range.firstPart };
}

export function rangeText(l10n: ReactLocalization, range: Range, only = false): string {
  const names: string[] = [];
  for (let n = range.first; n <= range.last; n++) {
    if (n === range.first && range.firstPart) {
      const key = range.firstPart === "first_half" ? "half-first" : "half-second";
      names.push(get(l10n, key, { series: get(l10n, "series-half", { n }) }));
    } else {
      names.push(get(l10n, names.length ? "series-lower" : "series-name", { n }));
    }
  }
  if (only && range.first === range.last && !range.firstPart) {
    return get(l10n, "length-only", {
      series: get(l10n, "series-lower", { n: range.last }),
    });
  }
  return names.join(" + ");
}

export function lengthText(
  l10n: ReactLocalization,
  catalog: Catalog,
  length: Length,
  locale: Locale,
): string {
  const range = rangeOf(catalog, length);
  if (!range) return length.series.join(" + ");
  if (range.first === 0) return get(l10n, "length-summary", { kind: "short" });
  const text = rangeText(l10n, range);
  if (!length.end) {
    const kind = length.series.length === 1 && !length.first_part ? "full-one" : "full";
    return get(l10n, "length-summary", { kind, range: text });
  }
  const last = catalog.series.find((s) => s.number === range.last);
  const stop = last?.stops.find((s) => s.key === length.end);
  const asana = stop ? (locale === "ru" ? stop.ru : stop.latin) : length.end;
  return get(l10n, "length-summary", { kind: "to", range: text, asana });
}

/** "Almaty (UTC+5)": the city from the IANA id, the offset on `day` (at `time`, so a DST
 * switch day is right) from Intl. */
export function zoneLabel(zone: string, day: string, time = "12:00", place?: string): string {
  // `place`: the home city's name, only when it is this zone's city (ADR-0029, see placeFor).
  const city = place ?? (zone.split("/").pop() ?? zone).replace(/_/g, " ");
  if (zone === "UTC") return "UTC";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    timeZoneName: "shortOffset",
  }).formatToParts(new Date(`${day}T${time}:00Z`));
  const gmt = parts.find((p) => p.type === "timeZoneName")?.value ?? "GMT";
  return `${city} (${gmt === "GMT" ? "UTC" : gmt.replace("GMT", "UTC")})`;
}

function get(l10n: ReactLocalization, id: string, args?: Record<string, string | number>): string {
  return plain(l10n.getString(id, args));
}
