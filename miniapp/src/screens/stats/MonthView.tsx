import { useLocalization } from "@fluent/react";

import type { AutoDay, Stats } from "../../api/client";
import { autoArgs, cellAt, dateOf, daysInMonth, kindOf, labelKey, mondayFirst } from "./cells";

interface Props {
  stats: Stats;
  month: number;
  moon: Set<string>;
  auto: Map<string, AutoDay>;
  /** The followed city, named in an unlogged moon day. */
  city: string;
  /** The device switch: a ladies' holiday gets its small mark and its own name. */
  showLadies: boolean;
  weekdays: string[];
  dateLabel: (day: string) => string;
  /** While another year loads: this month stays to be looked at, and no day can be opened. */
  frozen?: boolean | undefined;
  /** A tap on a day up to today, with the day's button (the focus returns to it). */
  onPick: (day: string, from: HTMLElement) => void;
}

/** A large calendar for one month: tap a day up to today to log or change it. Three fills and
 * the moon ring; a day with nothing logged is a plain number (never greyed, never crossed). */
export function MonthView({
  stats,
  month,
  moon,
  auto,
  city,
  showLadies,
  weekdays,
  dateLabel,
  frozen,
  onPick,
}: Props) {
  const { l10n } = useLocalization();
  const offset = mondayFirst(stats.year, month);
  const days = daysInMonth(stats.year, month);
  return (
    <div className="month-grid" role="group" aria-labelledby="month-title">
      {weekdays.map((w, i) => (
        <span key={`w${String(i)}`} className="weekday" aria-hidden="true">
          {w}
        </span>
      ))}
      {Array.from({ length: offset }, (_, i) => (
        <span key={`pad${String(i)}`} />
      ))}
      {Array.from({ length: days }, (_, i) => {
        const day = dateOf(stats.year, month, i + 1);
        const cell = cellAt(stats, day);
        const future = cell === undefined;
        const rest = cell === "none" ? auto.get(day) : undefined;
        const marker = moon.has(day) ? "yes" : "no";
        const label = future
          ? l10n.getString("stats-cell-future", { date: dateLabel(day), moon: marker })
          : rest
            ? l10n.getString("stats-cell-auto", autoArgs(rest, dateLabel(day), city))
            : l10n.getString("stats-cell-label", {
                date: dateLabel(day),
                status: l10n.getString(labelKey(cell, showLadies)),
                moon: marker,
              });
        const kind = future ? "future" : kindOf(cell, rest !== undefined);
        const classes = [
          "day",
          kind !== "none" && kind,
          day === stats.today && "today",
          moon.has(day) && "moon-marker",
          showLadies && cell === "ladies" && "flower",
        ];
        return (
          <button
            key={day}
            type="button"
            className={classes.filter(Boolean).join(" ")}
            disabled={future || frozen}
            aria-label={label}
            aria-current={day === stats.today ? "date" : undefined}
            onClick={(event) => {
              onPick(day, event.currentTarget);
            }}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}
