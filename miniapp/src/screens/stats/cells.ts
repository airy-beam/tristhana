import type { AutoDay, Stats } from "../../api/client";

export type Cell = Stats["cells"][number];
/** What a cell looks like: one colour per status family (ADR-0020); "auto" = an unlogged
 * day shown as rest (PR-09), lighter than a logged one. */
export type Kind = "practiced" | "rest" | "moon" | "ladies" | "away" | "skipped" | "none" | "auto";

/** A ladies' holiday looks like rest unless the person shows 🌸 days on this device. */
export function kindOf(cell: Cell, showLadies: boolean): Kind {
  switch (cell) {
    case "practiced":
    case "rest":
    case "moon":
    case "skipped":
    case "none":
      return cell;
    case "ladies":
      return showLadies ? "ladies" : "rest";
    case "sick":
    case "travel":
      return "away";
  }
}

/** The year's auto-rest by date (the server only sends unlogged days up to today). */
export function autoDays(stats: Stats): Map<string, AutoDay> {
  return new Map(stats.auto.map((a) => [a.date, a]));
}

/** `stats-cell-auto` arguments: "Sat, Oct 24: 🌙 moon day (📍 Mysuru), not logged". */
export function autoArgs(auto: AutoDay, date: string, city: string) {
  return { date, kind: auto.kind, city, dayoff: auto.also_day_off ? "yes" : "no" };
}

/** The Fluent key that names a cell (aria labels follow the 🌸 switch too). */
export function labelKey(cell: Cell, showLadies: boolean): string {
  if (cell === "none") return "stats-legend-none";
  if (cell === "ladies" && !showLadies) return "status-rest";
  return `status-${cell}`;
}

const DAY_MS = 86_400_000;
export const parse = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
export const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
export const addDays = (day: string, n: number) => iso(parse(day) + n * DAY_MS);
export const dayIndex = (year: number, day: string) =>
  Math.round((parse(day) - Date.UTC(year, 0, 1)) / DAY_MS);
export const daysInMonth = (year: number, month: number) =>
  new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
/** 0 = Monday … 6 = Sunday (weeks start on Monday in both languages). */
export const mondayFirst = (year: number, month: number, day = 1) =>
  (new Date(Date.UTC(year, month, day)).getUTCDay() + 6) % 7;
export const pad = (n: number) => String(n).padStart(2, "0");
export const dateOf = (year: number, month: number, day: number) =>
  `${String(year)}-${pad(month + 1)}-${pad(day)}`;

/** The cell for a date, or undefined after today (future days have no cell). */
export function cellAt(stats: Stats, day: string): Cell | undefined {
  return stats.cells[dayIndex(stats.year, day)];
}

/** Moon rings: every moon day of a past date, and future ones in the current month. */
export function moonDates(stats: Stats): Set<string> {
  const endOfMonth = (() => {
    const [y, m] = stats.today.split("-").map(Number) as [number, number];
    return dateOf(y, m - 1, daysInMonth(y, m - 1));
  })();
  return new Set(stats.moon.days.map((d) => d.date).filter((d) => d <= endOfMonth));
}

export function loadShowLadies(): boolean {
  try {
    return localStorage.getItem("stats.showLadies") === "1";
  } catch {
    return false;
  }
}

export function saveShowLadies(on: boolean): void {
  try {
    localStorage.setItem("stats.showLadies", on ? "1" : "0");
  } catch {
    // Private mode or blocked storage: the switch just doesn't persist.
  }
}
