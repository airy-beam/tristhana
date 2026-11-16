/** When a displayed time carries its UTC offset (ADR-0044): the twin of the backend's
 * `domain/time_label.py`, tested against the same table. The place always shows
 * (`07:00 Almaty`); the offset is added only for a zone that is not the viewer's own
 * (`17:30 Berlin (UTC+1)`). */

const UTC = "UTC";
const DAY_MS = 86_400_000;

/** One zone, two names. Chrome and Android's WebView still report CLDR's ids (the keys); the
 * seeded cities and Firefox use IANA's own (the values). The same table as the backend's
 * `ZONE_ALIASES`; both test files pin it. */
export const ZONE_ALIASES: Readonly<Partial<Record<string, string>>> = {
  "Africa/Asmera": "Africa/Asmara",
  "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
  "America/Catamarca": "America/Argentina/Catamarca",
  "America/Cordoba": "America/Argentina/Cordoba",
  "America/Jujuy": "America/Argentina/Jujuy",
  "America/Mendoza": "America/Argentina/Mendoza",
  "America/Coral_Harbour": "America/Atikokan",
  "America/Godthab": "America/Nuuk",
  "America/Indianapolis": "America/Indiana/Indianapolis",
  "America/Louisville": "America/Kentucky/Louisville",
  "Asia/Calcutta": "Asia/Kolkata",
  "Asia/Katmandu": "Asia/Kathmandu",
  "Asia/Rangoon": "Asia/Yangon",
  "Asia/Saigon": "Asia/Ho_Chi_Minh",
  "Atlantic/Faeroe": "Atlantic/Faroe",
  "Europe/Kiev": "Europe/Kyiv",
  "Pacific/Enderbury": "Pacific/Kanton",
  "Pacific/Ponape": "Pacific/Pohnpei",
  "Pacific/Truk": "Pacific/Chuuk",
};

/** IANA's own name for a zone that also goes by an older one (`Asia/Calcutta`). */
const canonical = (zone: string) => ZONE_ALIASES[zone] ?? zone;

/** False in the viewer's own zone: the same IANA zone (under either of its names), not an
 * equal clock, so the answer never flips on a daylight-saving date. An unknown viewer zone
 * shows the offset (nothing is "your own" yet). `UTC` never gets one: `07:00 UTC` already
 * says it. */
export function offsetShown(zone: string, viewer: string | null | undefined): boolean {
  return zone !== UTC && (!viewer || canonical(zone) !== canonical(viewer));
}

const formats = new Map<string, Intl.DateTimeFormat>();

/** Minutes east of UTC in `zone` at an instant. */
function minutesAt(zone: string, instant: number): number {
  let format = formats.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" });
    formats.set(zone, format);
  }
  const name = format.formatToParts(instant).find((p) => p.type === "timeZoneName")?.value;
  const m = /([+-])(\d+)(?::(\d+))?/.exec(name ?? ""); // "GMT+5:30"; a bare "GMT" is zero
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] ?? 0)) : 0;
}

/** `UTC+5`, `UTC+5:30`, `UTC-3:30`, `UTC+0`: the zone's offset at that wall-clock time
 * (`HH:MM`) on that date (`YYYY-MM-DD`), so daylight saving is right. */
export function offsetText(zone: string, day: string, at: string): string {
  // The wall clock read as UTC is off by the very offset we are after. So take the offsets a
  // day either side and keep the one that maps the wall time back onto itself. The earlier
  // one wins an hour that repeats or never happens, as the backend's `zoneinfo` does.
  const wall = Date.parse(`${day}T${at.slice(0, 5)}:00Z`);
  const before = minutesAt(zone, wall - DAY_MS);
  const after = minutesAt(zone, wall + DAY_MS);
  const fits = (m: number) => minutesAt(zone, wall - m * 60_000) === m;
  const minutes = before === after || fits(before) || !fits(after) ? before : after;
  const abs = Math.abs(minutes);
  const part = abs % 60 ? `:${String(abs % 60).padStart(2, "0")}` : "";
  return `UTC${minutes < 0 ? "-" : "+"}${String(Math.floor(abs / 60))}${part}`;
}

/** "Almaty" from "Asia/Almaty", "New York" from "America/New_York". */
export const zoneCity = (zone: string) => (zone.split("/").pop() ?? zone).replace(/_/g, " ");

export interface LabelOptions {
  /** The wall-clock time the label stands next to (`HH:MM`); noon when it labels a day. */
  at?: string | undefined;
  /** The home city's name, only when it is this zone's city (ADR-0029, see `placeFor`). */
  place?: string | undefined;
  /** The viewer's own IANA zone (the account's). Left out, the offset always shows: that is
   * for text saying what a zone is (the travel prompt, a daylight-saving day row), where the
   * offset is the information. */
  viewer?: string | null | undefined;
}

/** The time label minus the time: "Almaty" for a viewer in that zone, "Almaty (UTC+5)" (the
 * offset on `day` at `at`) for anyone else. */
export function zoneLabel(zone: string, day: string, options: LabelOptions = {}): string {
  if (zone === UTC) return UTC;
  const city = options.place ?? zoneCity(zone);
  if (!offsetShown(zone, options.viewer)) return city;
  return `${city} (${offsetText(zone, day, options.at ?? "12:00")})`;
}

/** "07:00 Almaty" / "17:30 Berlin (UTC+1)" / "07:00 UTC". */
export function timeLabel(
  at: string,
  zone: string,
  day: string,
  options: Omit<LabelOptions, "at"> = {},
): string {
  return `${at} ${zoneLabel(zone, day, { ...options, at })}`;
}
