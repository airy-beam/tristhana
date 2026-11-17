import { useSyncExternalStore } from "react";

import type { AutoDay, Stats } from "../../api/client";

export type Cell = Stats["cells"][number];
/** What a day is drawn as (ADR-0020, UI-06 stage 3): one of three fills, or nothing for a day
 * with nothing logged. The moon is a ring over any of them, never a fill. */
export type Kind = "practiced" | "rest" | "skipped" | "none";

/** Rest is one colour: a logged rest or moon day, sick, travel, a ladies' holiday, and an
 * unlogged day off or moon day (`auto`, PR-09). */
export function kindOf(cell: Cell, auto: boolean): Kind {
  switch (cell) {
    case "practiced":
    case "skipped":
      return cell;
    case "none":
      return auto ? "rest" : "none";
    case "rest":
    case "moon":
    case "ladies":
    case "sick":
    case "travel":
      return "rest";
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

/** The Fluent key that names a cell: a ladies' holiday is "Rest day" unless the person shows
 * 🌸 on this device. */
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

/** A month of a year; `month` is 0 for January. */
export interface Month {
  year: number;
  month: number;
}
/** The month of an ISO date: the server's `today` gives the current one, never the device. */
export const monthOf = (day: string): Month => ({
  year: Number(day.slice(0, 4)),
  month: Number(day.slice(5, 7)) - 1,
});
/** Months since year 0: to compare two months and to step between them. */
export const monthIndex = (m: Month) => m.year * 12 + m.month;
export const monthAt = (index: number): Month => ({
  year: Math.floor(index / 12),
  month: index % 12,
});

/** The cell for a date, or undefined after today (future days have no cell). */
export function cellAt(stats: Stats, day: string): Cell | undefined {
  return stats.cells[dayIndex(stats.year, day)];
}

/** Moon rings: every moon day of a past date, and future ones in the current month. */
export function moonDates(stats: Stats): Set<string> {
  const now = monthOf(stats.today);
  const endOfMonth = dateOf(now.year, now.month, daysInMonth(now.year, now.month));
  return new Set(stats.moon.days.map((d) => d.date).filter((d) => d <= endOfMonth));
}

export function loadShowLadies(): boolean {
  try {
    return localStorage.getItem("stats.showLadies") === "1";
  } catch {
    return false;
  }
}

const watchers = new Set<() => void>();
const watch = (changed: () => void) => {
  watchers.add(changed);
  return () => {
    watchers.delete(changed);
  };
};

export function saveShowLadies(on: boolean): void {
  try {
    localStorage.setItem("stats.showLadies", on ? "1" : "0");
  } catch {
    // Private mode or blocked storage: the switch just doesn't persist.
  }
  watchers.forEach((changed) => {
    changed();
  });
}

/** The device switch as it is now: Settings changes it while the Practice tab stays mounted
 * underneath, and the calendar follows without a reload. */
export function useShowLadies(): boolean {
  return useSyncExternalStore(watch, loadShowLadies);
}
